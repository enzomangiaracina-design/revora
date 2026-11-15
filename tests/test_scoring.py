"""Tests du calcul du score global."""

import pytest

from core.scoring import DEFAULT_WEIGHTS, compute_global_score


def test_default_weights_sum_to_one():
    assert sum(DEFAULT_WEIGHTS.values()) == pytest.approx(1)


def test_global_score_formula():
    # 0,35 × 80 + 0,40 × 50 + 0,25 × 20 = 28 + 20 + 5 = 53
    assert compute_global_score(80, 50, 20) == 53.0


def test_global_score_bounds():
    assert compute_global_score(0, 0, 0) == 0
    assert compute_global_score(100, 100, 100) == 100


def test_custom_weights():
    weights = {"fit": 0.5, "engagement": 0.25, "intent": 0.25}
    # 0,5 × 80 + 0,25 × 40 + 0,25 × 40 = 40 + 10 + 10 = 60
    assert compute_global_score(80, 40, 40, weights) == 60.0


def test_weights_must_sum_to_one():
    with pytest.raises(ValueError):
        compute_global_score(50, 50, 50, {"fit": 0.5, "engagement": 0.5, "intent": 0.5})


def test_score_out_of_range_is_rejected():
    with pytest.raises(ValueError):
        compute_global_score(120, 50, 50)

    with pytest.raises(ValueError):
        compute_global_score(-1, 50, 50)


def test_score_must_be_a_number():
    with pytest.raises(TypeError):
        compute_global_score("80", 50, 50)


# ---------- Phase 5 : moteur de scoring ----------

from datetime import date

import database
from core import scoring
from core import score_service

TODAY = date(2026, 11, 14)


def interaction(day, channel="Call", direction="Outbound", event_type="Completed"):
    return {
        "occurred_at_local": f"{day} 10:00:00", "channel": channel,
        "direction": direction, "event_type": event_type,
    }


PROSPECT = {"vertical": "SaaS", "job_title": "Head of Sales", "status": "In contact"}
ICP = {"icp": {"verticals": ["SaaS"], "title_keywords": ["sales", "ceo"]}}


def test_global_score_without_fit_uses_available_dimensions():
    # (0,40 × 50 + 0,25 × 80) / 0,65 = 61,5
    assert compute_global_score(None, 50, 80) == 61.5


def test_decay():
    assert scoring.decay(0, 30) == 1
    assert scoring.decay(30, 30) == pytest.approx(0.5)
    assert scoring.decay(60, 30) == pytest.approx(0.25)


def test_fit_not_configured():
    fit, explanation = scoring.compute_fit(PROSPECT, scoring.merge_config())
    assert fit is None
    assert "not configured" in explanation[0]["signal"]


def test_fit_with_target_profile():
    config = scoring.merge_config(ICP)

    assert scoring.compute_fit(PROSPECT, config)[0] == 100
    assert scoring.compute_fit({**PROSPECT, "job_title": "Engineer"}, config)[0] == 50
    assert scoring.compute_fit({"vertical": "Finance", "job_title": None}, config)[0] == 0


def test_fit_ignores_accented_case():
    config = scoring.merge_config({"icp": {"verticals": ["Santé"], "title_keywords": []}})
    assert scoring.compute_fit({"vertical": "SANTÉ"}, config)[0] == 100


def test_attempts_without_reaction_give_no_engagement():
    """Le cahier des charges : ne pas surévaluer un prospect très sollicité."""

    attempts = [interaction("2026-11-1" + str(d), event_type="No answer") for d in range(10)]
    attempts += [interaction("2026-11-13", channel="Email") ]  # email sortant

    score, explanation = scoring.compute_engagement(attempts, scoring.merge_config(), TODAY)

    assert score == 0
    assert "11 outbound attempt(s) without reaction" in explanation[-1]["signal"]


def test_engagement_points_decay_and_cap():
    config = scoring.merge_config()

    fresh = scoring.compute_engagement(
        [interaction("2026-11-14", "Email", "Inbound")], config, TODAY
    )[0]
    old = scoring.compute_engagement(
        [interaction("2026-10-15", "Email", "Inbound")], config, TODAY
    )[0]
    many = scoring.compute_engagement(
        [interaction("2026-11-14", "Email", "Inbound")] * 5, config, TODAY
    )

    assert fresh == 20
    assert old == 10          # 30 jours = une demi-vie
    assert many[0] == 40      # plafond des réponses email
    assert sum(1 for i in many[1] if "cap of 40" in i["signal"]) == 3


