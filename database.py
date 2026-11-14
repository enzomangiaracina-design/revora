
import json
import sqlite3
from pathlib import Path


# ==========================================
# 1. CONFIGURATION DE LA BASE DE DONNEES
# ==========================================

BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "revora.db"


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

    # MIGRATIONS (phase 2) : ajout de colonnes sur une base existante,
    # sans toucher aux données déjà enregistrées.
    _add_column_if_missing(cursor, "contacts", "source", "TEXT")
    _add_column_if_missing(cursor, "contacts", "owner", "TEXT")
    _add_column_if_missing(cursor, "contacts", "updated_at", "TEXT")
    _add_column_if_missing(cursor, "companies", "industry", "TEXT")
    _add_column_if_missing(cursor, "companies", "size", "TEXT")
    _add_column_if_missing(cursor, "companies", "country", "TEXT")

    connection.commit()
    connection.close()

    print("REVORA database initialized successfully.")
    print(f"Database location: {DATABASE_PATH}")


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

def _clean(value):
    """Retire les espaces autour d'un texte ; retourne None si le texte est vide."""

    if value is None:
        return None

    value = str(value).strip()

    return value or None


def _get_or_create_company(cursor, company_name, vertical):
    """Retourne l'id de l'entreprise (meme nom et meme verticale), en la creant si besoin."""

    vertical = _clean(vertical)

    # "IS" (et non "=") pour que deux verticales vides (NULL) soient considerees egales
    cursor.execute(
        """
        SELECT id FROM companies
        WHERE lower(name) = lower(?)
        AND vertical IS ?
        """,
        (company_name.strip(), vertical)
    )

    company = cursor.fetchone()

    if company:
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
    owner=None
):
    """Cree une entreprise si necessaire et un prospect.

    status, source et owner sont optionnels : les appels existants
    (7 arguments) continuent de fonctionner.
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
                owner
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                _clean(owner)
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
            contacts.created_at,
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
    owner=None
):
    """Met a jour un prospect. Retourne (succes, message)."""

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
                contact_id
            )
        )

        if cursor.rowcount == 0:
            return False, "Prospect introuvable."

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
        for table in ("interactions", "tasks", "scores")
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

        for table in ("interactions", "tasks", "scores"):
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
        connection.execute(
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

        return True

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
             ORDER BY t.due_at IS NULL, t.due_at LIMIT 1) AS next_task_title

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

def get_tasks(contact_id):
    """Recupere les relances d'un prospect."""

    connection = get_connection()

    tasks = connection.execute(
        """
        SELECT *
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
