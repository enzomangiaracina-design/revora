
import json
import sqlite3
from pathlib import Path


# ==========================================
# 1. CONFIGURATION DE LA BASE DE DONNEES
# ==========================================

BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "revora.db"

# Etapes de prospection creees au premier lancement (modifiables ensuite
# depuis la page Pipeline). "A prospecter" est la valeur par defaut deja
# utilisee dans la base : elle est conservee telle quelle.
DEFAULT_STAGES = [
    "A prospecter",
    "Première tentative",
    "En contact",
    "Intéressé",
    "Rendez-vous obtenu",
    "A relancer",
    "Non intéressé",
    "Disqualifié",
]

# Etapes "fermees" : le prospect n'est plus a travailler (exclu des priorites
# et de la detection d'inactivite).
DEFAULT_CLOSED_STAGES = {"Non intéressé", "Disqualifié"}

# Informations de qualification CONFIRMEES par le commercial (cases a cocher
# sur la fiche prospect). Elles alimentent l'Intent Score.
QUALIFICATION_FIELDS = [
    "need_identified",
    "is_decision_maker",
    "budget_confirmed",
    "demo_requested",
]


def get_connection():
    """Ouvre une connexion a la base SQLite."""

    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")

    return connection


# ==========================================
# 2. INITIALISATION DES TABLES
# ==========================================

def initialize_database():
    """Cree les tables de REVORA."""

    connection = get_connection()
    cursor = connection.cursor()

    # ENTREPRISES
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            vertical TEXT,
            website TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # CONTACTS
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id INTEGER,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            job_title TEXT,
            status TEXT DEFAULT 'A prospecter',
            hubspot_id TEXT UNIQUE,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (company_id)
                REFERENCES companies(id)
        )
    """)

    # INTERACTIONS : APPELS, EMAILS, NOTES
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS interactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id INTEGER NOT NULL,
            channel TEXT NOT NULL,
            direction TEXT,
            event_type TEXT NOT NULL,
            subject TEXT,
            content TEXT,
            outcome TEXT,
            occurred_at TEXT DEFAULT CURRENT_TIMESTAMP,
            provider TEXT,
            external_id TEXT,
            metadata TEXT,

            FOREIGN KEY (contact_id)
                REFERENCES contacts(id),

            UNIQUE(provider, external_id)
        )
    """)

    # HISTORIQUE DES SCORES
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id INTEGER NOT NULL,
            fit_score INTEGER DEFAULT 0,
            engagement_score INTEGER DEFAULT 0,
            intent_score INTEGER DEFAULT 0,
            global_score INTEGER DEFAULT 0,
            calculated_at TEXT DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (contact_id)
                REFERENCES contacts(id)
        )
    """)

    # TACHES ET RELANCES
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            due_at TEXT,
            status TEXT DEFAULT 'A faire',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (contact_id)
                REFERENCES contacts(id)
        )
    """)

    # INTEGRATIONS
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS integrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL UNIQUE,
            status TEXT DEFAULT 'Non connecte',
            last_sync_at TEXT,
            last_error TEXT
        )
    """)

    # ETAPES DU PIPELINE (personnalisables)
    # contacts.status contient le NOM de l'etape.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pipeline_stages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            position INTEGER NOT NULL,
            is_closed INTEGER NOT NULL DEFAULT 0
        )
    """)

    _seed_pipeline_stages(cursor)

    # JOURNAL DES SYNCHRONISATIONS (une ligne par execution d'un connecteur)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS integration_syncs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL,
            started_at TEXT DEFAULT CURRENT_TIMESTAMP,
            finished_at TEXT,
            status TEXT,
            fetched INTEGER DEFAULT 0,
            created INTEGER DEFAULT 0,
            duplicates INTEGER DEFAULT 0,
            unmatched INTEGER DEFAULT 0,
            errors INTEGER DEFAULT 0,
            message TEXT
        )
    """)

    # OBJECTIONS (phase 8) : uniquement des objections REELLEMENT exprimees.
    # stage = etape du pipeline au moment de l'objection (pour les statistiques).
    # source = "manual" (saisie du commercial) ; "ai" plus tard, toujours a confirmer.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS objections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id INTEGER NOT NULL,
            interaction_id INTEGER,
            category TEXT NOT NULL,
            verbatim TEXT,
            stage TEXT,
            status TEXT NOT NULL DEFAULT 'Open',
            source TEXT NOT NULL DEFAULT 'manual',
            occurred_at TEXT DEFAULT CURRENT_TIMESTAMP,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (contact_id) REFERENCES contacts(id),
            FOREIGN KEY (interaction_id) REFERENCES interactions(id)
        )
    """)

    # HISTORIQUE DES CHANGEMENTS D'ETAPE (P0.3) : chaque passage d'une etape a une
    # autre est enregistre, avec son origine (pipeline, modification, suppression d'etape).
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS stage_changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id INTEGER NOT NULL,
            from_stage TEXT,
            to_stage TEXT NOT NULL,
            source TEXT NOT NULL,
            changed_at TEXT DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (contact_id) REFERENCES contacts(id)
        )
    """)

    # « PAS MAINTENANT » (P1) : un prospect ecarte du Today's Focus jusqu'a une date,
    # par decision du commercial (corriger ou rejeter une priorite proposee).
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS focus_snoozes (
            contact_id INTEGER PRIMARY KEY,
            until TEXT NOT NULL,
            reason TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (contact_id) REFERENCES contacts(id)
        )
    """)

    # REPONSES RECOMMANDEES par categorie (redigees par le commercial)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS objection_responses (
            category TEXT PRIMARY KEY,
            response TEXT NOT NULL,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # REGLAGES (ex. configuration du scoring), stockes en JSON par cle
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # MIGRATIONS (phase 2) : ajout de colonnes sur une base existante,
    # sans toucher aux données déjà enregistrées.
    _add_column_if_missing(cursor, "contacts", "source", "TEXT")
    _add_column_if_missing(cursor, "contacts", "owner", "TEXT")
    _add_column_if_missing(cursor, "contacts", "updated_at", "TEXT")
    _add_column_if_missing(cursor, "companies", "industry", "TEXT")
    _add_column_if_missing(cursor, "companies", "size", "TEXT")
    _add_column_if_missing(cursor, "companies", "country", "TEXT")

    # MIGRATIONS (phase 5) : qualification confirmee par le commercial
    # (0 = non, 1 = oui) et explication des scores
    for column in QUALIFICATION_FIELDS:
        _add_column_if_missing(cursor, "contacts", column, "INTEGER DEFAULT 0")

    _add_column_if_missing(cursor, "scores", "explanation", "TEXT")

    # MIGRATION (phase 9) : URL du profil LinkedIn (saisie par le commercial)
    _add_column_if_missing(cursor, "contacts", "linkedin_url", "TEXT")
    # P2.4 : definition de chaque etape (critere d'entree), redigee par l'equipe
    _add_column_if_missing(cursor, "pipeline_stages", "definition", "TEXT")

    connection.commit()
    connection.close()

    print("REVORA database initialized successfully.")
    print(f"Database location: {DATABASE_PATH}")


