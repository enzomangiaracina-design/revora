"""Tests des connecteurs HubSpot et Gmail et du moteur de synchronisation.

AUCUN appel réseau : un faux "transport" renvoie des réponses préparées
au format des API (données fictives).
"""

import json
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import pytest

import database
from core import sync_service
from integrations.config import load_env_file
from integrations.gmail.connector import GmailConnector, message_time
from integrations.http import HttpClient, IntegrationError
from integrations.hubspot.connector import HubSpotConnector, parse_hubspot_time, to_epoch_ms


class FakeTransport:
    """Imite un serveur : associe (méthode, chemin) à une liste de réponses."""

    def __init__(self, routes):
        self.routes = {key: list(value) for key, value in routes.items()}
        self.calls = []

    def __call__(self, method, url, headers, body):
        parsed = urlparse(url)
        self.calls.append({"method": method, "path": parsed.path,
                           "query": parse_qs(parsed.query), "body": body, "headers": headers})

        key = (method, parsed.path)
        if key not in self.routes or not self.routes[key]:
            return 404, {}, {"message": f"no route {key}"}

        response = self.routes[key].pop(0) if len(self.routes[key]) > 1 else self.routes[key][0]
        return response


def ok(payload):
    return 200, {}, payload


# ==========================================
# CLIENT HTTP
# ==========================================

def test_http_retries_then_succeeds():
    waits = []
    transport = FakeTransport({("GET", "/x"): [(429, {"Retry-After": "2"}, {}), (503, {}, {}), ok({"a": 1})]})
    client = HttpClient("https://api.test", "tok", transport=transport, sleep=waits.append)

    assert client.request("GET", "/x") == {"a": 1}
    assert waits == [2.0, 2]  # Retry-After respecté, puis attente exponentielle (2^1)
    assert transport.calls[0]["headers"]["Authorization"] == "Bearer tok"


def test_http_raises_on_client_error():
    transport = FakeTransport({("GET", "/x"): [(401, {}, {"message": "bad token"})]})
    client = HttpClient("https://api.test", "tok", transport=transport, sleep=lambda s: None)

    with pytest.raises(IntegrationError) as error:
        client.request("GET", "/x")

    assert error.value.status == 401
    assert "bad token" in str(error.value)


def test_http_gives_up_after_max_retries():
    transport = FakeTransport({("GET", "/x"): [(500, {}, {})]})
    client = HttpClient("https://api.test", "tok", transport=transport, max_retries=2, sleep=lambda s: None)

    with pytest.raises(IntegrationError):
        client.request("GET", "/x")

    assert len(transport.calls) == 3


