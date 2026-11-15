"""Appel à l'API Google Gemini (fournisseur alternatif, offre gratuite).

Même interface que ai/claude_client.py : is_configured() et
generate(system, prompt, schema) -> (données JSON, consommation).

Vérifié dans le kit officiel installé (google-genai 3.3.0) :
  - client : genai.Client(api_key=...) ;
  - appel  : client.models.generate_content(model, contents, config=...)
             avec types.GenerateContentConfig(system_instruction,
             response_mime_type="application/json", response_json_schema) ;
  - lecture : response.text, response.usage_metadata.prompt_token_count /
             candidates_token_count, candidates[0].finish_reason ;
  - erreurs : google.genai.errors.ClientError (4xx) / ServerError (5xx), attribut .code.

ATTENTION (page tarifs officielle, 15/11/2026) : sur l'offre GRATUITE, le
contenu envoyé est « utilisé pour améliorer les produits » de Google.
Réservé aux données de démonstration ou de test.
"""

import json

from ai.claude_client import CopilotError
from integrations.config import get_secret

MODEL = "gemini-3.8-flash"     # disponible sur l'offre gratuite d'après la page tarifs
API_KEY_NAME = "GEMINI_API_KEY"
LABEL = "Google Gemini"
PRICES = None            # offre gratuite : pas de coût affiché
FREE_TIER_NOTE = "Gemini free tier: Google may use the content sent to improve its products."

BLOCKED = {"SAFETY", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII", "RECITATION"}


def is_configured():
    return get_secret(API_KEY_NAME) is not None


def _default_client():
    from google import genai

    return genai.Client(api_key=get_secret(API_KEY_NAME))


def generate(system, prompt, schema, client=None):
    """Envoie la demande à Gemini et renvoie (données JSON, consommation)."""

    from google.genai import errors, types

    if client is None:
        if not is_configured():
            raise CopilotError(f"No API key found. Add {API_KEY_NAME} to the .env file.")
        client = _default_client()

    config = types.GenerateContentConfig(
        system_instruction=system,
        response_mime_type="application/json",
        response_json_schema=schema,
    )

    try:
        response = client.models.generate_content(model=MODEL, contents=prompt, config=config)
    except errors.ClientError as error:
        if error.code in (401, 403):
            raise CopilotError(f"The Gemini API key was rejected. Check {API_KEY_NAME} in the .env file.")
        if error.code == 429:
            raise CopilotError("Gemini free-tier limit reached. Wait a minute (or until tomorrow) and try again.")
        raise CopilotError(f"The request was refused by Gemini: {error.message}")
    except errors.ServerError as error:
        raise CopilotError(f"Gemini returned an error ({error.code}). Try again later.")
    except errors.APIError as error:
        raise CopilotError(f"Gemini error: {error.message}")

    feedback = getattr(response, "prompt_feedback", None)

    if feedback is not None and getattr(feedback, "block_reason", None):
        raise CopilotError("Gemini declined this request. Nothing was generated.")

    candidates = response.candidates or []
    reason = getattr(getattr(candidates[0], "finish_reason", None), "name", None) if candidates else None

    if reason in BLOCKED:
        raise CopilotError("Gemini declined this request. Nothing was generated.")

    if reason == "MAX_TOKENS":
        raise CopilotError("The answer was cut off before the end. Try again.")

    text = response.text

    if not text:
        raise CopilotError("Gemini returned no answer. Try again.")

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        raise CopilotError("The Gemini answer could not be read. Try again.")

    usage = getattr(response, "usage_metadata", None)

    return data, {
        "input_tokens": getattr(usage, "prompt_token_count", 0) or 0,
        "output_tokens": getattr(usage, "candidates_token_count", 0) or 0,
        "model": getattr(response, "model_version", None) or MODEL,
    }
