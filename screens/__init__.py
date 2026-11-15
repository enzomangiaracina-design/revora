"""Pages de l'application REVORA (une page = un module avec render(ctx))."""

from dataclasses import dataclass, field


@dataclass
class AppContext:
    """Données chargées une fois par affichage et partagées par les pages."""

    prospects: list
    stage_names: list
    scores: dict
    users: list = field(default_factory=list)   # équipe (phase 11)
    user: dict | None = None                    # utilisateur actif (« Signed in as » ou vraie connexion)
    auth: bool = False                          # vraie connexion activée (phase 12.1)
