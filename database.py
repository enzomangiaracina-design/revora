
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

    connection.commit()
    connection.close()

    print("REVORA database initialized successfully.")
    print(f"Database location: {DATABASE_PATH}")


# ==========================================
# 3. CREATION DES PROSPECTS
# ==========================================

def create_prospect(
    first_name,
    last_name,
    company_name,
    vertical,
    email,
    phone,
    job_title
):
    """Cree une entreprise si necessaire et un prospect."""

    connection = get_connection()

    try:
        cursor = connection.cursor()

        # Recherche de l'entreprise
        cursor.execute(
            """
            SELECT id FROM companies
            WHERE lower(name) = lower(?)
            AND vertical = ?
            """,
            (company_name.strip(), vertical)
        )

        company = cursor.fetchone()

        # Creation de l'entreprise si elle n'existe pas
        if company:
            company_id = company["id"]

        else:
            cursor.execute(
                """
                INSERT INTO companies (name, vertical)
                VALUES (?, ?)
                """,
                (company_name.strip(), vertical)
            )

            company_id = cursor.lastrowid

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
                job_title
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                company_id,
                first_name.strip(),
                last_name.strip(),
                email.strip() if email else None,
                phone.strip() if phone else None,
                job_title.strip() if job_title else None
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
# 6. ENREGISTREMENT DES INTERACTIONS
# ==========================================

def add_interaction(
    contact_id,
    channel,
    direction,
    event_type,
    subject,
    content,
    outcome
):
    """Enregistre un appel, un email ou une note."""

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
                provider
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                contact_id,
                channel,
                direction,
                event_type,
                subject,
                content,
                outcome,
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
        SELECT *
        FROM interactions

        WHERE contact_id = ?

        ORDER BY occurred_at DESC, id DESC
        """,
        (contact_id,)
    ).fetchall()

    connection.close()

    return [dict(item) for item in interactions]


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
