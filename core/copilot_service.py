"""AI Copilot (phase 10.1) : préparation d'appel et brouillon d'email.

Ce module ne parle PAS à l'IA : il prépare ce qui lui est envoyé et vérifie
ce qu'elle renvoie. L'appel réseau est dans ai/claude_client.py.

Règles du cahier des charges, appliquées ici :
  - s'appuyer uniquement sur les données réelles de la base ;
  - citer les échanges utilisés (identifiants « I12 », « O3 ») ;
  - distinguer faits confirmés et hypothèses ;
  - ne jamais inventer une information absente.

Minimisation des données : l'email, le téléphone et l'URL LinkedIn du
prospect ne sont JAMAIS envoyés (inutiles pour préparer un appel).
"""

import json

MAX_INTERACTIONS = 10

SETTING_ENABLED = "ai_enabled"

# ---------- Formats de réponse imposés (structured outputs) ----------
# Concept : on donne à l'API un « schéma JSON ». La réponse est garantie
# conforme : REVORA sait exactement où lire les faits, les sources, etc.

_SOURCED_ITEM = {
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "sources": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["text", "sources"],
    "additionalProperties": False,
}

CALL_BRIEF_SCHEMA = {
    "type": "object",
    "properties": {
        "facts": {"type": "array", "items": _SOURCED_ITEM},
        "hypotheses": {"type": "array", "items": _SOURCED_ITEM},
        "questions": {"type": "array", "items": {"type": "string"}},
        "next_step": {"type": "string"},
    },
    "required": ["facts", "hypotheses", "questions", "next_step"],
    "additionalProperties": False,
}

