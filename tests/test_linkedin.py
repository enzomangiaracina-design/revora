"""Tests de la phase 9 — LinkedIn (saisie manuelle, aucun accès à LinkedIn)."""

from datetime import date, datetime

import pytest

import database
from core import activity_service, performance_service, prospect_service, scoring
from core.deduplication import normalize_linkedin_url

NOW = datetime(2026, 11, 15, 12, 0)


# ---------- URL de profil ----------

@pytest.mark.parametrize("url, expected", [
    ("linkedin.com/in/Jane-Doe", "https://www.linkedin.com/in/jane-doe"),
    ("https://fr.linkedin.com/in/jane-doe/?trk=public", "https://www.linkedin.com/in/jane-doe"),
    ("http://www.linkedin.com/in/jane.doe-42/", "https://www.linkedin.com/in/jane.doe-42"),
    ("https://www.linkedin.com/in/ren%C3%A9-lef%C3%A8vre", "https://www.linkedin.com/in/ren%c3%a9-lef%c3%a8vre"),
    ("https://www.linkedin.com/company/acme", None),      # page entreprise, pas un profil
    ("https://evil.example/in/jane", None),
    ("https://www.linkedin.com/in/x)[a](javascript:alert(1))", None),  # tentative d'injection de lien
    ("", None),
    (None, None),
])
def test_normalize_linkedin_url(url, expected):
    assert normalize_linkedin_url(url) == expected


def test_invalid_linkedin_url_is_rejected():
    errors = prospect_service.validate_prospect({
        "first_name": "A", "last_name": "B", "company_name": "C",
        "linkedin_url": "https://www.linkedin.com/company/acme",
    })

    assert any("LinkedIn" in error for error in errors)


def test_create_stores_normalized_url_and_detects_duplicate(temp_db):
    ok, _ = prospect_service.create_prospect({
        "first_name": "Jane", "last_name": "Doe", "company_name": "Acme",
        "linkedin_url": "fr.linkedin.com/in/Jane-Doe/",
    })
    assert ok
    assert database.get_all_prospects()[0]["linkedin_url"] == "https://www.linkedin.com/in/jane-doe"

    # Même profil, autre nom et autre entreprise : doublon quand même
    ok, message = prospect_service.create_prospect({
        "first_name": "J.", "last_name": "D.", "company_name": "Other",
        "linkedin_url": "https://www.linkedin.com/in/jane-doe?trk=x",
    })
    assert not ok and "LinkedIn" in message


def test_update_keeps_url_when_not_provided(thomas):
    database.update_prospect(thomas, "Thomas", "Martins", "AlphaEngine", "SaaS", None, None, None,
                             "A prospecter", linkedin_url="https://www.linkedin.com/in/thomas")
    # Ancien appel, sans l'argument : l'URL ne doit pas être effacée
    database.update_prospect(thomas, "Thomas", "Martins", "AlphaEngine", "SaaS", None, None, None,
                             "En contact")

    assert database.get_prospect_by_id(thomas)["linkedin_url"] == "https://www.linkedin.com/in/thomas"

    # Champ vidé dans le formulaire : l'URL est effacée
    prospect_service.update_prospect(thomas, {
        "first_name": "Thomas", "last_name": "Martins", "company_name": "AlphaEngine",
        "linkedin_url": "",
    })
    assert database.get_prospect_by_id(thomas)["linkedin_url"] is None


def test_csv_import_recognizes_linkedin_column(temp_db):
    content = "Prénom;Nom;Entreprise;Profil LinkedIn\nZoé;Petit;Gamma;linkedin.com/in/zoe-petit\n"

    df, ignored = prospect_service.read_prospect_csv(content.encode())
    report = prospect_service.import_prospects(df)

    assert ignored == [] and report["created"] == 1
    assert database.get_all_prospects()[0]["linkedin_url"] == "https://www.linkedin.com/in/zoe-petit"


# ---------- Actions LinkedIn dans l'activité ----------

def linkedin_action(event_type, channel="LinkedIn", direction="Outbound", subject=""):
    return {"channel": channel, "direction": direction, "event_type": event_type,
            "subject": subject, "content": "", "occurred_at": datetime(2026, 11, 15, 9, 0)}


@pytest.mark.parametrize("event_type, direction", [
    ("Connection request sent", "Outbound"),
    ("Connection accepted", "Inbound"),
    ("InMail sent", "Outbound"),
])
def test_linkedin_action_sets_direction_and_subject(thomas, event_type, direction):
    # Sens volontairement faux et objet vide : REVORA corrige le sens et l'objet est facultatif
    ok, _ = activity_service.log_interaction(
        thomas, linkedin_action(event_type, direction="Internal"), now=NOW
    )

    saved = database.get_interactions(thomas)[0]
    assert ok
    assert (saved["direction"], saved["event_type"], saved["subject"]) == (direction, event_type, event_type)


def test_linkedin_action_requires_linkedin_channel(thomas):
    ok, message = activity_service.log_interaction(
        thomas, linkedin_action("Connection accepted", channel="Email"), now=NOW
    )

    assert not ok and "LinkedIn" in message
    assert database.get_interactions(thomas) == []


# ---------- Scoring et performance ----------

def interaction(day, event_type, direction, contact=1):
    return {"contact_id": contact, "occurred_at_local": f"{day} 10:00:00", "channel": "LinkedIn",
            "direction": direction, "event_type": event_type}


def test_accepted_connection_is_weak_engagement_not_a_reply():
    config = scoring.merge_config()
    accepted = [interaction("2026-11-15", "Connection accepted", "Inbound")] * 3
    reply = [interaction("2026-11-15", "Completed", "Inbound")]

    score, explanation = scoring.compute_engagement(accepted, config, date(2026, 11, 15))
    assert score == 10  # plafonné à 10, même si accepté plusieurs fois
    assert explanation[0]["signal"].startswith("LinkedIn connection accepted")

    assert scoring.compute_engagement(reply, config, date(2026, 11, 15))[0] == 15


def test_linkedin_performance_indicators():
    data = [
        interaction("2026-11-10", "Connection request sent", "Outbound", contact=1),
        interaction("2026-11-12", "Connection accepted", "Inbound", contact=1),
        interaction("2026-11-11", "Connection request sent", "Outbound", contact=2),
        interaction("2026-11-13", "InMail sent", "Outbound", contact=3),
        interaction("2026-11-14", "Completed", "Outbound", contact=1),        # message LinkedIn
    ]

    k = performance_service.compute_kpis(data, [], date(2026, 11, 9), date(2026, 11, 15))

    assert k["linkedin_requests"] == 2
    assert k["linkedin_acceptance_rate"] == 50          # 1 sur 2 prospects invités
    assert k["linkedin_messages"] == 2                   # InMail + message (pas l'invitation)
    assert k["replied"] == 0                             # accepter n'est pas répondre