def _seed_pipeline_stages(cursor):
    """Cree les etapes par defaut si la table est vide.

    Tout statut deja utilise par un prospect mais absent de la liste est
    ajoute a la fin : aucun prospect ne se retrouve sans etape.
    """

    if cursor.execute("SELECT count(*) FROM pipeline_stages").fetchone()[0] == 0:
        for position, name in enumerate(DEFAULT_STAGES):
            cursor.execute(
                "INSERT INTO pipeline_stages (name, position, is_closed) VALUES (?, ?, ?)",
                (name, position, int(name in DEFAULT_CLOSED_STAGES))
            )

    existing = {row[0] for row in cursor.execute("SELECT name FROM pipeline_stages")}
    used = [
        row[0] for row in cursor.execute(
            "SELECT DISTINCT status FROM contacts WHERE status IS NOT NULL AND status != ''"
        )
    ]

    for name in used:
        if name not in existing:
            cursor.execute(
                """
                INSERT INTO pipeline_stages (name, position)
                VALUES (?, (SELECT coalesce(max(position), -1) + 1 FROM pipeline_stages))
                """,
                (name,)
            )
            existing.add(name)


def _add_column_if_missing(cursor, table, column, column_type):
    """Ajoute une colonne a une table si elle n'existe pas encore.

    Concept : c'est une "migration". SQLite ne modifie pas une table deja
    creee avec CREATE TABLE IF NOT EXISTS ; on ajoute donc les nouvelles
    colonnes une par une avec ALTER TABLE. Les lignes existantes recoivent
    la valeur NULL dans la nouvelle colonne : aucune donnee n'est perdue.
    """

    columns = [row["name"] for row in cursor.execute(f"PRAGMA table_info({table})")]

    if column not in columns:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")


# ==========================================
# 3. CREATION DES PROSPECTS
# ==========================================

def _record_stage_change(connection, contact_id, from_stage, to_stage, source):
    """Ajoute une ligne a l'historique des etapes si l'etape change vraiment."""

    if from_stage != to_stage:
        connection.execute(
            "INSERT INTO stage_changes (contact_id, from_stage, to_stage, source) VALUES (?, ?, ?, ?)",
            (contact_id, from_stage, to_stage, source)
        )


# Valeur speciale : "argument non fourni" (different de None, qui veut dire "vide")
_UNCHANGED = object()


def _clean(value):
    """Retire les espaces autour d'un texte ; retourne None si le texte est vide."""

    if value is None:
        return None

    value = str(value).strip()

    return value or None


def _get_or_create_company(cursor, company_name, vertical):
    """Retourne l'id de l'entreprise (meme nom et meme verticale), en la creant si besoin."""

    vertical = _clean(vertical)

    # "IS" (et non "=") pour que deux verticales vides (NULL) soient considerees egales.
    # Le nom est compare en Python (_same_text) pour gerer les accents.
    candidates = cursor.execute(
        "SELECT id, name FROM companies WHERE vertical IS ? ORDER BY id",
        (vertical,)
    ).fetchall()

    for company in candidates:
        if _same_text(company["name"], company_name):
            return company["id"]

    cursor.execute(
        """
        INSERT INTO companies (name, vertical)
        VALUES (?, ?)
        """,
        (company_name.strip(), vertical)
    )

    return cursor.lastrowid


