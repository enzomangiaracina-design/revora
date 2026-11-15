"""Équipe (phase 11.1) : utilisateurs, rôles et choix du propriétaire d'un prospect.

Prototype SANS mot de passe : chacun choisit son nom dans la barre latérale.
Une vraie connexion (identifiants, fournisseur d'identité) viendra avec
l'hébergement (phase 12).

Le propriétaire d'un prospect reste un NOM stocké dans contacts.owner : les
données existantes ne sont pas converties. La liste des utilisateurs sert à
proposer des noms cohérents (fini « Léa » / « Lea Martin » / « léa »).
"""

import database
from core.prospect_service import EMAIL_PATTERN

ROLES = ["SDR", "Manager"]

UNASSIGNED_LABEL = "Unassigned"


def _clean_email(email):
    """Email nettoyé (minuscules, sans espaces), "" si vide, None s'il est invalide."""

    email = (email or "").strip().lower()

    if email and not EMAIL_PATTERN.match(email):
        return None

    return email


def create_user(name, role="SDR", email=None):
    """Valide puis ajoute un utilisateur. Retourne (succès, message).

    email (facultatif) : celui de son compte Google / Microsoft, utilisé par la
    vraie connexion (phase 12.1).
    """

    name = " ".join((name or "").split())          # espaces en trop retirés

    if len(name) < 2:
        return False, "Enter a name (at least 2 characters)."

    if role not in ROLES:
        return False, "Choose a role: " + " or ".join(ROLES) + "."

    email = _clean_email(email)
    if email is None:
        return False, "Enter a valid email, for example lea.martin@company.com."

    if database.add_user(name, role, email or None) is None:
        return False, f"{name} or this email is already in the team."

    return True, f"{name} added to the team."


def set_email(user_id, email):
    """Change l'email de connexion d'un utilisateur. Retourne (succès, message)."""

    email = _clean_email(email)
    if email is None:
        return False, "Enter a valid email, for example lea.martin@company.com."

    result = database.set_user_email(user_id, email or None)

    if result is None:
        return False, "This email is already used by another team member."
    if not result:
        return False, "User not found."

    return True, "Email updated." if email else "Email removed."


def set_role(user_id, role):
    """Change le rôle d'un utilisateur. Retourne (succès, message)."""

    if role not in ROLES:
        return False, "Choose a role: " + " or ".join(ROLES) + "."

    if not database.update_user(user_id, role=role):
        return False, "User not found."

    return True, f"Role updated: {role}."


def set_active(user_id, active):
    """Active ou désactive un utilisateur (jamais supprimé). Retourne (succès, message)."""

    if not database.update_user(user_id, active=active):
        return False, "User not found."

    return True, "User reactivated." if active else "User deactivated: kept in history, hidden from lists."


def missing_owners(users, prospects):
    """Propriétaires déjà présents sur des prospects mais absents de l'équipe (sans doublon)."""

    known = {u["name"].casefold() for u in users}
    found = {}

    for p in prospects:
        owner = (p.get("owner") or "").strip()
        if owner and owner.casefold() not in known:
            found.setdefault(owner.casefold(), owner)

    return sorted(found.values(), key=str.casefold)


def import_owners(users, prospects):
    """Ajoute à l'équipe (rôle SDR) les propriétaires trouvés sur les prospects.

    Ne modifie aucun prospect. Retourne (succès, message).
    """

    names = missing_owners(users, prospects)

    for name in names:
        database.add_user(name, "SDR")

    if not names:
        return True, "Every sales owner is already in the team."

    return True, f"{len(names)} user(s) added: {', '.join(names)}."


def owner_choices(users, current=None):
    """Noms proposés comme propriétaire : utilisateurs actifs, plus le propriétaire actuel.

    Le propriétaire actuel est gardé même s'il n'est pas (ou plus) dans l'équipe,
    pour qu'une modification ne l'efface jamais en silence.
    La chaîne vide "" signifie « non assigné ».
    """

    names = [u["name"] for u in users if u["active"]]
    current = (current or "").strip()

    if current and current.casefold() not in {n.casefold() for n in names}:
        names.append(current)

    return [""] + names


def find_user(users, name):
    """Utilisateur portant ce nom (sans tenir compte des majuscules), ou None."""

    name = (name or "").casefold()

    return next((u for u in users if u["name"].casefold() == name), None)


# ==========================================
# « MES PROSPECTS » (phase 11.2)
# ==========================================

MINE = "My prospects"
EVERYONE = "Everyone"


def default_scope(user):
    """Vue par défaut : un SDR voit ses prospects, un manager (ou personne) voit tout."""

    return MINE if user and user.get("role") == "SDR" else EVERYONE


def owned_by(prospects, name):
    """Prospects dont le propriétaire est `name` (sans tenir compte des majuscules ni des espaces)."""

    name = (name or "").strip().casefold()

    return [p for p in prospects if name and (p.get("owner") or "").strip().casefold() == name]


def for_prospects(items, prospects, key="contact_id"):
    """Garde les éléments (interactions, relances, objections…) qui concernent ces prospects."""

    ids = {p["id"] for p in prospects}

    return [item for item in items if item.get(key) in ids]
