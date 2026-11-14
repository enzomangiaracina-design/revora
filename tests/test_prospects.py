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


# ---------- Phase 2 : service prospects ----------

import pytest

from core import prospect_service as service


def make(**overrides):
    data = {
        "first_name": "Marie", "last_name": "Dupont", "company_name": "Exemple SAS",
        "vertical": "SaaS", "email": "marie@example.com", "phone": "0611223344",
        "job_title": "CEO", "status": "A prospecter", "source": "", "owner": "",
    }
    data.update(overrides)
    return data


def test_validate_valid_data():
    assert service.validate_prospect(make()) == []


@pytest.mark.parametrize("overrides, expected", [
    ({"first_name": " "}, "prénom"),
    ({"company_name": ""}, "entreprise"),
    ({"email": "pas-un-email"}, "Email invalide"),
    ({"phone": "12"}, "Téléphone invalide"),
    ({"status": "Inventé"}, "Statut inconnu"),
])
def test_validate_errors(overrides, expected):
    errors = service.validate_prospect(make(**overrides))
    assert any(expected in error for error in errors)


def test_service_create_and_name_duplicate(temp_db):
    ok, _ = service.create_prospect(make())
    assert ok

    # Pas d'email, mais même nom + entreprise (casse différente) : doublon
    ok, message = service.create_prospect(make(email="", first_name="MARIE", company_name="exemple sas"))
    assert not ok
    assert "Doublon" in message
    assert len(database.get_all_prospects()) == 1


def test_same_phone_is_not_a_duplicate(temp_db):
    """Deux personnes d'une même entreprise peuvent partager le standard."""

    service.create_prospect(make(phone="0140000000"))
    ok, _ = service.create_prospect(make(first_name="Paul", email="paul@example.com", phone="01 40 00 00 00"))

    assert ok


def test_service_update_keeps_own_email(thomas):
    ok, _ = service.update_prospect(thomas, make(
        first_name="Thomas", last_name="Martins", company_name="AlphaEngine",
        email="thomas.martin@example.com", status="Intéressé",
    ))

    assert ok
    assert database.get_prospect_by_id(thomas)["status"] == "Intéressé"


PROSPECTS = [
    {"id": 1, "first_name": "Thomas", "last_name": "Martins", "company_name": "AlphaEngine",
     "email": "thomas@alpha.io", "phone": "06 12 34 56 78", "job_title": "Head of Sales",
     "vertical": "SaaS", "status": "A prospecter", "source": "HubSpot"},
    {"id": 2, "first_name": "Julie", "last_name": "Durand", "company_name": "BankCo",
     "email": "julie@bank.fr", "phone": None, "job_title": "CFO",
     "vertical": "Finance", "status": "Intéressé", "source": None},
]


@pytest.mark.parametrize("kwargs, expected_ids", [
    ({}, [1, 2]),
    ({"query": "alpha"}, [1]),
    ({"query": "thomas martins"}, [1]),
    ({"query": "0612345678"}, [1]),
    ({"query": "cfo"}, [2]),
    ({"verticals": ["Finance"]}, [2]),
    ({"statuses": ["A prospecter"]}, [1]),
    ({"sources": ["HubSpot"]}, [1]),
    ({"query": "julie", "verticals": ["SaaS"]}, []),
])
def test_filter_prospects(kwargs, expected_ids):
    assert [p["id"] for p in service.filter_prospects(PROSPECTS, **kwargs)] == expected_ids


def test_read_csv_semicolon_french_headers_latin1():
    content = "Prénom;Nom;Entreprise;Téléphone;Colonne inconnue\nRené;Lefèvre;Société Générale;0611223344;x\n"

    df, ignored = service.read_prospect_csv(content.encode("latin-1"))

    assert list(df.columns) == ["first_name", "last_name", "company_name", "phone"]
    assert df.iloc[0]["first_name"] == "René"
    assert ignored == ["Colonne inconnue"]


def test_read_csv_hubspot_headers():
    content = "First Name,Last Name,Company Name,Email,Phone Number\nAna,Lopez,Acme,ana@acme.com,+34600000000\n"

    df, _ = service.read_prospect_csv(content.encode("utf-8"))

    assert set(df.columns) == {"first_name", "last_name", "company_name", "email", "phone"}


def test_read_csv_missing_required_column():
    with pytest.raises(ValueError, match="company_name"):
        service.read_prospect_csv(b"first_name,last_name\nA,B\n")


def test_read_csv_template_is_valid():
    df, ignored = service.read_prospect_csv(service.CSV_TEMPLATE.encode())
    assert len(df) == 1 and ignored == []


def test_import_report(thomas):
    content = (
        "first_name,last_name,company_name,email,phone\n"
        "Marie,Dupont,Exemple,marie@example.com,0611223344\n"   # ligne 2 : créée
        "Tom,M,AlphaEngine,THOMAS.MARTIN@example.com,\n"        # ligne 3 : doublon base (email)
        "Marie,Dupont,Exemple,,\n"                              # ligne 4 : doublon du fichier
        ",SansPrenom,Exemple,,\n"                               # ligne 5 : erreur
        "Paul,Bad,Exemple,pas-un-email,\n"                      # ligne 6 : erreur
    )

    df, _ = service.read_prospect_csv(content.encode())
    report = service.import_prospects(df, default_source="Test")

    assert report["created"] == 1
    assert [d["line"] for d in report["duplicates"]] == [3, 4]
    assert [e["line"] for e in report["errors"]] == [5, 6]

    marie = [p for p in database.get_all_prospects() if p["first_name"] == "Marie"][0]
    assert marie["source"] == "Test"
    assert marie["status"] == "A prospecter"