def create_prospect(
    first_name,
    last_name,
    company_name,
    vertical,
    email,
    phone,
    job_title,
    status=None,
    source=None,
    owner=None,
    hubspot_id=None,
    linkedin_url=None
):
    """Cree une entreprise si necessaire et un prospect.

    status, source, owner, hubspot_id et linkedin_url sont optionnels :
    les appels existants (7 arguments) continuent de fonctionner.
    """

    connection = get_connection()

    try:
        cursor = connection.cursor()

        company_id = _get_or_create_company(cursor, company_name, vertical)

        # Verification de l'email
        if email and email.strip():

            cursor.execute(
                """
                SELECT id FROM contacts
                WHERE lower(email) = lower(?)
                """,
                (email.strip(),)
            )

            existing_contact = cursor.fetchone()

            if existing_contact:
                return False, "Cet email existe deja dans REVORA."

        # Creation du prospect
        cursor.execute(
            """
            INSERT INTO contacts (
                company_id,
                first_name,
                last_name,
                email,
                phone,
                job_title,
                status,
                source,
                owner,
                hubspot_id,
                linkedin_url
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                company_id,
                first_name.strip(),
                last_name.strip(),
                _clean(email),
                _clean(phone),
                _clean(job_title),
                _clean(status) or "A prospecter",
                _clean(source),
                _clean(owner),
                _clean(hubspot_id),
                _clean(linkedin_url)
            )
        )

        connection.commit()

        return True, "Prospect enregistre avec succes."

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


# ==========================================
# 4. RECUPERATION DE TOUS LES PROSPECTS
# ==========================================

def get_all_prospects():
    """Recupere tous les prospects avec leur entreprise."""

    connection = get_connection()

    prospects = connection.execute(
        """
        SELECT
            contacts.id,
            contacts.first_name,
            contacts.last_name,
            contacts.email,
            contacts.phone,
            contacts.job_title,
            contacts.status,
            contacts.source,
            contacts.owner,
            contacts.hubspot_id,
            contacts.linkedin_url,
            contacts.created_at,
            datetime(contacts.created_at, 'localtime') AS created_at_local,
            contacts.need_identified,
            contacts.is_decision_maker,
            contacts.budget_confirmed,
            contacts.demo_requested,
            companies.name AS company_name,
            companies.vertical
        FROM contacts

        LEFT JOIN companies
            ON contacts.company_id = companies.id

        ORDER BY contacts.created_at DESC
        """
    ).fetchall()

    connection.close()

    return [dict(prospect) for prospect in prospects]


def get_verticals():
    """Liste des verticales deja utilisees, triees par ordre alphabetique."""

    connection = get_connection()

    rows = connection.execute(
        """
        SELECT DISTINCT vertical
        FROM companies
        WHERE vertical IS NOT NULL AND vertical != ''
        ORDER BY vertical
        """
    ).fetchall()

    connection.close()

    return [row["vertical"] for row in rows]


# ==========================================
# 5. FICHE INDIVIDUELLE DU PROSPECT
# ==========================================

def get_prospect_by_id(contact_id):
    """Recupere les informations completes d'un prospect."""

    connection = get_connection()

    prospect = connection.execute(
        """
        SELECT
            contacts.*,
            datetime(contacts.created_at, 'localtime') AS created_at_local,
            companies.name AS company_name,
            companies.vertical
        FROM contacts

        LEFT JOIN companies
            ON contacts.company_id = companies.id

        WHERE contacts.id = ?
        """,
        (contact_id,)
    ).fetchone()

    connection.close()

    return dict(prospect) if prospect else None


# ==========================================
# 5 bis. MODIFICATION ET SUPPRESSION
# ==========================================

def update_prospect(
    contact_id,
    first_name,
    last_name,
    company_name,
    vertical,
    email,
    phone,
    job_title,
    status,
    source=None,
    owner=None,
    linkedin_url=_UNCHANGED
):
    """Met a jour un prospect. Retourne (succes, message).

    linkedin_url : si l'argument n'est pas fourni, l'URL existante est
    conservee (les appels plus anciens ne l'effacent pas).
    """

    connection = get_connection()

    try:
        cursor = connection.cursor()

        # L'email ne doit pas appartenir a un AUTRE contact
        if _clean(email):
            cursor.execute(
                """
                SELECT id FROM contacts
                WHERE lower(email) = lower(?) AND id != ?
                """,
                (email.strip(), contact_id)
            )

            if cursor.fetchone():
                return False, "Cet email existe deja dans REVORA."

        company_id = _get_or_create_company(cursor, company_name, vertical)

        previous = cursor.execute(
            "SELECT status FROM contacts WHERE id = ?", (contact_id,)
        ).fetchone()

        cursor.execute(
            """
            UPDATE contacts
            SET company_id = ?,
                first_name = ?,
                last_name = ?,
                email = ?,
                phone = ?,
                job_title = ?,
                status = ?,
                source = ?,
                owner = ?,
                linkedin_url = CASE WHEN ? THEN ? ELSE linkedin_url END,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                company_id,
                first_name.strip(),
                last_name.strip(),
                _clean(email),
                _clean(phone),
                _clean(job_title),
                _clean(status) or "A prospecter",
                _clean(source),
                _clean(owner),
                int(linkedin_url is not _UNCHANGED),
                None if linkedin_url is _UNCHANGED else _clean(linkedin_url),
                contact_id
            )
        )

        if cursor.rowcount == 0:
            return False, "Prospect introuvable."

        _record_stage_change(
            connection, contact_id, previous["status"], _clean(status) or "A prospecter", "edit"
        )

        connection.commit()

        return True, "Prospect mis a jour."

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def count_prospect_activity(contact_id):
    """Compte ce qui est rattache a un prospect (affiche avant une suppression)."""

    connection = get_connection()

    counts = {
        table: connection.execute(
            f"SELECT count(*) FROM {table} WHERE contact_id = ?",
            (contact_id,)
        ).fetchone()[0]
        for table in ("interactions", "tasks", "scores", "objections")
    }

    connection.close()

    return counts


def delete_prospect(contact_id):
    """Supprime DEFINITIVEMENT un prospect et tout ce qui lui est rattache.

    Concept : une "transaction". Les quatre suppressions sont validees
    ensemble par commit(), ou annulees ensemble par rollback() en cas
    d'erreur : on ne peut pas se retrouver avec des interactions orphelines.
    L'entreprise est conservee (d'autres contacts peuvent y etre rattaches).

    Retourne le nombre d'elements supprimes par table.
    """

    connection = get_connection()

    try:
        deleted = {}

        # Les objections d'abord : elles referencent les interactions
        for table in ("objections", "interactions", "tasks", "scores", "stage_changes", "focus_snoozes"):
            deleted[table] = connection.execute(
                f"DELETE FROM {table} WHERE contact_id = ?",
                (contact_id,)
            ).rowcount

        deleted["contacts"] = connection.execute(
            "DELETE FROM contacts WHERE id = ?",
            (contact_id,)
        ).rowcount

        connection.commit()

        return deleted

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


# ==========================================
# 5 ter. ETAPES DU PIPELINE
# ==========================================

def get_stages():
    """Etapes du pipeline, dans l'ordre d'affichage."""

    connection = get_connection()

    rows = connection.execute(
        "SELECT id, name, position, is_closed, definition FROM pipeline_stages ORDER BY position, id"
    ).fetchall()

    connection.close()

    return [dict(row) | {"is_closed": bool(row["is_closed"])} for row in rows]


def get_stage_names():
    """Noms des etapes, dans l'ordre."""

    return [stage["name"] for stage in get_stages()]


def _same_text(a, b):
    """Compare deux textes sans tenir compte des majuscules, accents compris.

    Concept : lower() de SQLite ne convertit que les lettres sans accent
    ("É" reste "É"). La comparaison se fait donc en Python avec casefold(),
    qui gere toutes les lettres ("SOCIÉTÉ" == "société").
    """

    return (a or "").strip().casefold() == (b or "").strip().casefold()


def _stage_name_taken(connection, name, exclude_id=None):
    return any(
        _same_text(row["name"], name)
        for row in connection.execute(
            "SELECT name FROM pipeline_stages WHERE id IS NOT ?", (exclude_id,)
        )
    )


def add_stage(name, is_closed=False):
    """Ajoute une etape a la fin du pipeline. Retourne (succes, message)."""

    name = _clean(name)

    if not name:
        return False, "Le nom de l'etape est obligatoire."

    connection = get_connection()

    try:
        if _stage_name_taken(connection, name):
            return False, f"L'etape « {name} » existe deja."

        connection.execute(
            """
            INSERT INTO pipeline_stages (name, position, is_closed)
            VALUES (?, (SELECT coalesce(max(position), -1) + 1 FROM pipeline_stages), ?)
            """,
            (name, int(is_closed))
        )

        connection.commit()

        return True, f"Etape « {name} » ajoutee."

    finally:
        connection.close()


def rename_stage(stage_id, new_name):
    """Renomme une etape ET met a jour les prospects qui y sont (transaction)."""

    new_name = _clean(new_name)

    if not new_name:
        return False, "Le nom de l'etape est obligatoire."

    connection = get_connection()

    try:
        stage = connection.execute(
            "SELECT name FROM pipeline_stages WHERE id = ?", (stage_id,)
        ).fetchone()

        if not stage:
            return False, "Etape introuvable."

        if _stage_name_taken(connection, new_name, exclude_id=stage_id):
            return False, f"L'etape « {new_name} » existe deja."

        connection.execute(
            "UPDATE contacts SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE status = ?",
            (new_name, stage["name"])
        )
        connection.execute(
            "UPDATE pipeline_stages SET name = ? WHERE id = ?",
            (new_name, stage_id)
        )

        connection.commit()

        return True, f"Etape renommee en « {new_name} »."

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def move_stage(stage_id, step):
    """Deplace une etape d'un cran (step = -1 vers la gauche, +1 vers la droite)."""

    stages = get_stages()
    index = next((i for i, s in enumerate(stages) if s["id"] == stage_id), None)

    if index is None or not 0 <= index + step < len(stages):
        return False

    # On renumerote toutes les positions (0, 1, 2...) apres l'echange
    stages[index], stages[index + step] = stages[index + step], stages[index]

    connection = get_connection()

    try:
        for position, stage in enumerate(stages):
            connection.execute(
                "UPDATE pipeline_stages SET position = ? WHERE id = ?",
                (position, stage["id"])
            )

        connection.commit()

        return True

    finally:
        connection.close()


def set_stage_closed(stage_id, is_closed):
    """Marque une etape comme fermee (prospect plus a travailler) ou ouverte."""

    connection = get_connection()

    try:
        connection.execute(
            "UPDATE pipeline_stages SET is_closed = ? WHERE id = ?",
            (int(is_closed), stage_id)
        )
        connection.commit()

    finally:
        connection.close()


def delete_stage(stage_id, move_to=None):
    """Supprime une etape. Ses prospects sont d'abord deplaces vers `move_to`.

    Refuse si l'etape contient des prospects et qu'aucune etape de
    destination n'est donnee, ou s'il s'agit de la derniere etape.
    Retourne (succes, message).
    """

    connection = get_connection()

    try:
        stage = connection.execute(
            "SELECT name FROM pipeline_stages WHERE id = ?", (stage_id,)
        ).fetchone()

        if not stage:
            return False, "Etape introuvable."

        if connection.execute("SELECT count(*) FROM pipeline_stages").fetchone()[0] <= 1:
            return False, "Le pipeline doit garder au moins une etape."

        count = connection.execute(
            "SELECT count(*) FROM contacts WHERE status = ?", (stage["name"],)
        ).fetchone()[0]

        if count:
            target = connection.execute(
                "SELECT name FROM pipeline_stages WHERE name = ? AND id != ?",
                (move_to, stage_id)
            ).fetchone()

            if not target:
                return False, (
                    f"{count} prospect(s) sont dans « {stage['name']} » : "
                    "choisissez une etape de destination."
                )

            moved = [
                row["id"] for row in connection.execute(
                    "SELECT id FROM contacts WHERE status = ?", (stage["name"],)
                )
            ]

            connection.execute(
                "UPDATE contacts SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE status = ?",
                (target["name"], stage["name"])
            )

            for contact_id in moved:
                _record_stage_change(
                    connection, contact_id, stage["name"], target["name"], "stage deleted"
                )

        connection.execute("DELETE FROM pipeline_stages WHERE id = ?", (stage_id,))

        connection.commit()

        return True, f"Etape « {stage['name']} » supprimee."

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def set_stage_definition(stage_id, definition):
    """Enregistre la definition d'une etape (texte libre, vide = aucune)."""

    connection = get_connection()

    try:
        connection.execute(
            "UPDATE pipeline_stages SET definition = ? WHERE id = ?", (_clean(definition), stage_id)
        )
        connection.commit()

    finally:
        connection.close()


def set_prospect_stage(contact_id, stage_name):
    """Deplace un prospect dans une etape du pipeline. Retourne (succes, message)."""

    connection = get_connection()

    try:
        if not connection.execute(
            "SELECT 1 FROM pipeline_stages WHERE name = ?", (stage_name,)
        ).fetchone():
            return False, f"Etape inconnue : {stage_name}"

        current = connection.execute(
            "SELECT status FROM contacts WHERE id = ?", (contact_id,)
        ).fetchone()

        if not current:
            return False, "Prospect introuvable."

        connection.execute(
            "UPDATE contacts SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (stage_name, contact_id)
        )
        _record_stage_change(connection, contact_id, current["status"], stage_name, "pipeline")

        connection.commit()

        return True, f"Prospect deplace vers « {stage_name} »."

    finally:
        connection.close()


# ==========================================
# 5 quater. QUALIFICATION, REGLAGES ET SCORES
# ==========================================

def update_qualification(contact_id, values):
    """Enregistre la qualification confirmee d'un prospect.

    values : {"need_identified": True, "budget_confirmed": False, ...}.
    Les cles inconnues sont ignorees.
    """

    fields = [field for field in QUALIFICATION_FIELDS if field in values]

    if not fields:
        return False

    connection = get_connection()

    try:
        connection.execute(
            f"""
            UPDATE contacts
            SET {', '.join(f'{field} = ?' for field in fields)},
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            [int(bool(values[field])) for field in fields] + [contact_id]
        )

        connection.commit()

        return True

    finally:
        connection.close()


def get_setting(key, default=None):
    """Lit un reglage (valeur JSON). Retourne `default` s'il n'existe pas."""

    connection = get_connection()
    row = connection.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    connection.close()

    return json.loads(row["value"]) if row else default


def set_setting(key, value):
    """Enregistre (ou remplace) un reglage au format JSON."""

    connection = get_connection()

    try:
        connection.execute(
            """
            INSERT INTO settings (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
            """,
            (key, json.dumps(value, ensure_ascii=False))
        )

        connection.commit()

    finally:
        connection.close()


def _score_row(row):
    item = dict(row)

    try:
        item["explanation"] = json.loads(item["explanation"]) if item.get("explanation") else []
    except (TypeError, ValueError):
        item["explanation"] = []

    return item


def get_latest_scores():
    """Dernier score enregistre de chaque prospect : {contact_id: {...}}."""

    connection = get_connection()

    rows = connection.execute(
        """
        SELECT
            scores.*,
            datetime(scores.calculated_at, 'localtime') AS calculated_at_local
        FROM scores

        WHERE scores.id = (
            SELECT max(s.id) FROM scores s WHERE s.contact_id = scores.contact_id
        )
        """
    ).fetchall()

    connection.close()

    return {row["contact_id"]: _score_row(row) for row in rows}


def get_score_history(contact_id):
    """Historique des scores d'un prospect, du plus ancien au plus recent."""

    connection = get_connection()

    rows = connection.execute(
        """
        SELECT
            *,
            datetime(calculated_at, 'localtime') AS calculated_at_local
        FROM scores
        WHERE contact_id = ?
        ORDER BY id
        """,
        (contact_id,)
    ).fetchall()

    connection.close()

    return [_score_row(row) for row in rows]


def get_recent_score_changes(limit=20, min_change=5):
    """Dernieres variations notables du score global, tous prospects confondus.

    Concept : LAG() est une "fonction de fenetre" SQL. Pour chaque ligne,
    elle lit la valeur de la ligne precedente du meme prospect : on obtient
    ainsi l'ancien et le nouveau score sur une seule ligne.

    min_change : ecart minimal (en points) pour ignorer les petites
    variations dues au vieillissement des signaux.
    """

    connection = get_connection()

    rows = connection.execute(
        """
        SELECT * FROM (
            SELECT
                scores.contact_id,
                datetime(scores.calculated_at, 'localtime') AS occurred_at_local,
                scores.global_score,
                LAG(scores.global_score) OVER (
                    PARTITION BY scores.contact_id ORDER BY scores.id
                ) AS previous_score
            FROM scores
        )
        WHERE previous_score IS NOT NULL
          AND abs(global_score - previous_score) >= ?
        ORDER BY occurred_at_local DESC
        LIMIT ?
        """,
        (min_change, limit)
    ).fetchall()

    connection.close()

    return [dict(row) for row in rows]


def save_score(contact_id, fit, engagement, intent, global_score, explanation):
    """Ajoute un point a l'historique SEULEMENT si un score a change.

    Concept : on n'ecrit pas une ligne a chaque affichage de la page.
    L'historique ne contient donc que de vraies variations.
    Retourne True si une nouvelle ligne a ete enregistree.
    """

    connection = get_connection()

    try:
        last = connection.execute(
            """
            SELECT fit_score, engagement_score, intent_score, global_score
            FROM scores WHERE contact_id = ?
            ORDER BY id DESC LIMIT 1
            """,
            (contact_id,)
        ).fetchone()

        if last and tuple(last) == (fit, engagement, intent, global_score):
            return False

        connection.execute(
            """
            INSERT INTO scores (
                contact_id, fit_score, engagement_score, intent_score,
                global_score, explanation
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                contact_id, fit, engagement, intent, global_score,
                json.dumps(explanation, ensure_ascii=False)
            )
        )

        connection.commit()

        return True

    finally:
        connection.close()


# ==========================================
# 5 sexies. OBJECTIONS
# ==========================================

def add_objection(contact_id, category, verbatim=None, *, interaction_id=None,
                  occurred_at=None, source="manual"):
    """Enregistre une objection exprimee par un prospect.

    L'etape actuelle du prospect est memorisee avec l'objection.
    occurred_at : date et heure LOCALES ("AAAA-MM-JJ HH:MM:SS"), absentes = maintenant.
    Retourne l'identifiant de l'objection.
    """

    connection = get_connection()

    try:
        stage = connection.execute(
            "SELECT status FROM contacts WHERE id = ?", (contact_id,)
        ).fetchone()

        if not stage:
            raise ValueError("Prospect introuvable.")

        cursor = connection.execute(
            """
            INSERT INTO objections (
                contact_id, interaction_id, category, verbatim, stage, source, occurred_at
            )
            VALUES (?, ?, ?, ?, ?, ?, COALESCE(datetime(?, 'utc'), CURRENT_TIMESTAMP))
            """,
            (
                contact_id, interaction_id, category.strip(), _clean(verbatim),
                stage["status"], source, occurred_at
            )
        )

        connection.commit()

        return cursor.lastrowid

    finally:
        connection.close()


def get_objections(contact_id=None):
    """Objections (toutes, ou celles d'un prospect), les plus recentes d'abord.

    Chaque ligne contient aussi le prospect, l'entreprise et la verticale.
    """

    query = """
        SELECT
            objections.*,
            datetime(objections.occurred_at, 'localtime') AS occurred_at_local,
            contacts.first_name,
            contacts.last_name,
            contacts.email,
            contacts.phone,
            companies.name AS company_name,
            companies.vertical,
            interactions.channel AS interaction_channel,
            interactions.subject AS interaction_subject,
            datetime(interactions.occurred_at, 'localtime') AS interaction_at_local
        FROM objections

        JOIN contacts
            ON objections.contact_id = contacts.id

        LEFT JOIN companies
            ON contacts.company_id = companies.id

        -- P2 : l'echange au cours duquel l'objection a ete exprimee (s'il est connu)
        LEFT JOIN interactions
            ON objections.interaction_id = interactions.id
    """

    params = ()

    if contact_id is not None:
        query += " WHERE objections.contact_id = ?"
        params = (contact_id,)

    query += " ORDER BY objections.occurred_at DESC, objections.id DESC"

    connection = get_connection()
    rows = connection.execute(query, params).fetchall()
    connection.close()

    return [dict(row) for row in rows]


def set_objection_status(objection_id, status):
    """Met a jour le statut d'une objection (Open / Handled / Lost)."""

    connection = get_connection()

    try:
        connection.execute(
            "UPDATE objections SET status = ? WHERE id = ?", (status, objection_id)
        )
        connection.commit()

    finally:
        connection.close()


def set_objection_category(objection_id, category):
    """Corrige la categorie d'une objection (P2). Retourne True si elle existait."""

    connection = get_connection()

    try:
        cursor = connection.execute(
            "UPDATE objections SET category = ? WHERE id = ?", (category.strip(), objection_id)
        )
        connection.commit()

        return cursor.rowcount == 1

    finally:
        connection.close()


def delete_objection(objection_id):
    """Supprime une objection saisie par erreur."""

    connection = get_connection()

    try:
        connection.execute("DELETE FROM objections WHERE id = ?", (objection_id,))
        connection.commit()

    finally:
        connection.close()


def get_objection_responses():
    """Reponses recommandees : {categorie: texte}."""

    connection = get_connection()
    rows = connection.execute("SELECT category, response FROM objection_responses").fetchall()
    connection.close()

    return {row["category"]: row["response"] for row in rows}


def set_objection_response(category, response):
    """Enregistre (ou efface si vide) la reponse recommandee d'une categorie."""

    connection = get_connection()

    try:
        if _clean(response):
            connection.execute(
                """
                INSERT INTO objection_responses (category, response, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(category) DO UPDATE SET
                    response = excluded.response,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (category, response.strip())
            )
        else:
            connection.execute("DELETE FROM objection_responses WHERE category = ?", (category,))

        connection.commit()

    finally:
        connection.close()


# ==========================================
# 5 quinquies. INTEGRATIONS ET SYNCHRONISATIONS
# ==========================================

def add_external_interaction(
    contact_id,
    provider,
    external_id,
    channel,
    direction,
    event_type,
    occurred_at_utc,
    subject=None,
    content=None,
    metadata=None
):
    """Enregistre une interaction venant d'un outil externe (HubSpot, Gmail...).

    occurred_at_utc : "AAAA-MM-JJ HH:MM:SS" en UTC.

    Concept : "idempotence". Recevoir deux fois le meme evenement ne doit
    pas creer deux lignes. La contrainte UNIQUE(provider, external_id) de la
    table interactions, combinee a INSERT OR IGNORE, garantit qu'une
    synchronisation relancee n'ajoute jamais de doublon.

    Retourne True si une ligne a ete ajoutee, False si elle existait deja.
    """

    connection = get_connection()

    try:
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO interactions (
                contact_id, channel, direction, event_type, subject, content,
                outcome, occurred_at, provider, external_id, metadata
            )
            VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?)
            """,
            (
                contact_id, channel, direction, event_type, subject, content,
                occurred_at_utc, provider, external_id,
                json.dumps(metadata, ensure_ascii=False) if metadata else None
            )
        )

        connection.commit()

        return cursor.rowcount == 1

    finally:
        connection.close()


def set_hubspot_id(contact_id, hubspot_id):
    """Rattache un prospect REVORA a son identifiant HubSpot."""

    connection = get_connection()

    try:
        connection.execute(
            "UPDATE contacts SET hubspot_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (hubspot_id, contact_id)
        )
        connection.commit()

    finally:
        connection.close()


def set_integration_status(provider, status, last_error=None, synced=False):
    """Met a jour l'etat d'une integration (creee si besoin)."""

    connection = get_connection()

    try:
        connection.execute(
            """
            INSERT INTO integrations (provider, status, last_error, last_sync_at)
            VALUES (?, ?, ?, CASE WHEN ? THEN CURRENT_TIMESTAMP END)
            ON CONFLICT(provider) DO UPDATE SET
                status = excluded.status,
                last_error = excluded.last_error,
                last_sync_at = CASE WHEN ? THEN CURRENT_TIMESTAMP ELSE last_sync_at END
            """,
            (provider, status, last_error, int(synced), int(synced))
        )
        connection.commit()

    finally:
        connection.close()


def get_integrations():
    """Etat des integrations : {provider: {...}} (heures locales)."""

    connection = get_connection()

    rows = connection.execute(
        """
        SELECT provider, status, last_error,
               datetime(last_sync_at, 'localtime') AS last_sync_at
        FROM integrations
        """
    ).fetchall()

    connection.close()

    return {row["provider"]: dict(row) for row in rows}


def log_sync(provider, status, counts, message=None):
    """Ajoute une ligne au journal des synchronisations."""

    connection = get_connection()

    try:
        connection.execute(
            """
            INSERT INTO integration_syncs (
                provider, finished_at, status, fetched, created,
                duplicates, unmatched, errors, message
            )
            VALUES (?, CURRENT_TIMESTAMP, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                provider, status,
                counts.get("fetched", 0), counts.get("created", 0),
                counts.get("duplicates", 0), counts.get("unmatched", 0),
                counts.get("errors", 0), message
            )
        )
        connection.commit()

    finally:
        connection.close()


def get_sync_logs(limit=20):
    """Dernieres synchronisations, de la plus recente a la plus ancienne."""

    connection = get_connection()

    rows = connection.execute(
        """
        SELECT *, datetime(started_at, 'localtime') AS started_at_local
        FROM integration_syncs
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,)
    ).fetchall()

    connection.close()

    return [dict(row) for row in rows]


# ==========================================
# 6. ENREGISTREMENT DES INTERACTIONS
# ==========================================

def add_interaction(
    contact_id,
    channel,
    direction,
    event_type,
    subject,
    content,
    outcome,
    occurred_at=None,
    metadata=None
):
    """Enregistre un appel, un email, un message LinkedIn ou une note.

    occurred_at : date et heure LOCALES ("2026-11-14 15:30:00"), optionnelles.
                  Absentes = maintenant.
    metadata    : dictionnaire optionnel (ex. {"duration_seconds": 300}),
                  stocke au format JSON.

    Concept (fuseaux horaires) : la base stocke toutes les heures en UTC,
    l'heure universelle. C'est ce que fait deja CURRENT_TIMESTAMP. Une heure
    locale saisie par l'utilisateur est donc convertie en UTC avec
    datetime(?, 'utc'), puis reconvertie en heure locale a l'affichage.
    """

    connection = get_connection()

    try:
        cursor = connection.execute(
            """
            INSERT INTO interactions (
                contact_id,
                channel,
                direction,
                event_type,
                subject,
                content,
                outcome,
                occurred_at,
                metadata,
                provider
            )
            VALUES (?, ?, ?, ?, ?, ?, ?,
                    COALESCE(datetime(?, 'utc'), CURRENT_TIMESTAMP),
                    ?, ?)
            """,
            (
                contact_id,
                channel,
                direction,
                event_type,
                subject,
                content,
                outcome,
                occurred_at,
                json.dumps(metadata) if metadata else None,
                "manual"
            )
        )

        connection.commit()

        # Identifiant de l'interaction creee (vrai, comme avant : >= 1)
        return cursor.lastrowid

    finally:
        connection.close()


# Seules les saisies manuelles sont modifiables : une interaction synchronisee
# (HubSpot, Gmail) appartient a sa source et serait recreee a la synchro suivante.
_MANUAL = "(provider = 'manual' OR provider IS NULL)"


def get_interaction(interaction_id):
    """Une interaction (avec son heure locale), ou None."""

    connection = get_connection()
    row = connection.execute(
        "SELECT *, datetime(occurred_at, 'localtime') AS occurred_at_local FROM interactions WHERE id = ?",
        (interaction_id,)
    ).fetchone()
    connection.close()

    return _with_metadata(row) if row else None


def update_interaction(interaction_id, channel, direction, event_type, subject, content, outcome,
                       occurred_at, metadata=None):
    """Corrige une interaction saisie a la main. Retourne True si elle a ete modifiee.

    occurred_at : date et heure LOCALES ("AAAA-MM-JJ HH:MM:SS").
    """

    connection = get_connection()

    try:
        cursor = connection.execute(
            f"""
            UPDATE interactions
            SET channel = ?, direction = ?, event_type = ?, subject = ?, content = ?,
                outcome = ?, occurred_at = datetime(?, 'utc'), metadata = ?
            WHERE id = ? AND {_MANUAL}
            """,
            (channel, direction, event_type, subject, content, outcome, occurred_at,
             json.dumps(metadata) if metadata else None, interaction_id)
        )
        connection.commit()

        return cursor.rowcount == 1

    finally:
        connection.close()


def delete_interaction(interaction_id):
    """Supprime une interaction saisie par erreur (saisie manuelle uniquement).

    Les objections notees pendant cet echange sont CONSERVEES (elles ont ete
    reellement exprimees) : elles perdent seulement leur lien vers l'echange.
    Retourne {"deleted": bool, "objections_unlinked": n}.
    """

    connection = get_connection()

    try:
        if not connection.execute(
            f"SELECT 1 FROM interactions WHERE id = ? AND {_MANUAL}", (interaction_id,)
        ).fetchone():
            return {"deleted": False, "objections_unlinked": 0}

        unlinked = connection.execute(
            "UPDATE objections SET interaction_id = NULL WHERE interaction_id = ?", (interaction_id,)
        ).rowcount
        connection.execute("DELETE FROM interactions WHERE id = ?", (interaction_id,))
        connection.commit()

        return {"deleted": True, "objections_unlinked": unlinked}

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


# ==========================================
# 7. HISTORIQUE DES INTERACTIONS
# ==========================================

def get_interactions(contact_id):
    """Recupere les interactions d'un prospect."""

    connection = get_connection()

    interactions = connection.execute(
        """
        SELECT
            *,
            datetime(occurred_at, 'localtime') AS occurred_at_local
        FROM interactions

        WHERE contact_id = ?

        ORDER BY occurred_at DESC, id DESC
        """,
        (contact_id,)
    ).fetchall()

    connection.close()

    return [_with_metadata(item) for item in interactions]


def _with_metadata(row):
    """Convertit une ligne en dictionnaire et decode la colonne metadata (JSON)."""

    item = dict(row)

    try:
        item["metadata"] = json.loads(item["metadata"]) if item.get("metadata") else {}
    except (TypeError, ValueError):
        item["metadata"] = {}

    return item


def get_all_interactions(channels=None, start_date=None, end_date=None):
    """Toutes les interactions, avec le nom du prospect et de l'entreprise.

    channels   : liste de canaux a garder (None = tous).
    start_date, end_date : dates LOCALES "AAAA-MM-JJ" incluses (None = sans limite).
    """

    query = """
        SELECT
            interactions.*,
            datetime(interactions.occurred_at, 'localtime') AS occurred_at_local,
            contacts.first_name,
            contacts.last_name,
            companies.name AS company_name
        FROM interactions

        JOIN contacts
            ON interactions.contact_id = contacts.id

        LEFT JOIN companies
            ON contacts.company_id = companies.id

        WHERE 1 = 1
    """

    params = []

    if channels:
        query += f" AND interactions.channel IN ({', '.join('?' for _ in channels)})"
        params.extend(channels)

    if start_date:
        query += " AND date(interactions.occurred_at, 'localtime') >= ?"
        params.append(start_date)

    if end_date:
        query += " AND date(interactions.occurred_at, 'localtime') <= ?"
        params.append(end_date)

    query += " ORDER BY interactions.occurred_at DESC, interactions.id DESC"

    connection = get_connection()
    rows = connection.execute(query, params).fetchall()
    connection.close()

    return [_with_metadata(row) for row in rows]


def get_activity_summary():
    """Compteurs automatiques par prospect.

    Retourne un dictionnaire {contact_id: {...}} avec le nombre d'appels,
    d'emails, de messages LinkedIn et de notes, la date de la derniere
    interaction (heure locale) et la prochaine relance ouverte.
    """

    connection = get_connection()

    rows = connection.execute(
        """
        SELECT
            contacts.id AS contact_id,

            (SELECT count(*) FROM interactions i
             WHERE i.contact_id = contacts.id AND i.channel = 'Call') AS calls,

            (SELECT count(*) FROM interactions i
             WHERE i.contact_id = contacts.id AND i.channel = 'Email') AS emails,

            (SELECT count(*) FROM interactions i
             WHERE i.contact_id = contacts.id AND i.channel = 'LinkedIn') AS linkedin,

            (SELECT count(*) FROM interactions i
             WHERE i.contact_id = contacts.id AND i.channel = 'Note') AS notes,

            (SELECT datetime(max(i.occurred_at), 'localtime') FROM interactions i
             WHERE i.contact_id = contacts.id) AS last_interaction_at,

            (SELECT t.due_at FROM tasks t
             WHERE t.contact_id = contacts.id AND t.status = 'A faire'
             ORDER BY t.due_at IS NULL, t.due_at LIMIT 1) AS next_task_due,

            (SELECT t.title FROM tasks t
             WHERE t.contact_id = contacts.id AND t.status = 'A faire'
             ORDER BY t.due_at IS NULL, t.due_at LIMIT 1) AS next_task_title,

            (SELECT t.id FROM tasks t
             WHERE t.contact_id = contacts.id AND t.status = 'A faire'
             ORDER BY t.due_at IS NULL, t.due_at LIMIT 1) AS next_task_id,

            (SELECT datetime(t.created_at, 'localtime') FROM tasks t
             WHERE t.contact_id = contacts.id AND t.status = 'A faire'
             ORDER BY t.due_at IS NULL, t.due_at LIMIT 1) AS next_task_created_at,

            (SELECT i.channel FROM interactions i
             WHERE i.contact_id = contacts.id
             ORDER BY i.occurred_at DESC, i.id DESC LIMIT 1) AS last_channel

        FROM contacts
        """
    ).fetchall()

    connection.close()

    return {row["contact_id"]: dict(row) for row in rows}


# ==========================================
# 8. CREATION DES RELANCES
# ==========================================

def create_task(contact_id, title, description, due_at):
    """Cree une prochaine action commerciale."""

    connection = get_connection()

    try:
        connection.execute(
            """
            INSERT INTO tasks (
                contact_id,
                title,
                description,
                due_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                contact_id,
                title,
                description,
                due_at
            )
        )

        connection.commit()

        return True

    finally:
        connection.close()


# ==========================================
# 9. RECUPERATION DES RELANCES
# ==========================================

def get_stage_changes(contact_id):
    """Changements d'etape d'un prospect, du plus recent au plus ancien."""

    connection = get_connection()

    rows = connection.execute(
        """
        SELECT *, datetime(changed_at, 'localtime') AS changed_at_local
        FROM stage_changes
        WHERE contact_id = ?
        ORDER BY id DESC
        """,
        (contact_id,)
    ).fetchall()

    connection.close()

    return [dict(row) for row in rows]


def get_tasks(contact_id):
    """Recupere les relances d'un prospect."""

    connection = get_connection()

    tasks = connection.execute(
        """
        SELECT *, datetime(created_at, 'localtime') AS created_at_local
        FROM tasks

        WHERE contact_id = ?

        ORDER BY due_at ASC
        """,
        (contact_id,)
    ).fetchall()

    connection.close()

    return [dict(task) for task in tasks]


def get_all_tasks():
    """Toutes les relances, avec le nom du prospect et de l'entreprise."""

    connection = get_connection()

    tasks = connection.execute(
        """
        SELECT
            tasks.*,
            contacts.first_name,
            contacts.last_name,
            companies.name AS company_name
        FROM tasks

        JOIN contacts
            ON tasks.contact_id = contacts.id

        LEFT JOIN companies
            ON contacts.company_id = companies.id

        ORDER BY tasks.due_at IS NULL, tasks.due_at ASC, tasks.id ASC
        """
    ).fetchall()

    connection.close()

    return [dict(task) for task in tasks]


# ==========================================
# 10. TERMINER UNE RELANCE
# ==========================================

def reschedule_task(task_id, due_at):
    """Reporte une relance a une nouvelle echeance ("AAAA-MM-JJ")."""

    connection = get_connection()

    try:
        connection.execute("UPDATE tasks SET due_at = ? WHERE id = ?", (due_at, task_id))
        connection.commit()

    finally:
        connection.close()


def snooze_prospect(contact_id, until, reason=None):
    """Ecarte un prospect du Today's Focus jusqu'a une date ("AAAA-MM-JJ") incluse."""

    connection = get_connection()

    try:
        connection.execute(
            """
            INSERT INTO focus_snoozes (contact_id, until, reason, created_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(contact_id) DO UPDATE SET
                until = excluded.until, reason = excluded.reason, created_at = CURRENT_TIMESTAMP
            """,
            (contact_id, until, _clean(reason))
        )
        connection.commit()

    finally:
        connection.close()


def unsnooze_prospect(contact_id=None):
    """Remet un prospect (ou tous si contact_id est None) dans le Today's Focus."""

    connection = get_connection()

    try:
        if contact_id is None:
            connection.execute("DELETE FROM focus_snoozes")
        else:
            connection.execute("DELETE FROM focus_snoozes WHERE contact_id = ?", (contact_id,))
        connection.commit()

    finally:
        connection.close()


def get_active_snoozes(today):
    """Prospects ecartes dont la date de fin n'est pas depassee : {contact_id: {...}}."""

    connection = get_connection()

    rows = connection.execute(
        "SELECT * FROM focus_snoozes WHERE until >= ?", (today,)
    ).fetchall()

    connection.close()

    return {row["contact_id"]: dict(row) for row in rows}


def complete_task(task_id):
    """Marque une relance comme terminee."""

    connection = get_connection()

    try:
        connection.execute(
            """
            UPDATE tasks
            SET status = 'Terminee'
            WHERE id = ?
            """,
            (task_id,)
        )

        connection.commit()

    finally:
        connection.close()


# ==========================================
# 11. EXECUTION DIRECTE DU FICHIER
# ==========================================

if __name__ == "__main__":
    initialize_database()
