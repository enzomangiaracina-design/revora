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

from core.activity_service import TASK_DONE

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
expected. REVORA is the SDR's internal tool, not the product being sold: never mention REVORA to the
prospect, and do not name the product unless the record names it."""

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
        "Draft a short follow-up email to this prospect (under 150 words). Reference only things that "
        "actually happened. Do not promise anything that is not in the record. Use the playbook "
        "response if an objection is open.\n"
        "- subject and body: the email, ready to be reviewed by the SDR. Write the body in 2 to 4 short "
        "paragraphs separated by a blank line (greeting on its own line, sign-off on its own lines). "
        "Check spelling carefully. No placeholders except [Your name] for the signature.\n"
        "- facts_used: the facts from the record the email relies on, each with its sources."
    ),
}

# ---------- Style des emails (réglage « ai_email_style », modifiable dans Settings) ----------

SETTING_EMAIL_STYLE = "ai_email_style"

EMAIL_LANGUAGES = ["Auto", "English", "French"]
EMAIL_TONES = ["Formal", "Friendly"]
DEFAULT_EMAIL_STYLE = {"language": "Auto", "tone": "Formal", "signature": ""}


def email_style(saved=None):
    """Style complet : les valeurs enregistrées, complétées par les valeurs par défaut."""

    style = {**DEFAULT_EMAIL_STYLE, **(saved or {})}

    if style["language"] not in EMAIL_LANGUAGES:
        style["language"] = DEFAULT_EMAIL_STYLE["language"]
    if style["tone"] not in EMAIL_TONES:
        style["tone"] = DEFAULT_EMAIL_STYLE["tone"]

    style["signature"] = (style.get("signature") or "").strip()
    return style


def email_instructions(style):
    """Consignes de style ajoutées à la demande de brouillon d'email."""

    style = email_style(style)
    language = ("the language of the latest exchanges (English if there are none)"
                if style["language"] == "Auto" else style["language"])
    lines = [f"Style: write the email in {language}."]

    if style["tone"] == "Formal":
        lines.append("Tone: formal and polite. In French, always use « vous » (never « tu »).")
    else:
        lines.append("Tone: warm and friendly, still professional. In French, use « vous » unless the "
                     "record shows that the SDR already uses « tu » with this prospect.")

    if style["signature"]:
        lines.append(f"Sign the email exactly as: {style['signature']} (instead of [Your name]).")

    return "\n".join(lines)


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


def build_prompt(task, context, style=None):
    """Message envoyé à l'IA : la tâche (et le style pour un email), puis le dossier du prospect."""

    record = {key: value for key, value in context.items() if key != "labels"}
    instructions = TASKS[task]

    if task == "email_draft":
        instructions += "\n" + email_instructions(style)

    return f"{instructions}\n\nProspect record (JSON):\n{json.dumps(record, ensure_ascii=False, indent=1)}"


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


# ==========================================
# PHASE 10.2 : CHAT SUR TOUTE LA BASE
# ==========================================

MAX_PROSPECTS = 200
NOTES_EXCERPT = 200
CHAT_HISTORY = 6

CHAT_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "facts": {"type": "array", "items": _SOURCED_ITEM},
        "hypotheses": {"type": "array", "items": _SOURCED_ITEM},
        "out_of_scope": {"type": "boolean"},
    },
    "required": ["answer", "facts", "hypotheses", "out_of_scope"],
    "additionalProperties": False,
}

