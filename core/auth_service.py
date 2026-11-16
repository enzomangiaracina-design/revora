"""Vraie connexion (phase 12.1) : règles, sans interface.

REVORA ne gère AUCUN mot de passe. La connexion passe par un fournisseur
d'identité (Google, Microsoft…) via st.login() de Streamlit, norme OIDC :
le fournisseur vérifie l'identité et renvoie l'email de la personne.

Activation : uniquement si une section [auth] complète existe dans
.streamlit/secrets.toml (fichier exclu de Git). Sans elle, REVORA fonctionne
comme avant, avec le menu « Signed in as » (prototype local).

Accès : l'email renvoyé doit correspondre à un membre ACTIF de l'équipe
(Settings › Team). Personne d'autre n'entre, même avec un compte Google valide.
"""

# Réglages exigés par st.login() pour le fournisseur par défaut (documentation Streamlit 1.67)
REQUIRED_AUTH_KEYS = ("redirect_uri", "cookie_secret", "client_id", "client_secret", "server_metadata_url")


def auth_settings(secrets):
    """Section [auth] des secrets, ou None si elle est absente.

    secrets : st.secrets, ou un dictionnaire (tests). Ne lève jamais d'erreur :
    un fichier secrets.toml absent signifie simplement « pas de connexion ».
    """

    try:
        section = secrets.get("auth") if hasattr(secrets, "get") else None
    except Exception:          # secrets.toml absent ou illisible
        return None

    return dict(section) if section else None


def missing_settings(secrets):
    """Réglages manquants dans [auth] (liste vide = configuration complète)."""

    section = auth_settings(secrets) or {}

    return [key for key in REQUIRED_AUTH_KEYS if not str(section.get(key) or "").strip()]


REQUIRE_ENV = "REVORA_REQUIRE_SIGN_IN"


def sign_in_required(environ):
    """True si la connexion est OBLIGATOIRE (version en ligne : REVORA_REQUIRE_SIGN_IN=1).

    Dans ce cas, REVORA refuse de s'ouvrir tant que la vraie connexion n'est pas
    configurée : jamais de menu « Signed in as » sans mot de passe sur Internet.
    """

    return str(environ.get(REQUIRE_ENV, "")).strip().lower() in ("1", "true", "yes")


def is_configured(secrets):
    """True si la vraie connexion doit être exigée (section [auth] présente et complète)."""

    return auth_settings(secrets) is not None and not missing_settings(secrets)


def resolve_user(users, claims):
    """Membre de l'équipe correspondant à l'identité renvoyée par le fournisseur.

    claims : informations du fournisseur (st.user), dont "email" et parfois
    "email_verified". Retourne (utilisateur ou None, message pour l'écran).
    """

    email = str((claims or {}).get("email") or "").strip().lower()

    if not email:
        return None, "Your identity provider did not share an email address."

    # Un fournisseur qui signale un email NON vérifié : refusé (quelqu'un pourrait l'avoir inventé)
    if (claims or {}).get("email_verified") is False:
        return None, f"The email {email} is not verified by your identity provider."

    for user in users:
        if (user.get("email") or "").strip().lower() == email:
            if not user.get("active"):
                return None, f"The account for {email} is deactivated. Ask a manager to reactivate it."
            return user, f"Signed in as {user['name']}."

    return None, (f"{email} is not in the REVORA team yet. "
                  "Ask a manager to add this email in Settings › Team.")


def can_manage_team(user, auth_enabled):
    """Gérer l'équipe : tout le monde en local (prototype), seulement un manager avec la vraie connexion."""

    return not auth_enabled or bool(user and user.get("role") == "Manager")
