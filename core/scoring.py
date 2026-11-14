"""Moteur de scoring de REVORA — version de départ.

Pour l'instant, ce module calcule uniquement le SCORE GLOBAL à partir des
trois dimensions déjà calculées :

    global = 0,35 × Fit + 0,40 × Engagement + 0,25 × Intent

Le calcul de chaque dimension à partir des interactions (déduplication,
plafonds, décroissance temporelle, historique, explications) viendra en phase 5.
Les pondérations sont provisoires et configurables.
"""

# Pondérations indicatives du cahier des charges (leur somme doit valoir 1).
DEFAULT_WEIGHTS = {
    "fit": 0.35,
    "engagement": 0.40,
    "intent": 0.25,
}


def _check_score(name, value):
    """Vérifie qu'un score est un nombre compris entre 0 et 100."""

    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TypeError(f"Le score {name} doit être un nombre.")

    if not 0 <= value <= 100:
        raise ValueError(f"Le score {name} doit être compris entre 0 et 100.")


def compute_global_score(fit, engagement, intent, weights=None):
    """Calcule le score global (sur 100) d'un prospect.

    Paramètres :
        fit, engagement, intent : scores sur 100.
        weights : dictionnaire optionnel {"fit": ..., "engagement": ..., "intent": ...}.
                  Si absent, DEFAULT_WEIGHTS est utilisé.

    Retourne un nombre arrondi à 1 décimale.
    """

    weights = weights or DEFAULT_WEIGHTS

    if set(weights) != {"fit", "engagement", "intent"}:
        raise ValueError("Les pondérations doivent contenir fit, engagement et intent.")

    if abs(sum(weights.values()) - 1) > 1e-9:
        raise ValueError("La somme des pondérations doit être égale à 1.")

    _check_score("fit", fit)
    _check_score("engagement", engagement)
    _check_score("intent", intent)

    total = (
        weights["fit"] * fit
        + weights["engagement"] * engagement
        + weights["intent"] * intent
    )

    return round(total, 1)