CHAT_SYSTEM_PROMPT = """You are the sales copilot inside REVORA, a prospecting tool for SDRs and BDRs.
You answer the SDR's questions about their own prospects, interactions, follow-ups and objections,
using ONLY the database snapshot you are given (JSON). Today's date is in the snapshot.

Rules:
- Every fact in your answer must appear in "facts", each with the ids of the records it comes from
  (prospects "P12", interactions "I34", objections "O5"). Never state anything that is not in the snapshot.
- Reasonable guesses go in "hypotheses", worded as hypotheses, with the records that suggest them.
- "answer": a short, direct answer for a busy SDR (bullet points when listing prospects). It must only
  restate the facts and hypotheses you list. Do not write record ids (P12, I34…) in the answer:
  name people and companies instead; the sources are shown separately.
- If the snapshot does not contain what is needed, say so plainly instead of guessing.
- If the question has nothing to do with this sales data, set out_of_scope to true and say briefly
  that you can only help with the REVORA data.
- You cannot change anything in REVORA: never claim you did.
- Answer in the language of the question. Notes may be written in French; that is expected."""


def build_global_context(prospects, scores, interactions, objections, tasks, stages,
                         priority_ids=(), today=None, limit=MAX_PROSPECTS):
    """Instantané de la base envoyé au chat, avec un identifiant par source.

    prospects    : get_all_prospects ; scores : {contact_id: résultat de scoring}
    interactions : get_all_interactions ; objections : get_objections ; tasks : get_all_tasks
    priority_ids : prospects prioritaires (envoyés en premier si la base dépasse `limit`).
    Jamais envoyé : email, téléphone, URL LinkedIn.
    Retourne {"snapshot", "labels", "contacts", "truncated"} :
    labels   : identifiant -> libellé lisible ; contacts : identifiant -> contact_id.
    """

    from collections import Counter
    from datetime import date

    today = today or date.today()
    closed = {s["name"] for s in stages if s["is_closed"]}
    names = {p["id"]: f"{p['first_name']} {p['last_name']}" for p in prospects}

    latest = {}
    for item in interactions:                       # les plus récentes d'abord
        latest.setdefault(item["contact_id"], item)

    open_objections = {}
    for objection in objections:
        if objection["status"] == "Open":
            open_objections.setdefault(objection["contact_id"], []).append(objection)

    next_task = {}
    for task in sorted((t for t in tasks if t["status"] != TASK_DONE),
                       key=lambda t: (t["due_at"] is None, t["due_at"] or "")):
        next_task.setdefault(task["contact_id"], task)

    priority = [pid for pid in priority_ids if pid in names]
    rest = sorted((p["id"] for p in prospects if p["id"] not in set(priority)),
                  key=lambda pid: latest.get(pid, {}).get("occurred_at_local") or "", reverse=True)
    order = (priority + rest)[:limit]
    by_id = {p["id"]: p for p in prospects}

    labels, contacts, rows = {}, {}, []

    for pid in order:
        p = by_id[pid]
        source_id = f"P{pid}"
        labels[source_id] = f"{names[pid]} · {p.get('company_name') or '—'}"
        contacts[source_id] = pid
        result = scores.get(pid) or {}
        row = {
            "id": source_id,
            "name": names[pid],
            "company": p.get("company_name"),
            "vertical": p.get("vertical"),
            "job_title": p.get("job_title"),
            "stage": p.get("status"),
            "stage_closed": p.get("status") in closed,
            "owner": p.get("owner") or None,
            "score": result.get("global"),
            "temperature": result.get("temperature"),
            "last_touch": None,
            "next_follow_up": None,
            "open_objections": [],
        }

        touch = latest.get(pid)
        if touch:
            iid = f"I{touch['id']}"
            day = touch["occurred_at_local"][:10]
            labels[iid] = f"{touch['channel']} · {day[8:10]}/{day[5:7]} · {names[pid]}"
            contacts[iid] = pid
            notes = (touch.get("content") or "").strip()
            row["last_touch"] = {
                "id": iid, "date": day, "channel": touch["channel"], "direction": touch["direction"],
                "result": touch["event_type"], "subject": touch.get("subject") or None,
                "notes_excerpt": notes[:NOTES_EXCERPT] + ("…" if len(notes) > NOTES_EXCERPT else "") or None,
                "next_step": touch.get("outcome") or None,
            }

        task = next_task.get(pid)
        if task:
            row["next_follow_up"] = {"due": task["due_at"], "title": task["title"],
                                     "overdue": bool(task["due_at"] and task["due_at"] < today.isoformat())}

        for objection in open_objections.get(pid, []):
            oid = f"O{objection['id']}"
            labels[oid] = f"Objection · {objection['category']} · {names[pid]}"
            contacts[oid] = pid
            row["open_objections"].append({"id": oid, "category": objection["category"],
                                           "date": (objection.get("occurred_at_local") or "")[:10]})

        rows.append(row)

    snapshot = {
        "today": today.isoformat(),
        "totals": {
            "prospects": len(prospects),
            "prospects_in_snapshot": len(rows),
            "by_stage": dict(Counter(p.get("status") for p in prospects)),
            "overdue_follow_ups": sum(1 for r in rows if (r["next_follow_up"] or {}).get("overdue")),
            "objections_by_category": dict(Counter(o["category"] for o in objections)),
        },
        "prospects": rows,
    }

    return {"snapshot": snapshot, "labels": labels, "contacts": contacts,
            "truncated": len(prospects) > len(rows)}


