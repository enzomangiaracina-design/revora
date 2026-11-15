"""Tests des indicateurs de performance (fonctions pures, valeurs calculées à la main)."""

from datetime import date

import pytest

from core import performance_service as perf

# Période testée : lundi 9 au dimanche 15 novembre 2026 (5 jours ouvrés)
START, END = date(2026, 11, 9), date(2026, 11, 15)


def i(contact, day, channel="Call", direction="Outbound", result="No answer", time="10:00:00"):
    return {"contact_id": contact, "occurred_at_local": f"{day} {time}", "channel": channel,
            "direction": direction, "event_type": result}


INTERACTIONS = [
    # Prospect 1 : appelé avant la période, rappelé 4 jours plus tard, a répondu par email
    i(1, "2026-11-06"),
    i(1, "2026-11-10", result="Completed"),
    i(1, "2026-11-11", "Email", "Inbound", "Completed"),
    # Prospect 2 : un appel sans réponse, un email, puis rendez-vous obtenu
    i(2, "2026-11-09"),
    i(2, "2026-11-10", "Email", result="Completed", time="09:00:00"),
    i(2, "2026-11-12", result="Meeting booked"),
    # Prospect 3 : email envoyé, pas de réaction
    i(3, "2026-11-13", "Email", result="Completed"),
    # Prospect 4 : a écrit AVANT d'être contacté dans la période (pas une réponse)
    i(4, "2026-11-09", "Email", "Inbound", "Completed", time="08:00:00"),
    i(4, "2026-11-09", "LinkedIn", result="Completed", time="11:00:00"),
    # Hors période
    i(5, "2026-10-20"),
]

OBJECTIONS = [
    {"contact_id": 2, "occurred_at_local": "2026-11-12 10:00:00"},
    {"contact_id": 3, "occurred_at_local": "2026-10-01 10:00:00"},
]


def test_periods_and_working_days():
    assert perf.period_range(7, today=date(2026, 11, 15)) == (START, END)
    assert perf.previous_range(START, END) == (date(2026, 11, 2), date(2026, 11, 8))
    assert perf.working_days(START, END) == 5
    assert perf.working_days(date(2026, 11, 14), date(2026, 11, 15)) == 0  # week-end


def test_compute_kpis():
    k = perf.compute_kpis(INTERACTIONS, OBJECTIONS, START, END)

    # Appels sortants : P1 (10/11), P2 (09/11, 12/11) = 3 ; connectés : Completed + Meeting booked = 2
    assert (k["calls"], k["connection_rate"]) == (3, 67)
    assert k["calls_per_day"] == 0.6                      # 3 / 5 jours ouvrés
    assert (k["emails_sent"], k["emails_received"]) == (2, 2)
    # Contactés : 1, 2, 3, 4 ; ont répondu APRÈS le contact : seulement 1
    assert (k["contacted"], k["replied"], k["reply_rate"]) == (4, 1, 25)
    assert (k["meetings"], k["conversion_rate"]) == (1, 25)
    assert k["objections"] == 1
    # Relances : P1 06→10 = 4 j ; P2 09→10 (0,96 j) et 10→12 (2,04 j) ; moyenne = 7 / 3
    assert k["follow_up_delay"] == 2.3


def test_empty_period_gives_no_misleading_zero_rates():
    k = perf.compute_kpis([], [], START, END)

    assert k["calls"] == 0
    assert (k["connection_rate"], k["reply_rate"], k["conversion_rate"]) == (None, None, None)
    assert k["follow_up_delay"] is None
    assert perf.compute_kpis([], [], date(2026, 11, 14), date(2026, 11, 15))["calls_per_day"] is None


@pytest.mark.parametrize("current, previous, expected", [
    (5, 3, 2), (25, 40, -15), (None, 3, None), (2.3, None, None), (0.6, 0.6, 0),
])
def test_delta(current, previous, expected):
    assert perf.delta(current, previous) == expected


def test_daily_activity():
    rows = {r["Day"]: r for r in perf.daily_activity(INTERACTIONS, START, END)}

    assert len(rows) == 7
    assert rows["2026-11-09"] == {"Day": "2026-11-09", "Calls": 1, "Emails sent": 0, "Replies": 1}
    assert rows["2026-11-10"] == {"Day": "2026-11-10", "Calls": 1, "Emails sent": 1, "Replies": 0}
    assert rows["2026-11-15"]["Calls"] == 0


def test_by_vertical():
    prospects = [{"id": 1, "vertical": "SaaS"}, {"id": 2, "vertical": "SaaS"},
                 {"id": 3, "vertical": "Finance"}, {"id": 4, "vertical": None}, {"id": 5, "vertical": "Santé"}]

    rows = {r["Vertical"]: r for r in perf.by_vertical(INTERACTIONS, OBJECTIONS, prospects, START, END)}

    assert set(rows) == {"SaaS", "Finance", "Unknown"}  # Santé : aucun contact dans la période
    assert rows["SaaS"]["Prospects contacted"] == 2
    assert (rows["SaaS"]["Reply rate (%)"], rows["SaaS"]["Conversion (%)"]) == (50, 50)
    assert rows["SaaS"]["Objections"] == 1
    assert rows["Finance"]["Calls"] == 0 and rows["Finance"]["Connection rate (%)"] is None


# ---------- P2.3 : faible volume et filtre par commercial ----------

from core.performance_service import (
    MIN_SAMPLE, filter_by_owner, low_volume_rates, owner_options,
)


def test_low_volume_flags_only_small_samples():
    kpis = {"calls": 3, "connection_rate": 67, "contacted": 1, "reply_rate": 100,
            "conversion_rate": 0, "invited": 0, "linkedin_acceptance_rate": None}

    assert low_volume_rates(kpis) == {
        "connection_rate": "connection rate: 3 calls",
        "reply_rate": "reply rate: 1 prospect contacted",
        "conversion_rate": "conversion rate: 1 prospect contacted",
    }


def test_enough_volume_is_not_flagged():
    kpis = {"calls": MIN_SAMPLE, "connection_rate": 40, "contacted": 25, "reply_rate": 12,
            "conversion_rate": 4, "invited": 12, "linkedin_acceptance_rate": 50}

    assert low_volume_rates(kpis) == {}


PROSPECTS = [{"id": 1, "owner": "Lea"}, {"id": 2, "owner": "Marc"}, {"id": 3, "owner": None}]


def test_owner_options():
    assert owner_options(PROSPECTS) == ["Lea", "Marc", "Unassigned"]
    assert owner_options(PROSPECTS[:2]) == ["Lea", "Marc"]


def test_filter_by_owner_on_interactions_and_prospects():
    interactions = [{"contact_id": 1}, {"contact_id": 2}, {"contact_id": 3}]

    assert filter_by_owner(interactions, PROSPECTS, ["Lea", "Unassigned"]) == [{"contact_id": 1}, {"contact_id": 3}]
    assert filter_by_owner(PROSPECTS, PROSPECTS, ["Marc"]) == [PROSPECTS[1]]
    assert filter_by_owner(interactions, PROSPECTS, []) == interactions
    assert filter_by_owner([], PROSPECTS, ["Lea"]) == []


def test_compute_kpis_exposes_invited_sample():
    assert perf.compute_kpis([], [], date(2026, 11, 1), date(2026, 11, 14))["invited"] == 0
