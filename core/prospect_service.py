"""Service prospects : règles métier entre l'interface (main.py) et la base (database.py).

Contenu :
  - validation des données d'un prospect ;
  - détection des doublons (email, puis nom + prénom + entreprise) ;
  - création et modification avec ces contrôles ;
  - recherche et filtres ;
  - import CSV (lecture, reconnaissance des colonnes, rapport d'import).

Le téléphone n'est PAS utilisé seul pour bloquer un doublon : plusieurs
contacts d'une même entreprise peuvent partager un standard.
"""

import io
import re

import pandas as pd

import database
from core.deduplication import normalize_email, normalize_phone

# Étapes de prospection (cahier des charges). "A prospecter" est la valeur
# par défaut déjà utilisée dans la base : elle est conservée telle quelle.
STATUSES = [
    "A prospecter",
    "Première tentative",
    "En contact",
    "Intéressé",
    "Rendez-vous obtenu",
    "A relancer",
    "Non intéressé",
    "Disqualifié",
]

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Noms de colonnes CSV reconnus (en minuscules) pour chaque champ REVORA.
# Inclut les en-têtes d'un export HubSpot ("First Name", "Phone Number"...).
COLUMN_ALIASES = {
    "first_name": ["first_name", "first name", "firstname", "prenom", "prénom"],
    "last_name": ["last_name", "last name", "lastname", "nom"],
    "company_name": ["company_name", "company name", "company", "entreprise", "société", "societe"],
    "vertical": ["vertical", "verticale"],
    "email": ["email", "e-mail", "mail", "adresse email"],
    "phone": ["phone", "phone number", "telephone", "téléphone", "tel", "mobile"],
    "job_title": ["job_title", "job title", "poste", "fonction"],
    "status": ["status", "statut"],
    "source": ["source"],
    "owner": ["owner", "contact owner", "responsable", "commercial"],
}

REQUIRED_CSV_FIELDS = ["first_name", "last_name", "company_name"]

CSV_TEMPLATE = (
    "first_name,last_name,company_name,vertical,email,phone,job_title,status,source,owner\n"
    "Marie,Dupont,Exemple SAS,SaaS,marie.dupont@example.com,0611223344,CEO,A prospecter,Salon,\n"
)


# ==========================================
# VALIDATION ET DOUBLONS
# ==========================================

def validate_prospect(data):
    """Retourne la liste des erreurs (vide si les données sont valides).

    `data` est un dictionnaire avec les clés first_name, last_name,
    company_name, email, phone, status (les autres sont libres).
    """

    errors = []

    for field, label in [
        ("first_name", "Le prénom"),
        ("last_name", "Le nom"),
        ("company_name", "L'entreprise"),
    ]:
        if not (data.get(field) or "").strip():
            errors.append(f"{label} est obligatoire.")

    email = (data.get("email") or "").strip()
    if email and not EMAIL_PATTERN.match(email):
        errors.append(f"Email invalide : {email}")

    phone = (data.get("phone") or "").strip()
    if phone and normalize_phone(phone) is None:
        errors.append(f"Téléphone invalide : {phone}")

    status = (data.get("status") or "").strip()
    if status and status not in STATUSES:
        errors.append(f"Statut inconnu : {status}")

    return errors


def find_duplicate(data, prospects, exclude_id=None):
    """Cherche un prospect existant identique. Retourne (prospect, raison) ou (None, None).

    Règles, dans l'ordre :
      1. même email (sans tenir compte des majuscules) ;
      2. même prénom + nom + entreprise.
    """

    email = normalize_email(data.get("email"))
    identity = _identity(data.get("first_name"), data.get("last_name"), data.get("company_name"))

    for prospect in prospects:
        if prospect["id"] == exclude_id:
            continue

        if email and normalize_email(prospect.get("email")) == email:
            return prospect, "même email"

        if identity == _identity(
            prospect.get("first_name"), prospect.get("last_name"), prospect.get("company_name")
        ):
            return prospect, "même nom et même entreprise"

    return None, None


def _identity(first_name, last_name, company_name):
    return tuple((value or "").strip().lower() for value in (first_name, last_name, company_name))


# ==========================================
# CREATION ET MODIFICATION
# ==========================================

def create_prospect(data):
    """Valide puis crée un prospect. Retourne (succès, message)."""

    errors = validate_prospect(data)
    if errors:
        return False, " ".join(errors)

    duplicate, reason = find_duplicate(data, database.get_all_prospects())
    if duplicate:
        return False, (
            f"Doublon ({reason}) : {duplicate['first_name']} {duplicate['last_name']}"
            f" — {duplicate['company_name']}."
        )

    return database.create_prospect(
        data["first_name"],
        data["last_name"],
        data["company_name"],
        data.get("vertical"),
        data.get("email"),
        data.get("phone"),
        data.get("job_title"),
        status=data.get("status"),
        source=data.get("source"),
        owner=data.get("owner"),
    )