def build_chat_prompt(question, history, context):
    """Message envoyé au chat : l'instantané, les derniers échanges du chat, puis la question."""

    lines = ["Database snapshot (JSON):", json.dumps(context["snapshot"], ensure_ascii=False, indent=1)]

    recent = history[-CHAT_HISTORY:]
    if recent:
        lines.append("\nEarlier in this conversation:")
        lines += [f"{m['role'].upper()}: {m['content']}" for m in recent]

    lines.append(f"\nQuestion: {question}")

    return "\n".join(lines)


def validate_chat(data, context):
    """Contrôle la réponse du chat : faits sans source réelle écartés.

    Retourne {"answer", "facts", "hypotheses", "out_of_scope", "dropped", "prospects"} ;
    prospects = contact_id des prospects cités (pour les boutons « Open »), sans doublon.
    """

    known = set(context["labels"])
    facts, dropped_facts = _check_items(data.get("facts"), known, require_source=True)
    hypotheses, dropped_hyp = _check_items(data.get("hypotheses"), known, require_source=False)

    cited = []
    for item in facts + hypotheses:
        for source in item["sources"]:
            pid = context["contacts"].get(source)
            if pid is not None and pid not in cited:
                cited.append(pid)

    return {
        "answer": (data.get("answer") or "").strip(),
        "facts": facts,
        "hypotheses": hypotheses,
        "out_of_scope": bool(data.get("out_of_scope")),
        "dropped": dropped_facts + dropped_hyp,
        "prospects": cited,
    }


# ==========================================
# PHASE 8 : DÉTECTION DES OBJECTIONS DANS LES NOTES
# ==========================================
# L'IA SUGGÈRE seulement : rien n'est enregistré sans la confirmation du
# commercial (bouton « Add »). Garde-fou principal : la formulation proposée
# doit se retrouver MOT POUR MOT dans les notes de l'échange cité, sinon la
# suggestion est écartée (impossible d'inventer une objection).