def test_engagement_is_capped_at_100():
    signals = (
        [interaction("2026-11-14", "Call", "Inbound", "Positive response")] * 3
        + [interaction("2026-11-14", "Email", "Inbound")] * 3
        + [interaction("2026-11-14", "Call", "Outbound", "Completed")] * 3
    )

    assert scoring.compute_engagement(signals, scoring.merge_config(), TODAY)[0] == 100


def test_intent_confirmed_and_observed():
    prospect = {**PROSPECT, "need_identified": 1, "budget_confirmed": 1}
    meeting = [interaction("2026-11-14", event_type="Meeting booked")]

    score, explanation = scoring.compute_intent(prospect, meeting, scoring.merge_config(), TODAY)

    assert score == 25 + 30 + 35
    assert {i["type"] for i in explanation} == {"confirmed", "observed"}


def test_intent_is_zero_in_closed_stage():
    prospect = {**PROSPECT, "status": "Disqualified", "budget_confirmed": 1}

    score, explanation = scoring.compute_intent(prospect, [], scoring.merge_config(), TODAY, stage_closed=True)

    assert score == 0
    assert explanation[0]["type"] == "rule"


def test_compute_scores_and_temperature():
    prospect = {**PROSPECT, "need_identified": 1, "is_decision_maker": 1,
                "budget_confirmed": 1, "demo_requested": 1}
    signals = [interaction("2026-11-14", "Call", "Inbound", "Positive response")]

    result = scoring.compute_scores(prospect, signals, ICP, today=TODAY)

    # Fit 100, Engagement 25 + 20 = 45, Intent 100
    assert (result["fit"], result["engagement"], result["intent"]) == (100, 45, 100)
    assert result["global"] == round(0.35 * 100 + 0.40 * 45 + 0.25 * 100)
    assert result["temperature"] == "Hot"
    assert scoring.temperature(39) == "Cold"
    assert scoring.temperature(40) == "Warm"


@pytest.mark.parametrize("config, expected", [
    ({"weights": {"fit": 0.5, "engagement": 0.5, "intent": 0.5}}, "100 %"),
    ({"thresholds": {"hot": 40, "warm": 50}}, "Warm < Hot"),
    ({"half_life_days": 0}, "half-life"),
])
def test_validate_config(config, expected):
    errors = scoring.validate_config(scoring.merge_config(config))
    assert any(expected in error for error in errors)


# ---------- Service : configuration, historique ----------

def test_config_is_saved_and_validated(temp_db):
    ok, _ = score_service.save_config(ICP)
    assert ok
    assert score_service.load_config()["icp"]["verticals"] == ["SaaS"]

    ok, message = score_service.save_config({"thresholds": {"hot": 10, "warm": 50}})
    assert not ok
    assert score_service.load_config()["thresholds"]["hot"] == 70


def test_history_only_records_changes(thomas):
    score_service.refresh_scores(TODAY)
    score_service.refresh_scores(TODAY)

    assert len(database.get_score_history(thomas)) == 1

    database.update_qualification(thomas, {"budget_confirmed": True})
    results = score_service.refresh_scores(TODAY)

    history = score_service.score_changes(database.get_score_history(thomas))
    assert len(history) == 2
    assert results[thomas]["intent"] == 30
    assert history[-1]["delta"] == history[-1]["global_score"] - history[0]["global_score"]
    assert any(i["signal"] == "Budget confirmed" for i in history[-1]["explanation"])


def test_qualification_ignores_unknown_fields(thomas):
    database.update_qualification(thomas, {"need_identified": 1, "hacked": 1})

    prospect = database.get_prospect_by_id(thomas)
    assert prospect["need_identified"] == 1
    assert prospect["budget_confirmed"] == 0


def test_calibration_by_stage(thomas):
    results = score_service.refresh_scores(TODAY)
    rows = score_service.calibration_by_stage(
        database.get_all_prospects(), results, database.get_stages()
    )

    first = rows[0]
    assert first["Stage"] == "To prospect" and first["Prospects"] == 1
    assert rows[1]["Average score"] is None
