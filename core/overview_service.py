"""Overview (cockpit du SDR) : mise en forme des données existantes.

Ce module n'ajoute aucune donnée et aucune règle métier nouvelle :
  - la priorité vient de pipeline_service.prioritize (règles explicables) ;
  - l'action recommandée est DÉDUITE de la raison de priorité (aucune IA) ;
  - le fil d'activité assemble des événements réellement enregistrés.
"""

from datetime import date, datetime, timedelta

from core.pipeline_service import days_since


# ==========================================
# EN-TÊTE
# ==========================================

def greeting(now=None):
    """« Good morning. » / « Good afternoon. » / « Good evening. » selon l'heure locale."""

    hour = (now or datetime.now()).hour

    if hour < 12:
        return "Good morning."
    if hour < 18:
        return "Good afternoon."
    return "Good evening."


def long_date(today=None):
    """« Sunday 15 November 2026 »."""

    today = today or date.today()

    return f"{today:%A} {today.day} {today:%B %Y}"


# ==========================================
# TODAY'S FOCUS
# ==========================================

def priority_label(points):
    """Niveau lisible à partir des points d'urgence (règles de pipeline_service)."""

    if points >= 3:
        return "High"
    if points >= 2:
        return "Medium"
    return "Low"


def _short(value):
    """"2026-11-13" ou "2026-11-13 10:00:00" -> "13/11" ; vide -> "—"."""

    return datetime.fromisoformat(str(value)[:10]).strftime("%d/%m") if value else "—"


def _due_task(summary, today_iso):
    """La prochaine relance si elle est due aujourd'hui ou en retard, sinon None."""

    due = (summary.get("next_task_due") or "")[:10]

    if summary.get("next_task_title") and due and due <= today_iso:
        return due

    return None


def action_type(item, today=None):
    """Type d'action (blueprint : appeler, email, préparer, relancer), déduit des données.

      - relance due ou en retard            -> "Follow up"
      - jamais contacté                     -> "Call" si téléphone, sinon "Email", sinon "Prepare"
      - inactif                             -> canal du dernier échange (Call, Email, LinkedIn)
    """

    prospect = item.get("prospect") or {}
    summary = item.get("summary") or {}
    today_iso = (today or date.today()).isoformat()

    if _due_task(summary, today_iso):
        return "Follow up"

    last_channel = summary.get("last_channel")

    if summary.get("last_interaction_at") and last_channel in ("Call", "Email", "LinkedIn"):
        return last_channel

    if prospect.get("phone"):
        return "Call"
    if prospect.get("email"):
        return "Email"
    return "Prepare"


def next_action(item, today=None):
    """Action recommandée, déduite uniquement de la raison de priorité."""

    summary = item.get("summary") or {}
    today_iso = (today or date.today()).isoformat()

    if _due_task(summary, today_iso):
        return f"Follow-up: {summary['next_task_title']}"

    kind = action_type(item, today)
    days = days_since(summary.get("last_interaction_at"), today)

    if days is None:
        return {
            "Call": "First contact: call",
            "Email": "First contact: email",
        }.get(kind, "Prepare: find a phone number or an email")

    return f"Re-engage by {kind.lower()}: no touch for {days} days"


def due_label(item, today=None):
    """Échéance lisible : (texte, état) avec état overdue / today / later / none."""

    summary = item.get("summary") or {}
    today = today or date.today()
    due = (summary.get("next_task_due") or "")[:10]

    if not summary.get("next_task_title") or not due:
        return "—", "none"

    late = (today - date.fromisoformat(due)).days

    if late > 0:
        return f"Overdue {late} d", "overdue"
    if late == 0:
        return "Today", "today"
    return f"Due {_short(due)}", "later"


def reason_detail(item, today=None):
    """Raison de la priorité avec sa source et sa date (aucune déduction)."""

    prospect = item.get("prospect") or {}
    summary = item.get("summary") or {}
    today_iso = (today or date.today()).isoformat()
    parts = []

    due = _due_task(summary, today_iso)
    if due:
        created = summary.get("next_task_created_at")
        parts.append(
            f"Follow-up due {_short(due)}" + (f" (scheduled {_short(created)})" if created else "")
        )

    days = days_since(summary.get("last_interaction_at"), today)

    if days is None:
        added = prospect.get("created_at_local") or prospect.get("created_at")
        text = "Never contacted"
        if added:
            text += f" · added {_short(added)}"
        if prospect.get("source"):
            text += f" via {prospect['source']}"
        parts.append(text)
    elif not due:
        channel = (summary.get("last_channel") or "interaction").lower()
        parts.append(f"No touch for {days} d · last {channel} on {_short(summary['last_interaction_at'])}")

    return " · ".join(parts) or " · ".join(item.get("reasons", []))


