"""Outils de rapprochement et de déduplication — version de départ.

Pourquoi normaliser ? Le même numéro peut être écrit "06 12 34 56 78",
"+33 6 12 34 56 78" ou "0033612345678". Pour reconnaître qu'il s'agit du même
contact (par exemple quand un appel Noota arrivera), il faut d'abord ramener
toutes ces écritures à une forme unique.

Rappel du cahier des charges : le rapprochement d'une interaction avec un
contact doit utiliser en priorité l'identifiant CRM, puis le téléphone
normalisé, puis l'email. Le téléphone seul ne suffit pas (standards partagés).
"""

import re


def normalize_email(email):
    """Retourne l'email en minuscules et sans espaces, ou None s'il est vide."""

    if not email or not email.strip():
        return None

    return email.strip().lower()


def normalize_phone(phone):
    """Convertit un numéro au format international E.164 (ex. +33612345678).

    Règles (prototype, pensé pour la France) :
      - les espaces, points, tirets et parenthèses sont ignorés ;
      - "00..." devient "+..." ;
      - un numéro français à 10 chiffres commençant par 0 devient "+33..." ;
      - un numéro déjà au format "+..." est conservé.
    Retourne None si le numéro est vide ou ne peut pas être interprété.
    """

    if not phone:
        return None

    cleaned = re.sub(r"[\s.\-()]", "", phone)

    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]

    if re.fullmatch(r"0\d{9}", cleaned):
        return "+33" + cleaned[1:]

    if re.fullmatch(r"\+\d{8,15}", cleaned):
        return cleaned

    return None


LINKEDIN_PROFILE = re.compile(
    # Identifiant limité aux caractères utilisés par LinkedIn (lettres, chiffres, - _ . %) :
    # l'URL est affichée comme lien, aucun caractère ne doit pouvoir le détourner.
    r"^(?:https?://)?(?:[a-z]{2,3}\.|www\.)?linkedin\.com/in/([A-Za-z0-9_.%-]+)/?(?:[?#].*)?$",
    re.IGNORECASE,
)


def normalize_linkedin_url(url):
    """URL de profil LinkedIn -> forme unique "https://www.linkedin.com/in/<identifiant>".

    Accepte "linkedin.com/in/x", "fr.linkedin.com/in/x/", "https://www.linkedin.com/in/X?trk=…".
    Retourne None si ce n'est pas une URL de profil personnel (/in/…).
    Simple mise en forme du texte saisi : aucune page LinkedIn n'est consultée.
    """

    if not url or not url.strip():
        return None

    match = LINKEDIN_PROFILE.match(url.strip())

    if not match:
        return None

    return f"https://www.linkedin.com/in/{match.group(1).lower()}"
