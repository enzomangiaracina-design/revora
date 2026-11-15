"""Appel à l'API Claude (phase 10.1).

Seul endroit de REVORA qui envoie des données à un service d'IA externe.
Il n'est appelé que sur un clic explicite du commercial, quand les
fonctions IA sont activées dans Settings ET qu'une clé est configurée.

Concepts :
  - la clé n'est jamais dans le code : elle est lue dans .env
    (ANTHROPIC_API_KEY), fichier exclu de Git ;
  - « structured outputs » : on impose un schéma JSON à la réponse ;
  - « fallbacks » : si le modèle refuse pour une raison de sécurité, l'API
    relance la même demande sur un autre modèle (choisi par l'API) ;
  - le client est « injectable » : les tests passent un faux client et
    n'appellent jamais l'API réelle (aucun coût).
"""

import json

from integrations.config import get_secret

MODEL = "claude-opus-5-5"
EFFORT = "low"            # brief et brouillon courts : effort faible = moins cher et plus rapide
MAX_TOKENS = 16000
API_KEY_NAME = "ANTHROPIC_API_KEY"
FALLBACK_BETA = "server-side-fallback-2026-07-01"
LABEL = "Anthropic Claude"
FREE_TIER_NOTE = None
PRICES = (4.0, 20.0)      # dollars par million de jetons (entrée, sortie)


class CopilotError(Exception):
    """Erreur présentée telle quelle au commercial (message lisible, en anglais)."""


def is_configured():
    """Une clé API est-elle disponible (.env ou terminal) ?"""

    return get_secret(API_KEY_NAME) is not None


def _default_client():
    import anthropic

    return anthropic.Anthropic(api_key=get_secret(API_KEY_NAME), max_retries=2, timeout=120.0)


def generate(system, prompt, schema, client=None):
    """Envoie une demande à Claude et renvoie (données JSON, consommation).

    Lève CopilotError avec un message clair en cas de problème.
    """

    import anthropic

    if client is None:
        if not is_configured():
            raise CopilotError(f"No API key found. Add {API_KEY_NAME} to the .env file.")
        client = _default_client()

    try:
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            betas=[FALLBACK_BETA],
            fallbacks="default",
            output_config={"effort": EFFORT, "format": {"type": "json_schema", "schema": schema}},
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.AuthenticationError:
        raise CopilotError("The API key was rejected. Check ANTHROPIC_API_KEY in the .env file.")
    except anthropic.PermissionDeniedError:
        raise CopilotError("This API key is not allowed to use this model.")
    except anthropic.RateLimitError:
        raise CopilotError("Too many requests or spending limit reached. Try again in a minute.")
    except anthropic.BadRequestError as error:
        raise CopilotError(f"The request was refused by the API: {error.message}")
    except anthropic.APIStatusError as error:
        raise CopilotError(f"The AI service returned an error ({error.status_code}). Try again later.")
    except anthropic.APIConnectionError:
        raise CopilotError("Could not reach the AI service. Check your internet connection.")

    if response.stop_reason == "refusal":
        raise CopilotError("The AI declined this request. Nothing was generated.")

    if response.stop_reason == "max_tokens":
        raise CopilotError("The answer was cut off before the end. Try again.")

    text = next((block.text for block in response.content if block.type == "text"), None)

    if text is None:
        raise CopilotError("The AI returned no answer. Try again.")

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        raise CopilotError("The AI answer could not be read. Try again.")

    usage = {
        "input_tokens": getattr(response.usage, "input_tokens", 0) or 0,
        "output_tokens": getattr(response.usage, "output_tokens", 0) or 0,
        "model": getattr(response, "model", MODEL),
    }

    return data, usage
