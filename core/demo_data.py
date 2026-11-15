"""Base de démonstration réaliste et ENTIÈREMENT FICTIVE.

Crée une base SÉPARÉE (par défaut demo.db) pour tester et faire des démos,
sans jamais toucher revora.db :
  - 20 prospects fictifs (noms, entreprises, emails en .example, numéros factices) ;
  - appels, emails, messages LinkedIn et notes sur les 45 derniers jours ;
  - objections, relances (dont certaines en retard), qualification.

Le contenu est déterministe (graine fixe) : deux générations le même jour
donnent la même base. Les dates sont calculées à partir d'aujourd'hui.

Lancement : python3 seed_demo.py   (voir README)
"""

import random
from datetime import date, datetime, time, timedelta
from pathlib import Path

import database

DEMO_PATH = database.BASE_DIR / "demo.db"

OWNERS = ["Léa Martin", "Hugo Bernard", None]
SOURCES = ["Import CSV", "LinkedIn", "Trade show", "Referral", "Website"]

# Prénom, nom, entreprise, verticale, poste — tous inventés
PEOPLE = [
    ("Camille", "Roussel", "Nordvia", "SaaS", "Head of Sales"),
    ("Julien", "Mercier", "Kaltera", "Finance", "CFO"),
    ("Sarah", "Benali", "Medivo", "Santé", "Directrice des opérations"),
    ("Maxime", "Lefort", "Atelio", "Industrie", "Plant Manager"),
    ("Emma", "Collins", "Brightlane", "SaaS", "VP Sales"),
    ("Thomas", "Garnier", "Finexo", "Finance", "Head of Revenue"),
    ("Inès", "Moreau", "Clinova", "Santé", "Responsable achats"),
    ("Lucas", "Perrin", "Metalys", "Industrie", "Directeur commercial"),
    ("Olivia", "Grant", "Stackwise", "SaaS", "CEO"),
    ("Nathan", "Faure", "Capvia", "Finance", "COO"),
    ("Chloé", "Lambert", "Santéo", "Santé", "Directrice générale"),
    ("Hugo", "Renaud", "Usinor Lab", "Industrie", "Head of Operations"),
    ("Manon", "Girard", "Cloudora", "SaaS", "Sales Ops Manager"),
    ("Antoine", "Dubois", "Trésoria", "Finance", "Directeur financier"),
    ("Léna", "Fontaine", "Pharmalys", "Santé", "Head of Procurement"),
    ("Paul", "Chevalier", "Robotix", "Industrie", "CTO"),
    ("Zoé", "Marchand", "Retailio", "Retail", "Directrice e-commerce"),
    ("Hamza", "Haddad", "Shopwave", "Retail", "Head of Growth"),
    ("Clara", "Noël", "Datavia", "SaaS", "Head of Marketing"),
    ("Victor", "Blanc", "Assurio", "Finance", "Head of Sales"),
]

# Scénario de chaque prospect (même ordre que PEOPLE) et étape finale
SCENARIOS = [
    "meeting", "interested", "in_contact", "first_attempt", "never", "lost", "interested", "first_attempt",
    "meeting", "follow_up", "in_contact", "never", "interested", "disqualified", "first_attempt",
    "in_contact", "never", "follow_up", "in_contact", "first_attempt",
]

STAGE_OF = {
    "never": "To prospect", "first_attempt": "First attempt", "in_contact": "In contact",
    "interested": "Interested", "meeting": "Meeting scheduled", "follow_up": "To follow up",
    "lost": "Not interested", "disqualified": "Disqualified",
}


def _slug(text):
    table = str.maketrans("éèêëàâäîïôöùûüç ", "eeeeaaaiioouuuc-")
    return text.lower().translate(table)


class _Builder:
    """Écrit les enregistrements d'un prospect, avec des dates passées cohérentes."""

    def __init__(self, contact_id, rng, today):
        self.id, self.rng, self.today = contact_id, rng, today

    def at(self, days_ago, hour=None):
        moment = datetime.combine(self.today - timedelta(days=days_ago),
                                  time(hour if hour is not None else self.rng.randint(9, 17), self.rng.choice([0, 15, 30, 45])))
        return moment.strftime("%Y-%m-%d %H:%M:%S")

    def touch(self, days_ago, channel, direction, result, subject, notes="", next_step="", minutes=0):
        metadata = {"duration_seconds": minutes * 60} if channel == "Call" and minutes else None
        return database.add_interaction(self.id, channel, direction, result, subject, notes, next_step,
                                        occurred_at=self.at(days_ago), metadata=metadata)

    def objection(self, category, wording, days_ago, interaction_id=None, status="Open"):
        objection_id = database.add_objection(self.id, category, wording, interaction_id=interaction_id,
                                              occurred_at=self.at(days_ago))
        if status != "Open":
            database.set_objection_status(objection_id, status)

    def follow_up(self, title, due_in_days, done=False, scheduled_days_ago=None):
        database.create_task(self.id, title, "", (self.today + timedelta(days=due_in_days)).isoformat())
        task = next(t for t in database.get_tasks(self.id) if t["title"] == title)
        # Planifiée quelques jours avant son échéance (et jamais dans le futur)
        planned = scheduled_days_ago if scheduled_days_ago is not None else max(1, 3 - due_in_days)
        database.set_created_at("tasks", task["id"], self.at(planned))
        if done:
            database.complete_task(task["id"])