def update_prospect(contact_id, data):
    """Valide puis met à jour un prospect. Retourne (succès, message)."""

    errors = validate_prospect(data)
    if errors:
        return False, " ".join(errors)

    duplicate, reason = find_duplicate(data, database.get_all_prospects(), exclude_id=contact_id)
    if duplicate:
        return False, (
            f"Doublon ({reason}) : {duplicate['first_name']} {duplicate['last_name']}"
            f" — {duplicate['company_name']}."
        )

    return database.update_prospect(
        contact_id,
        data["first_name"],
        data["last_name"],
        data["company_name"],
        data.get("vertical"),
        data.get("email"),
        data.get("phone"),
        data.get("job_title"),
        data.get("status"),
        source=data.get("source"),
        owner=data.get("owner"),
    )


# ==========================================
# RECHERCHE ET FILTRES
# ==========================================

def filter_prospects(prospects, query="", verticals=None, statuses=None, sources=None):
    """Filtre une liste de prospects.

    query : texte cherché dans le nom, l'entreprise, l'email, le poste et le
            téléphone (le téléphone est comparé chiffres uniquement).
    verticals, statuses, sources : listes de valeurs acceptées (vide = tout).
    """

    query = (query or "").strip().lower()
    query_digits = re.sub(r"\D", "", query)

    results = []

    for prospect in prospects:
        if verticals and prospect.get("vertical") not in verticals:
            continue
        if statuses and prospect.get("status") not in statuses:
            continue
        if sources and prospect.get("source") not in sources:
            continue

        if query:
            text = " ".join(
                str(prospect.get(key) or "")
                for key in ("first_name", "last_name", "company_name", "email", "job_title")
            ).lower()
            full_name = f"{prospect.get('first_name') or ''} {prospect.get('last_name') or ''}".lower()
            phone_digits = re.sub(r"\D", "", prospect.get("phone") or "")

            matches = (
                query in text
                or query in full_name
                or (len(query_digits) >= 4 and query_digits in phone_digits)
            )

            if not matches:
                continue

        results.append(prospect)

    return results


# ==========================================
# IMPORT CSV
# ==========================================

def read_prospect_csv(file):
    """Lit un fichier CSV et renomme les colonnes reconnues.

    Accepte les séparateurs "," et ";" et les encodages UTF-8 / Latin-1
    (fréquent pour les CSV produits par Excel sur Mac ou Windows).

    Retourne (dataframe, colonnes_ignorées). Lève ValueError si le fichier
    est illisible ou si une colonne obligatoire manque.
    """

    raw = file.read() if hasattr(file, "read") else file

    if isinstance(raw, bytes):
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("latin-1")
    else:
        text = raw

    if not text.strip():
        raise ValueError("Le fichier est vide.")

    try:
        df = pd.read_csv(
            io.StringIO(text), sep=None, engine="python", dtype=str, keep_default_na=False
        )
    except Exception as error:
        raise ValueError(f"Fichier CSV illisible : {error}") from error

    alias_to_field = {
        alias: field for field, aliases in COLUMN_ALIASES.items() for alias in aliases
    }

    renames = {}
    ignored = []

    for column in df.columns:
        field = alias_to_field.get(str(column).strip().lower())
        if field and field not in renames.values():
            renames[column] = field
        else:
            ignored.append(column)

    df = df[list(renames)].rename(columns=renames)

    missing = [field for field in REQUIRED_CSV_FIELDS if field not in df.columns]
    if missing:
        raise ValueError(
            "Colonnes obligatoires manquantes : " + ", ".join(missing)
            + ". Téléchargez le modèle CSV pour voir le format attendu."
        )

    return df, ignored


def import_prospects(df, default_source="Import CSV"):
    """Importe les lignes d'un DataFrame (issu de read_prospect_csv).

    Chaque ligne est validée et contrôlée contre les doublons (base existante
    ET lignes déjà importées du même fichier). Aucune ligne existante n'est
    modifiée.

    Retourne un rapport : {"created": n, "duplicates": [...], "errors": [...]}.
    Les numéros de ligne correspondent à ceux du fichier (en-tête = ligne 1).
    """

    report = {"created": 0, "duplicates": [], "errors": []}

    for position, row in enumerate(df.to_dict("records")):
        line = position + 2
        data = {key: (value or "").strip() for key, value in row.items()}
        data["source"] = data.get("source") or default_source

        errors = validate_prospect(data)
        if errors:
            report["errors"].append({"line": line, "reason": " ".join(errors)})
            continue

        duplicate, reason = find_duplicate(data, database.get_all_prospects())
        if duplicate:
            report["duplicates"].append({
                "line": line,
                "reason": f"{reason} que {duplicate['first_name']} {duplicate['last_name']}",
            })
            continue

        created, message = create_prospect(data)

        if created:
            report["created"] += 1
        else:
            report["errors"].append({"line": line, "reason": message})

    return report
