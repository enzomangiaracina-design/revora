"""Timeline unifiée de la fiche prospect (blueprint §5.3).

Assemble, en une seule chronologie, tout ce qui est réellement enregistré
pour un prospect : interactions, relances, objections, changements d'étape,
variations de score et création de la fiche. Aucune donnée n'est déduite.

Chaque événement : {"at", "kind", "title", "detail", "meta", "source"}.
"""

KINDS = ["Interaction", "Follow-up", "Objection", "Stage", "Score", "Prospect"]

from core.activity_service import SOURCE_LABELS  # une seule définition des sources


def _interaction_event(item, format_duration):
    direction = {"Inbound": "in", "Outbound": "out"}.get(item.get("direction"), "")
    detail = " — ".join(part for part in (item.get("subject"), item.get("content")) if part)
    meta = [m for m in (format_duration(item.get("metadata")),
                        f"Next step: {item['outcome']}" if item.get("outcome") else None) if m]

    return {
        "at": item["occurred_at_local"],
        "kind": "Interaction",
        "channel": item["channel"],
        "title": f"{item['channel']} {direction}".strip() + f" · {item['event_type']}",
        "detail": detail,
        "meta": " · ".join(meta),
        "source": SOURCE_LABELS.get(item.get("provider"), item.get("provider") or "Manual"),
    }


def build_timeline(prospect, interactions, tasks, objections, score_history, stage_changes,
                   format_duration=lambda metadata: ""):
    """Liste chronologique (plus récent d'abord) de tous les événements du prospect."""

    events = [_interaction_event(i, format_duration) for i in interactions]

    for task in tasks:
        if not task.get("created_at_local"):
            continue

        status = "done" if task.get("status") != "A faire" else "open"

        events.append({
            "at": task["created_at_local"],
            "kind": "Follow-up",
            "title": f"Follow-up scheduled · {task['title']}",
            "detail": task.get("description") or "",
            "meta": f"Due {task.get('due_at') or 'no date'} · {status}",
            "source": "Manual",
        })

    for objection in objections:
        events.append({
            "at": objection["occurred_at_local"],
            "kind": "Objection",
            "title": f"Objection · {objection['category']}",
            "detail": f"“{objection['verbatim']}”" if objection.get("verbatim") else "",
            "meta": f"Status: {objection['status']} · stage: {objection.get('stage') or '—'}"
                    + (f" · during {objection['interaction_channel'] or 'interaction'}"
                       if objection.get("interaction_at_local") else ""),
            "source": SOURCE_LABELS.get(objection.get("source"), objection.get("source") or "Manual"),
        })

    origin = {"pipeline": "moved in the pipeline", "edit": "changed in the prospect form",
              "stage deleted": "stage deleted, prospect moved"}

    for change in stage_changes:
        events.append({
            "at": change["changed_at_local"],
            "kind": "Stage",
            "title": f"Stage · {change.get('from_stage') or '—'} → {change['to_stage']}",
            "detail": "",
            "meta": origin.get(change["source"], change["source"]),
            "source": "REVORA",
        })

    previous = None
    for row in score_history:  # du plus ancien au plus récent
        if previous is not None and row["global_score"] != previous["global_score"]:
            events.append({
                "at": row["calculated_at_local"],
                "kind": "Score",
                "title": f"Score {previous['global_score']} → {row['global_score']}",
                "detail": "",
                "meta": (f"Fit {row['fit_score'] if row['fit_score'] is not None else 'n/a'} · "
                         f"Engagement {row['engagement_score']} · Intent {row['intent_score']}"),
                "source": "REVORA",
            })
        previous = row

    if prospect.get("created_at_local"):
        events.append({
            "at": prospect["created_at_local"],
            "kind": "Prospect",
            "title": "Prospect created",
            "detail": "",
            "meta": f"Source: {prospect['source']}" if prospect.get("source") else "",
            "source": "REVORA",
        })

    return sorted(events, key=lambda e: e["at"], reverse=True)


def filter_timeline(events, kinds):
    """Garde les événements des types choisis (liste vide = tout)."""

    return [e for e in events if not kinds or e["kind"] in kinds]