def _play(scenario, b, first_name):
    """Historique d'un prospect selon son scénario (les plus anciens d'abord)."""

    rng = b.rng

    if scenario == "never":
        database.set_created_at("contacts", b.id, b.at(rng.randint(2, 12)))
        return

    start = rng.randint(20, 40)
    database.set_created_at("contacts", b.id, b.at(start + 5))     # ajouté avant le premier contact

    if rng.random() < 0.5:
        b.touch(start + 2, "LinkedIn", "Outbound", "Connection request sent", "")
        if scenario != "first_attempt":
            b.touch(start + 1, "LinkedIn", "Inbound", "Connection accepted", "")

    b.touch(start, "Call", "Outbound", "No answer", "Premier appel")
    b.touch(start - 1, "Email", "Outbound", "Completed", "Présentation rapide",
            f"Email de présentation envoyé à {first_name} avec un cas client du même secteur.")

    if scenario == "first_attempt":
        b.touch(start - 4, "Call", "Outbound", "Voicemail", "Relance", "Message laissé, rappel prévu.")
        b.follow_up("Rappeler (2e tentative)", rng.choice([-3, -1, 0, 2]))
        return

    call = b.touch(start - 5, "Call", "Outbound", "Completed", "Appel de découverte",
                   rng.choice([
                       "Équipe de 8 commerciaux, prospection surtout par email. Cherche à gagner du temps sur la préparation des appels.",
                       "Utilise un CRM mais peu de suivi des relances. Intéressé par une vue des priorités du jour.",
                       "Process commercial en cours de refonte, décision prévue au prochain trimestre.",
                   ]),
                   "Envoyer une proposition", minutes=rng.randint(8, 25))

    if scenario == "lost":
        b.objection("Not interested", "Nous n'avons pas de besoin sur ce sujet.", start - 5, call, status="Lost")
        return

    if scenario == "disqualified":
        b.touch(start - 7, "Note", "Internal", "Other", "Hors cible", "Entreprise trop petite (3 personnes), hors cible.")
        return

    b.touch(start - 8, "Email", "Inbound", "Positive response", "Re: Présentation rapide",
            "Merci, pouvez-vous m'envoyer une proposition chiffrée ?")
    database.update_qualification(b.id, {"need_identified": True})

    if scenario == "in_contact":
        if rng.random() < 0.6:
            b.objection("Bad timing", "Revenez vers moi après la clôture du trimestre.", start - 5, call)
        b.follow_up("Envoyer la proposition", rng.choice([-5, -2, 1, 4]))
        return

    if scenario == "follow_up":
        b.objection("Bad timing", "Pas avant mars, budget gelé jusque-là.", start - 9, call)
        b.follow_up("Relancer en mars", rng.randint(20, 60))
        return

    b.touch(start - 12, "Call", "Outbound", "Positive response", "Point proposition",
            "Proposition bien reçue. Souhaite associer son directeur commercial.", "Organiser une démo", minutes=12)

    if rng.random() < 0.5:
        b.objection("Price too high", "Le prix est au-dessus de ce que nous avions prévu.", start - 12,
                    status=rng.choice(["Open", "Handled"]))

    if scenario == "interested":
        database.update_qualification(b.id, {"is_decision_maker": True})
        b.follow_up("Proposer une date de démo", rng.choice([-1, 0, 3]))
        return

    # meeting
    b.touch(start - 15, "Call", "Outbound", "Meeting booked", "Démo planifiée",
            "Démo calée avec le directeur commercial.", "Préparer la démo", minutes=6)
    database.update_qualification(b.id, {"is_decision_maker": True, "demo_requested": True})
    b.follow_up("Préparer la démo", rng.choice([1, 2, 5]))
    b.follow_up("Envoyer le récapitulatif de l'appel", -(start - 15) + 1, done=True)


def generate_demo(path=DEMO_PATH, today=None, seed=42, reset=False):
    """Crée la base de démonstration. Retourne un résumé {"path", "prospects", ...}.

    Sécurités : refuse de viser revora.db ; refuse d'écraser une base existante
    sans reset=True (et ne supprime alors QUE ce fichier de démo).
    """

    path = Path(path).resolve()
    today = today or date.today()

    if path == database.DEFAULT_DATABASE_PATH.resolve():
        raise ValueError("Refusing to write demo data into revora.db.")

    if path.exists():
        if not reset:
            raise FileExistsError(f"{path.name} already exists. Use --reset to recreate it.")
        path.unlink()

    rng = random.Random(seed)
    previous = database.DATABASE_PATH
    database.DATABASE_PATH = path

    try:
        database.initialize_database()

        for (first, last, company, vertical, job), scenario in zip(PEOPLE, SCENARIOS):
            ok, message = database.create_prospect(
                first, last, company, vertical,
                f"{_slug(first)}.{_slug(last)}@{_slug(company)}.example",
                f"+33 6 00 00 {rng.randint(10, 99)} {rng.randint(10, 99)}",
                job, status=STAGE_OF[scenario], source=rng.choice(SOURCES), owner=rng.choice(OWNERS),
            )
            if not ok:
                raise RuntimeError(message)

            contact_id = next(p["id"] for p in database.get_all_prospects()
                              if p["first_name"] == first and p["last_name"] == last)
            _play(scenario, _Builder(contact_id, rng, today), first)

        # Réponses du playbook (rédigées pour la démo)
        database.set_objection_response("Bad timing", "Acknowledge, ask what changes after the date, "
                                        "and book a dated call-back now.")
        database.set_objection_response("Price too high", "Ask which budget was planned, then show the "
                                        "time saved per SDR per week with a customer example.")

        return {
            "path": str(path),
            "prospects": len(database.get_all_prospects()),
            "interactions": len(database.get_all_interactions()),
            "objections": len(database.get_objections()),
            "follow_ups": len(database.get_all_tasks()),
        }

    finally:
        database.DATABASE_PATH = previous