def focus_rows(ranked, scores, limit=8, today=None):
    """Lignes de « Today's Focus » à partir de prioritize() (déjà trié)."""

    rows = []

    for item in ranked[:limit]:
        prospect = item["prospect"]
        summary = item.get("summary") or {}
        score = scores.get(prospect["id"]) or {}
        due_text, due_state = due_label(item, today)

        rows.append({
            "id": prospect["id"],
            "priority": priority_label(item["points"]),
            "prospect": f"{prospect.get('first_name') or ''} {prospect.get('last_name') or ''}".strip(),
            "company": prospect.get("company_name") or "—",
            "stage": prospect.get("status"),
            "score": score.get("global"),
            "temperature": score.get("temperature"),
            "last_interaction": format_when(summary.get("last_interaction_at"), today) or "Never",
            "action_type": action_type(item, today),
            "next_action": next_action(item, today),
            "due": due_text,
            "due_state": due_state,
            "reason": reason_detail(item, today),
            "task_id": summary.get("next_task_id"),
            "task_title": summary.get("next_task_title"),
        })

    return rows


# ==========================================
# RECENT ACTIVITY
# ==========================================

def format_when(value, today=None):
    """« 14:32 » (aujourd'hui), « Yesterday 10:40 », sinon « 12/11 09:00 ». Vide -> None."""

    if not value:
        return None

    moment = datetime.fromisoformat(str(value))
    today = today or date.today()

    if moment.date() == today:
        return moment.strftime("%H:%M")
    if moment.date() == today - timedelta(days=1):
        return f"Yesterday {moment:%H:%M}"

    return moment.strftime("%d/%m %H:%M")


def _name(record):
    return f"{record.get('first_name') or ''} {record.get('last_name') or ''}".strip()


def build_feed(interactions, objections, prospects, score_changes, limit=10):
    """Fil chronologique des derniers événements enregistrés (plus récent d'abord).

    Événement : {"at", "kind", "title", "detail", "contact_id", "prospect", "company"}.
    Chaque événement est rattaché à un prospect (lien vers sa fiche).
    """

    by_id = {p["id"]: p for p in prospects}
    events = []

    for i in interactions:
        direction = {"Inbound": "in", "Outbound": "out"}.get(i.get("direction"), "")
        events.append({
            "at": i["occurred_at_local"],
            "kind": i["channel"],
            "title": f"{i['channel']} {direction}".strip() + f" · {i['event_type']}",
            "detail": i.get("subject") or "",
            "contact_id": i["contact_id"],
            "prospect": _name(i),
            "company": i.get("company_name") or "",
        })

    for o in objections:
        events.append({
            "at": o["occurred_at_local"],
            "kind": "Objection",
            "title": f"Objection · {o['category']}",
            "detail": o.get("verbatim") or "",
            "contact_id": o["contact_id"],
            "prospect": _name(o),
            "company": o.get("company_name") or "",
        })

    for p in prospects:
        if p.get("created_at_local"):
            events.append({
                "at": p["created_at_local"],
                "kind": "Prospect",
                "title": "New prospect",
                "detail": p.get("source") or "",
                "contact_id": p["id"],
                "prospect": _name(p),
                "company": p.get("company_name") or "",
            })

    for change in score_changes:
        prospect = by_id.get(change["contact_id"])

        if not prospect:
            continue

        events.append({
            "at": change["occurred_at_local"],
            "kind": "Score",
            "title": f"Score {change['previous_score']} → {change['global_score']}",
            "detail": "",
            "contact_id": change["contact_id"],
            "prospect": _name(prospect),
            "company": prospect.get("company_name") or "",
        })

    events.sort(key=lambda e: e["at"], reverse=True)

    return events[:limit]