OBJECTION_SCHEMA = {
    "type": "object",
    "properties": {
        "objections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "interaction": {"type": "string"},
                    "category": {"type": "string"},
                    "wording": {"type": "string"},
                    "why": {"type": "string"},
                },
                "required": ["interaction", "category", "wording", "why"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["objections"],
    "additionalProperties": False,
}

OBJECTION_SYSTEM_PROMPT = """You help an SDR spot sales objections in their own interaction notes.

An objection is a reason the PROSPECT gave for not moving forward (budget, timing, already equipped,
not the decision maker, price, competitor, no need…). The SDR's own actions, plans and questions are
not objections. Only report objections that are actually expressed in the notes: never infer one
that is not written.

For each objection:
- interaction: the id of the interaction it appears in (like "I12").
- category: one of the given categories if one fits; otherwise a short new category in English.
- wording: an EXACT quote copied character for character from that interaction's subject or notes
  (keep the original language, typically French). Do not translate, rephrase or shorten words.
- why: one short sentence in English explaining why this is an objection.
Skip objections already recorded for the same interaction with the same category.
If there is no objection, return an empty list."""


def _normalize(text):
    """Texte comparable : minuscules, apostrophes et guillemets unifiés, espaces réduits."""

    text = (text or "").casefold()
    for fancy, plain in (("’", "'"), ("‘", "'"), ("“", '"'), ("”", '"'), ("«", '"'), ("»", '"')):
        text = text.replace(fancy, plain)

    return " ".join(text.split())


def build_objection_context(interactions, objections, categories, limit=MAX_INTERACTIONS):
    """Échanges à analyser (ceux qui ont des notes), objections déjà saisies et catégories.

    interactions : get_interactions (les plus récentes d'abord) ; seules les
    `limit` dernières avec un sujet ou des notes sont envoyées.
    Retourne {"interactions", "recorded", "categories", "labels", "texts"} ;
    texts garde le texte de chaque échange pour vérifier les citations.
    """

    sent, labels, texts = [], {}, {}

    for item in interactions:
        if len(sent) >= limit:
            break

        if not (item.get("content") or "").strip() and not (item.get("subject") or "").strip():
            continue

        source_id = f"I{item['id']}"
        day = item["occurred_at_local"][:10]
        sent.append({
            "id": source_id,
            "date": item["occurred_at_local"][:16],
            "channel": item["channel"],
            "direction": item["direction"],
            "subject": item.get("subject") or None,
            "notes": item.get("content") or None,
        })
        labels[source_id] = f"{item['channel']} · {day[8:10]}/{day[5:7]}" + (
            f" · {item['subject']}" if item.get("subject") else "")
        texts[source_id] = f"{item.get('subject') or ''}\n{item.get('content') or ''}"

    recorded = [
        {"interaction": f"I{o['interaction_id']}", "category": o["category"]}
        for o in objections if o.get("interaction_id") and f"I{o['interaction_id']}" in labels
    ]

    return {"interactions": sent, "recorded": recorded, "categories": list(categories),
            "labels": labels, "texts": texts}


def build_objection_prompt(context):
    """Message envoyé à l'IA : les catégories, les objections déjà saisies et les échanges."""

    record = {key: context[key] for key in ("categories", "recorded", "interactions")}

    return ("Find the objections expressed by the prospect in these interactions.\n\n"
            f"Data (JSON):\n{json.dumps(record, ensure_ascii=False, indent=1)}")


def validate_objections(data, context):
    """Garde les suggestions vérifiables. Retourne {"suggestions", "dropped"}.

    Une suggestion est écartée si : l'échange cité n'a pas été envoyé, la
    formulation ne figure pas mot pour mot dans ses notes, la catégorie est
    vide, ou elle est déjà enregistrée (même échange, même catégorie).
    """

    known = {c.casefold(): c for c in context["categories"]}
    taken = {(r["interaction"], r["category"].casefold()) for r in context["recorded"]}
    suggestions, dropped = [], 0

    for item in data.get("objections") or []:
        source = (item.get("interaction") or "").strip()
        wording = (item.get("wording") or "").strip().strip('"«» ')
        category = (item.get("category") or "").strip()
        category = known.get(category.casefold(), category)       # « no budget » -> « No budget »

        quoted = wording and _normalize(wording) in _normalize(context["texts"].get(source, ""))
        key = (source, category.casefold())

        if source not in context["labels"] or not quoted or not category or key in taken:
            dropped += 1
            continue

        taken.add(key)                                              # pas deux fois la même
        suggestions.append({
            "source": source,
            "interaction_id": int(source[1:]),
            "label": context["labels"][source],
            "category": category,
            "wording": wording,
            "why": (item.get("why") or "").strip(),
        })

    return {"suggestions": suggestions, "dropped": dropped}
