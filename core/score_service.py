"""Service scoring : relie le moteur (core/scoring.py, pur) à la base.

  - lecture / enregistrement de la configuration (table settings) ;
  - recalcul des scores de tous les prospects ;
  - enregistrement de l'historique (seulement quand un score change) ;
  - aide à la calibration (score moyen par étape).
"""

from collections import defaultdict
from datetime import date

import database
from core import scoring

CONFIG_KEY = "scoring"


def load_config():
    """Configuration du scoring (valeurs par défaut complétées)."""

    return scoring.merge_config(database.get_setting(CONFIG_KEY, {}))


def save_config(config):
    """Valide puis enregistre la configuration. Retourne (succès, message)."""

    config = scoring.merge_config(config)
    errors = scoring.validate_config(config)

    if errors:
        return False, " ".join(errors)

    database.set_setting(CONFIG_KEY, config)

    return True, "Configuration du scoring enregistrée. Scores recalculés."


def refresh_scores(today=None):
    """Recalcule le score de chaque prospect et enregistre les variations.

    Retourne {contact_id: résultat de scoring.compute_scores}.
    """

    today = today or date.today()
    config = load_config()
    closed = {stage["name"] for stage in database.get_stages() if stage["is_closed"]}

    by_contact = defaultdict(list)
    for interaction in database.get_all_interactions():
        by_contact[interaction["contact_id"]].append(interaction)

    results = {}

    for prospect in database.get_all_prospects():
        result = scoring.compute_scores(
            prospect,
            by_contact[prospect["id"]],
            config,
            stage_closed=prospect["status"] in closed,
            today=today,
        )

        database.save_score(
            prospect["id"],
            result["fit"],
            result["engagement"],
            result["intent"],
            result["global"],
            result["explanation"],
        )

        results[prospect["id"]] = result

    return results


def score_changes(history):
    """Ajoute à chaque point d'historique la variation par rapport au précédent."""

    changes = []
    previous = None

    for row in history:
        delta = None if previous is None else row["global_score"] - previous["global_score"]
        changes.append({**row, "delta": delta})
        previous = row

    return changes


def calibration_by_stage(prospects, results, stages):
    """Score global moyen et nombre de prospects par étape du pipeline.

    Première aide à la calibration : si les étapes avancées (rendez-vous…)
    n'ont pas de meilleurs scores que les premières, les pondérations ou
    les points sont à revoir.
    """

    rows = []

    for stage in stages:
        scores = [
            results[p["id"]]["global"]
            for p in prospects
            if p["status"] == stage["name"] and p["id"] in results
        ]

        rows.append({
            "Stage": stage["name"],
            "Prospects": len(scores),
            "Average score": round(sum(scores) / len(scores), 1) if scores else None,
            "Closed": stage["is_closed"],
        })

    return rows