EMAIL_SCHEMA = {
    "type": "object",
    "properties": {
        "subject": {"type": "string"},
        "body": {"type": "string"},
        "facts_used": {"type": "array", "items": _SOURCED_ITEM},
    },
    "required": ["subject", "body", "facts_used"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """You are the sales copilot inside REVORA, a prospecting tool for SDRs and BDRs.

You only know what is in the prospect record you are given. Every fact you state must come from it,
and must cite the ids of the records it comes from (interaction ids like "I12", objection ids like "O3",
"P" for the prospect profile). If something is not in the record, do not state it as a fact: either
leave it out or put it under hypotheses, worded as a hypothesis, with the records that suggest it.
Never invent names, numbers, budgets, dates, competitors or commitments.

Write in English, concisely, for a busy SDR. Notes in the record may be written in French; that is
expected."""

TASKS = {
    "call_brief": (
        "Prepare my next call with this prospect.\n"
        "- facts: what we actually know, each with its sources.\n"
        "- hypotheses: reasonable guesses to verify on the call, each with the records that suggest it.\n"
        "- questions: 3 to 5 questions to ask, based on gaps in what we know.\n"
        "- next_step: one concrete next step to propose at the end of the call.\n"
        "If an objection was raised and a recommended response exists in the playbook, use it."
    ),
    "email_draft": (
        "Draft a short follow-up email to this prospect (under 150 words), in the language of the "
        "latest exchanges. Reference only things that actually happened. Do not promise anything "
        "that is not in the record. Use the playbook response if an objection is open.\n"
        "- subject and body: the email, ready to be reviewed by the SDR. No placeholders except "
        "[Your name] for the signature.\n"
        "- facts_used: the facts from the record the email relies on, each with its sources."
    ),
}

SCHEMAS = {"call_brief": CALL_BRIEF_SCHEMA, "email_draft": EMAIL_SCHEMA}


# ==========================================
# CONTEXTE ENVOYÉ À L'IA
# ==========================================

def build_context(prospect, interactions, objections, playbook, limit=MAX_INTERACTIONS):
    """Données envoyées pour un prospect, avec un identifiant par source.

    interactions : get_interactions (les plus récentes d'abord) ; seules les
    `limit` dernières sont envoyées. Aucune coordonnée personnelle.
    Retourne {"profile", "interactions", "objections", "playbook", "labels"} ;
    labels associe chaque identifiant à un libellé lisible (affichage des sources).
    """

    profile = {
        "id": "P",
        "name": f"{prospect['first_name']} {prospect['last_name']}",
        "company": prospect.get("company_name"),
        "job_title": prospect.get("job_title"),
        "vertical": prospect.get("vertical"),
        "stage": prospect.get("status"),
        "added_on": (prospect.get("created_at_local") or "")[:10] or None,
    }

    labels = {"P": "Prospect profile"}
    sent_interactions = []

    for item in interactions[:limit]:
        source_id = f"I{item['id']}"
        day = item["occurred_at_local"][:10]
        sent_interactions.append({
            "id": source_id,
            "date": item["occurred_at_local"][:16],
            "channel": item["channel"],
            "direction": item["direction"],
            "result": item["event_type"],
            "subject": item.get("subject") or None,
            "notes": item.get("content") or None,
            "next_step": item.get("outcome") or None,
        })
        labels[source_id] = f"{item['channel']} · {day[8:10]}/{day[5:7]}" + (
            f" · {item['subject']}" if item.get("subject") else "")

    sent_objections = []
    used_categories = set()

    for objection in objections:
        source_id = f"O{objection['id']}"
        sent_objections.append({
            "id": source_id,
            "date": (objection.get("occurred_at_local") or "")[:10],
            "category": objection["category"],
            "wording": objection.get("verbatim") or None,
            "status": objection["status"],
        })
        labels[source_id] = f"Objection · {objection['category']}"
        used_categories.add(objection["category"])

    return {
        "profile": profile,
        "interactions": sent_interactions,
        "objections": sent_objections,
        "playbook": {c: r for c, r in (playbook or {}).items() if c in used_categories and r},
        "labels": labels,
    }


def build_prompt(task, context):
    """Message envoyé à l'IA : la tâche, puis le dossier du prospect (sans les libellés internes)."""

    record ={key: value for key, value in context.items() if key != "labels"}

    return f"{TASKS[task]}\n\nProspect record (JSON):\n{json.dumps(record, ensure_ascii=False, indent=1)}"


# ==========================================
# VÉRIFICATION DE LA RÉPONSE
# ==========================================

def _check_items(items, known_ids, require_source):
    """Garde les éléments dont les sources existent vraiment. Retourne (gardés, écartés)."""

    kept, dropped = [], 0

    for item in items or []:
        sources = [s for s in item.get("sources", []) if s in known_ids]

        if (require_source and not sources) or not (item.get("text") or "").strip():
            dropped += 1
            continue

        kept.append({"text": item["text"].strip(), "sources": sources})

    return kept, dropped


def validate_output(task, data, context):
    """Contrôle la réponse : un « fait » sans source réelle est écarté.

    Retourne la réponse nettoyée, avec "dropped" = nombre d'éléments écartés.
    """

    known = set(context["labels"])

    if task == "call_brief":
        facts, dropped_facts = _check_items(data.get("facts"), known, require_source=True)
        hypotheses, dropped_hyp = _check_items(data.get("hypotheses"), known, require_source=False)
        return {
            "facts": facts,
            "hypotheses": hypotheses,
            "questions": [q.strip() for q in data.get("questions", []) if q.strip()],
            "next_step": (data.get("next_step") or "").strip(),
            "dropped": dropped_facts + dropped_hyp,
        }

    facts, dropped = _check_items(data.get("facts_used"), known, require_source=True)
    return {
        "subject": (data.get("subject") or "").strip(),
        "body": (data.get("body") or "").strip(),
        "facts_used": facts,
        "dropped": dropped,
    }


def source_labels(sources, context):
    """Libellés lisibles des sources citées : « Call · 10/11 · Discovery »."""

    return [context["labels"][s] for s in sources if s in context["labels"]]


def estimate_cost(usage, input_price=4.0, output_price=20.0):
    """Coût approximatif en dollars (tarifs Claude Opus 5.5 par million de jetons)."""

    if not usage:
        return None

    return round(usage.get("input_tokens", 0) / 1e6 * input_price
                 + usage.get("output_tokens", 0) / 1e6 * output_price, 4)