def test_env_file_does_not_override(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("# comment\nREVORA_TEST_A=from_file\nREVORA_TEST_B='quoted'\nEMPTY=\n")
    monkeypatch.setenv("REVORA_TEST_A", "from_terminal")
    monkeypatch.delenv("REVORA_TEST_B", raising=False)

    load_env_file(env)

    import os
    assert os.environ["REVORA_TEST_A"] == "from_terminal"
    assert os.environ["REVORA_TEST_B"] == "quoted"
    monkeypatch.delenv("REVORA_TEST_B")


# ==========================================
# HUBSPOT
# ==========================================

SEARCH = "/crm/v3/objects/{}/search"
ASSOC = "/crm/v3/associations/{}/contacts/batch/read"

HS_CALL = {"id": "501", "properties": {
    "hs_timestamp": "2026-11-12T09:30:00Z", "hs_call_direction": "OUTBOUND",
    "hs_call_duration": "185000", "hs_call_status": "COMPLETED",
    "hs_call_disposition": "f240bbac-87c9-4f6e-bf70-924b57d47db7",
    "hs_call_to_number": "+33 6 12 34 56 78", "hs_call_title": "Discovery", "hs_call_body": "Notes privées",
}}

HS_EMAIL = {"id": "777", "properties": {
    "hs_timestamp": "1762939800000", "hs_email_direction": "INCOMING_EMAIL",
    "hs_email_subject": "RE: Proposition REVORA", "hs_email_text": "Corps privé",
    "hs_email_status": "SENT", "hs_email_from_email": "thomas.martin@example.com",
    "hs_email_to_email": "sdr@revora.test",
}}


def hubspot(routes, **kwargs):
    transport = FakeTransport(routes)
    return HubSpotConnector(token="test-token", transport=transport, sleep=lambda s: None, **kwargs), transport


def hubspot_routes(calls=None, emails=None):
    return {
        ("POST", SEARCH.format("calls")): [ok({"results": calls or []})],
        ("POST", SEARCH.format("emails")): [ok({"results": emails or []})],
        ("POST", ASSOC.format("calls")): [ok({"results": [{"from": {"id": "501"}, "to": [{"id": "9001"}]}]})],
        ("POST", ASSOC.format("emails")): [ok({"results": [{"from": {"id": "777"}, "to": [{"toObjectId": 9001}]}]})],
    }


def test_hubspot_requires_token(monkeypatch):
    monkeypatch.setattr("integrations.hubspot.connector.get_secret", lambda name: None)

    with pytest.raises(IntegrationError, match="HUBSPOT_ACCESS_TOKEN"):
        HubSpotConnector().authenticate()


def test_hubspot_time_and_epoch():
    assert parse_hubspot_time("2026-11-12T09:30:00Z") == datetime(2026, 11, 12, 9, 30, tzinfo=timezone.utc)
    assert parse_hubspot_time("1762939800000") == datetime(2025, 11, 12, 9, 30, tzinfo=timezone.utc)
    assert to_epoch_ms(datetime(2026, 1, 1, tzinfo=timezone.utc)) == 1767225600000


def test_hubspot_fetch_paginates_and_filters_incrementally():
    connector, transport = hubspot({
        ("POST", SEARCH.format("calls")): [
            ok({"results": [HS_CALL], "paging": {"next": {"after": "100"}}}),
            ok({"results": [{**HS_CALL, "id": "502"}]}),
        ],
        ("POST", SEARCH.format("emails")): [ok({"results": []})],
        ("POST", ASSOC.format("calls")): [ok({"results": []})],
    })

    events = connector.fetch_events(since=datetime(2026, 11, 1, tzinfo=timezone.utc))

    searches = [c for c in transport.calls if c["path"] == SEARCH.format("calls")]
    assert [e["id"] for e in events] == ["501", "502"]
    assert searches[1]["body"]["after"] == "100"
    assert searches[0]["body"]["filterGroups"][0]["filters"][0] == {
        "propertyName": "hs_lastmodifieddate", "operator": "GTE", "value": "1793491200000",
    }


def test_hubspot_normalize_call():
    connector, _ = hubspot(hubspot_routes(calls=[HS_CALL]))
    event = connector.normalize_event(connector.fetch_events()[0])

    assert (event.channel, event.direction, event.event_type) == ("Call", "Outbound", "Completed")
    assert event.external_id == "call:501"
    assert event.metadata["duration_seconds"] == 185
    assert event.match_keys["hubspot_contact_ids"] == ["9001"]
    assert event.match_keys["phones"] == ["+33 6 12 34 56 78"]
    assert event.content is None  # contenu non importé par défaut (RGPD)


@pytest.mark.parametrize("props, expected", [
    ({"hs_call_disposition": "b2cf5968-551e-4856-9783-52b3da59a7d0"}, "Voicemail"),
    ({"hs_call_disposition": None, "hs_call_status": "NO_ANSWER"}, "No answer"),
    ({"hs_call_disposition": None, "hs_call_status": "COMPLETED"}, "Other"),
])
def test_hubspot_call_results(props, expected):
    connector, _ = hubspot({})
    raw = {"kind": "call", "id": "1", "properties": {**HS_CALL["properties"], **props}}

    assert connector.normalize_event(raw).event_type == expected


def test_hubspot_normalize_email_and_content_opt_in():
    connector, _ = hubspot(hubspot_routes(emails=[HS_EMAIL]), include_content=True)
    event = connector.normalize_event(connector.fetch_events()[0])

    assert (event.direction, event.subject) == ("Inbound", "RE: Proposition REVORA")
    assert event.match_keys["emails"] == ["thomas.martin@example.com"]
    assert event.match_keys["hubspot_contact_ids"] == ["9001"]
    assert event.content == "Corps privé"


def test_hubspot_message_id_read_only_if_present():
    connector, _ = hubspot({})
    headers = json.dumps({"from": {"email": "a@b.c"}, "Message-Id": "<abc@mail>"})
    raw = {"kind": "email", "id": "1", "properties": {**HS_EMAIL["properties"], "hs_email_headers": headers}}

    assert connector.normalize_event(raw).metadata["message_id"] == "<abc@mail>"
    assert "message_id" not in connector.normalize_event({**raw, "properties": HS_EMAIL["properties"]}).metadata


def test_hubspot_normalize_contact():
    record = {"id": 9001, "properties": {"firstname": "Thomas", "lastname": "Martins", "company": "AlphaEngine",
                                         "email": "t@a.io", "mobilephone": "0611", "jobtitle": "CEO"}}

    assert HubSpotConnector.normalize_contact(record) == {
        "hubspot_id": "9001", "first_name": "Thomas", "last_name": "Martins", "company_name": "AlphaEngine",
        "email": "t@a.io", "phone": "0611", "job_title": "CEO",
    }


# ==========================================
# GMAIL
# ==========================================

def gmail_message(mid, sender, to, subject, ms, labels=("INBOX",), history="100", message_id=None):
    headers = [{"name": "From", "value": sender}, {"name": "To", "value": to},
               {"name": "Subject", "value": subject}]
    if message_id:
        headers.append({"name": "Message-ID", "value": message_id})
    return {"id": mid, "threadId": "t" + mid, "labelIds": list(labels), "historyId": history,
            "internalDate": str(ms), "payload": {"headers": headers}}


MSG_IN = gmail_message("m1", "Thomas Martin <thomas.martin@example.com>", "sdr@revora.test",
                       "Re: Proposition REVORA", 1762939920000, history="120", message_id="<x1@mail>")
MSG_OUT = gmail_message("m2", "SDR <sdr@revora.test>", "Thomas <THOMAS.MARTIN@example.com>, cc@other.test",
                        "Proposition REVORA", 1762853400000, labels=("SENT",), history="110")
MSG_SPAM = gmail_message("m3", "x@spam.test", "sdr@revora.test", "Win", 1762853400000, labels=("SPAM",))


def gmail(routes, **kwargs):
    transport = FakeTransport(routes)
    connector = GmailConnector(token="tok", user_email="sdr@revora.test", transport=transport,
                               sleep=lambda s: None, **kwargs)
    return connector, transport


def gmail_full_routes():
    return {
        ("GET", "/gmail/v1/users/me/messages"): [ok({"messages": [{"id": "m1"}, {"id": "m2"}, {"id": "m3"}]})],
        ("GET", "/gmail/v1/users/me/messages/m1"): [ok(MSG_IN)],
        ("GET", "/gmail/v1/users/me/messages/m2"): [ok(MSG_OUT)],
        ("GET", "/gmail/v1/users/me/messages/m3"): [ok(MSG_SPAM)],
    }


def test_gmail_requires_token(monkeypatch):
    monkeypatch.setattr("integrations.gmail.connector.get_secret", lambda name: None)

    with pytest.raises(IntegrationError, match="RESTRICTED"):
        GmailConnector().authenticate()


def test_gmail_full_sync_uses_metadata_only_and_skips_spam():
    connector, transport = gmail(gmail_full_routes())

    messages = connector.fetch_events()

    assert [m["id"] for m in messages] == ["m1", "m2"]
    assert connector.last_sync_mode == "full"
    assert connector.state["history_id"] == "120"
    get_call = next(c for c in transport.calls if c["path"].endswith("/m1"))
    assert get_call["query"]["format"] == ["metadata"]
    assert "q" not in transport.calls[0]["query"]  # interdit avec gmail.metadata


def test_gmail_partial_sync_with_history():
    connector, transport = gmail({
        ("GET", "/gmail/v1/users/me/history"): [ok({"history": [{"messagesAdded": [{"message": {"id": "m1"}}]}]})],
        ("GET", "/gmail/v1/users/me/messages/m1"): [ok(MSG_IN)],
    }, state={"history_id": "100"})

    assert [m["id"] for m in connector.fetch_events()] == ["m1"]
    assert connector.last_sync_mode == "partial"
    assert transport.calls[0]["query"]["startHistoryId"] == ["100"]


def test_gmail_expired_history_falls_back_to_full_sync():
    routes = gmail_full_routes()
    routes[("GET", "/gmail/v1/users/me/history")] = [(404, {}, {"message": "expired"})]
    connector, _ = gmail(routes, state={"history_id": "1"})

    assert len(connector.fetch_events()) == 2
    assert connector.last_sync_mode == "full"


def test_gmail_normalize_directions():
    connector, _ = gmail({})
    connector.authenticate()

    inbound = connector.normalize_event(MSG_IN)
    outbound = connector.normalize_event(MSG_OUT)

    assert (inbound.direction, inbound.match_keys["emails"]) == ("Inbound", ["thomas.martin@example.com"])
    assert inbound.metadata == {"thread_id": "tm1", "message_id": "<x1@mail>"}
    assert inbound.content is None
    assert (outbound.direction, outbound.match_keys["emails"]) == (
        "Outbound", ["thomas.martin@example.com", "cc@other.test"])


def test_gmail_date_header_fallback():
    message = {"id": "z", "payload": {"headers": [{"name": "Date", "value": "Thu, 12 Nov 2026 10:00:00 +0100"}]}}

    assert message_time(message) == datetime(2026, 11, 12, 9, 0, tzinfo=timezone.utc)


# ==========================================
# MOTEUR DE SYNCHRONISATION (base temporaire)
# ==========================================

@pytest.fixture
def crm(thomas):
    """Thomas (relié à HubSpot 9001) + deux contacts partageant un standard."""

    database.set_hubspot_id(thomas, "9001")
    database.create_prospect("Ana", "Lopez", "BankCo", "Finance", "ana@bank.test", "01 40 00 00 00", None)
    database.create_prospect("Bob", "Ray", "BankCo", "Finance", "bob@bank.test", "0140000000", None)
    return thomas


def test_match_contact_priorities(crm):
    from integrations.base import NormalizedEvent
    index = sync_service.build_contact_index(database.get_all_prospects())

    def event(**keys):
        return NormalizedEvent("x", "1", "Call", "Outbound", "Other", datetime.now(timezone.utc), match_keys=keys)

    assert sync_service.match_contact(event(hubspot_contact_ids=["9001"]), index) == (crm, "crm_id")
    assert sync_service.match_contact(event(phones=["+33612345678"]), index) == (crm, "phone")
    assert sync_service.match_contact(event(emails=["THOMAS.MARTIN@example.com"]), index) == (crm, "email")
    # Standard partagé par Ana et Bob : pas de rattachement au hasard
    assert sync_service.match_contact(event(phones=["+33140000000"]), index)[0] is None
    assert sync_service.match_contact(event(phones=["+33140000000"]), index)[1].startswith("ambiguous")
    # Le standard est ambigu, mais l'email tranche
    assert sync_service.match_contact(event(phones=["+33140000000"], emails=["ana@bank.test"]), index)[1] == "email"


def test_normalize_subject():
    assert sync_service.normalize_subject("RE: Fwd:  Proposition  REVORA") == "proposition revora"
    assert sync_service.normalize_subject("TR: Démo") == "démo"


def test_run_sync_hubspot_is_idempotent(crm):
    connector, _ = hubspot(hubspot_routes(calls=[HS_CALL], emails=[HS_EMAIL]))

    first = sync_service.run_sync(connector, full=True)
    second = sync_service.run_sync(connector, full=True)

    assert (first["status"], first["fetched"], first["created"]) == ("success", 2, 2)
    assert (second["created"], second["duplicates"]) == (0, 2)
    assert len(database.get_interactions(crm)) == 2

    call = next(i for i in database.get_interactions(crm) if i["channel"] == "Call")
    assert call["provider"] == "hubspot" and call["external_id"] == "call:501"
    assert call["metadata"]["matched_by"] == "crm_id"
    assert call["occurred_at"] == "2026-11-12 09:30:00"  # stocké en UTC

    logs = database.get_sync_logs()
    assert [log["created"] for log in logs] == [0, 2]
    assert database.get_integrations()["hubspot"]["status"] == "Connected"


def test_same_email_from_gmail_and_hubspot_is_stored_once(crm):
    # HubSpot : réponse de Thomas le 12/11/2026 09:30 UTC
    hs_email = {"id": "777", "properties": {**HS_EMAIL["properties"], "hs_timestamp": "2026-11-12T09:30:00Z"}}
    connector, _ = hubspot(hubspot_routes(emails=[hs_email]))
    sync_service.run_sync(connector, full=True)

    # Gmail : le même email, reçu 1 minute plus tard dans la boîte, objet « Re: »
    same = gmail_message("g1", "thomas.martin@example.com", "sdr@revora.test", "Re: Proposition REVORA",
                         to_epoch_ms(datetime(2026, 11, 12, 9, 31, tzinfo=timezone.utc)))
    other = gmail_message("g2", "thomas.martin@example.com", "sdr@revora.test", "Autre sujet",
                          to_epoch_ms(datetime(2026, 11, 12, 9, 31, tzinfo=timezone.utc)))
    connector, _ = gmail({
        ("GET", "/gmail/v1/users/me/messages"): [ok({"messages": [{"id": "g1"}, {"id": "g2"}]})],
        ("GET", "/gmail/v1/users/me/messages/g1"): [ok(same)],
        ("GET", "/gmail/v1/users/me/messages/g2"): [ok(other)],
    })

    result = sync_service.run_sync(connector, full=True)

    assert (result["created"], result["duplicates"]) == (1, 1)
    assert sorted(i["provider"] for i in database.get_interactions(crm)) == ["gmail", "hubspot"]


def test_unmatched_and_failed_sync(crm, monkeypatch):
    stranger = gmail_message("s1", "inconnu@nowhere.test", "sdr@revora.test", "Hello", 1762939920000)
    connector, _ = gmail({
        ("GET", "/gmail/v1/users/me/messages"): [ok({"messages": [{"id": "s1"}]})],
        ("GET", "/gmail/v1/users/me/messages/s1"): [ok(stranger)],
    })

    result = sync_service.run_sync(connector, full=True)
    assert (result["unmatched"], result["created"]) == (1, 0)

    broken, _ = gmail({("GET", "/gmail/v1/users/me/messages"): [(401, {}, {"error": {"message": "Invalid Credentials"}})]})
    failed = sync_service.run_sync(broken, full=True)

    assert failed["status"] == "failed" and "Invalid Credentials" in failed["message"]
    assert database.get_integrations()["gmail"]["status"] == "Error"


def test_sync_state_is_remembered(crm):
    connector, _ = gmail(gmail_full_routes())
    sync_service.run_sync(connector, full=True)

    assert database.get_setting("sync_state:gmail")["connector_state"] == {"history_id": "120"}

    connector, transport = gmail({("GET", "/gmail/v1/users/me/history"): [ok({"history": []})]})
    sync_service.run_sync(connector)

    assert transport.calls[0]["query"]["startHistoryId"] == ["120"]


def test_import_hubspot_contacts(crm):
    connector, _ = hubspot({("POST", SEARCH.format("contacts")): [ok({"results": [
        {"id": "9001", "properties": {"firstname": "Thomas", "lastname": "Martins", "company": "AlphaEngine"}},
        {"id": "9002", "properties": {"firstname": "Ana", "lastname": "Lopez", "company": "BankCo",
                                      "email": "ANA@bank.test"}},
        {"id": "9003", "properties": {"firstname": "Zoé", "lastname": "Petit", "company": "Gamma",
                                      "email": "zoe@gamma.test"}},
        {"id": "9004", "properties": {"firstname": "Sans", "lastname": "Entreprise", "email": "x@y.test"}},
    ]})]})

    report = sync_service.import_hubspot_contacts(connector)

    assert (report["already_linked"], report["linked"], report["created"]) == (1, 1, 1)
    assert report["errors"][0]["hubspot_id"] == "9004"
    by_name = {p["first_name"]: p for p in database.get_all_prospects()}
    assert by_name["Ana"]["hubspot_id"] == "9002"
    assert (by_name["Zoé"]["hubspot_id"], by_name["Zoé"]["source"]) == ("9003", "HubSpot")
