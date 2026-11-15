"""Pages de l'application REVORA (une page = un module avec render(ctx))."""

from dataclasses import dataclass


@dataclass
class AppContext:
    """Données chargées une fois par affichage et partagées par les pages."""

    prospects: list
    stage_names: list
    scores: dict
