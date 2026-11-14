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
