"""Choix du fournisseur d'IA de l'AI Copilot (réglage « ai_provider »).

Chaque fournisseur expose la même interface : LABEL, MODEL, API_KEY_NAME,
PRICES, FREE_TIER_NOTE, is_configured() et generate(system, prompt, schema).
La logique (contexte, sources, vérification) reste dans core/copilot_service.py.
"""

import database
from ai import claude_client, gemini_client

PROVIDERS = {"claude": claude_client, "gemini": gemini_client}
SETTING_PROVIDER = "ai_provider"
DEFAULT_PROVIDER = "claude"


def active_name():
    name = database.get_setting(SETTING_PROVIDER, DEFAULT_PROVIDER)
    return name if name in PROVIDERS else DEFAULT_PROVIDER


def active():
    """Module du fournisseur choisi dans Settings."""

    return PROVIDERS[active_name()]


def ai_is_configured():
    return active().is_configured()


def ai_generate(system, prompt, schema):
    return active().generate(system, prompt, schema)
