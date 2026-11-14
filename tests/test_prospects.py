"""Tests sur la création des prospects et la normalisation des coordonnées."""

import database
from core.deduplication import normalize_email, normalize_phone


def test_duplicate_email_is_rejected(thomas):
    """Un même email (même avec des majuscules) ne doit pas créer de doublon."""

    ok, message = database.create_prospect(
        "Tom", "Martins", "AlphaEngine", "SaaS",
        "  THOMAS.MARTIN@example.com ", None, None,
    )

    assert ok is False
    assert "existe" in message
    assert len(database.get_all_prospects()) == 1


def test_company_is_reused(thomas):
    database.create_prospect(
        "Julie", "Durand", "alphaengine", "SaaS", "julie@example.com", None, None
    )

    prospects = database.get_all_prospects()
    assert len(prospects) == 2
    assert len({p["company_name"].lower() for p in prospects}) == 1


def test_normalize_email():
    assert normalize_email("  Thomas.Martin@Example.COM ") == "thomas.martin@example.com"
    assert normalize_email("") is None
    assert normalize_email(None) is None


def test_normalize_phone_french_formats():
    expected = "+33612345678"

    assert normalize_phone("0612345678") == expected
    assert normalize_phone("06 12 34 56 78") == expected
    assert normalize_phone("06.12.34.56.78") == expected
    assert normalize_phone("+33 6 12 34 56 78") == expected
    assert normalize_phone("0033612345678") == expected


def test_normalize_phone_invalid():
    assert normalize_phone("") is None
    assert normalize_phone(None) is None
    assert normalize_phone("abc") is None
    assert normalize_phone("12345") is None
