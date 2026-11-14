"""Interface commune à tous les connecteurs externes (HubSpot, Gmail, Noota, LinkedIn).

Concept : une "classe abstraite" définit les méthodes que chaque connecteur
DOIT fournir, sans les implémenter. Ainsi, le reste de REVORA (activités,
scoring) peut traiter tous les fournisseurs de la même façon, sans dépendre
de leurs détails techniques.

Aucun connecteur concret n'existe encore.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class NormalizedEvent:
    """Une interaction convertie au format interne de REVORA.

    Le couple (provider, external_id) identifie l'événement de façon unique :
    c'est ce qui rend la synchronisation idempotente (pas de doublon si le même
    événement est reçu deux fois).
    """

    provider: str          # "hubspot", "gmail", "noota", "linkedin"
    external_id: str       # identifiant de l'événement chez le fournisseur
    channel: str           # "Call", "Email", "LinkedIn", "Note"
    direction: str         # "Outbound", "Inbound", "Internal"
    event_type: str        # ex. "Email sent", "Call completed"
    occurred_at: datetime
    subject: str | None = None
    content: str | None = None
    # Informations servant au rapprochement avec un contact (CRM, téléphone, email)
    match_keys: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


class BaseConnector(ABC):
    """Contrat que chaque connecteur doit respecter."""

    provider = None  # à définir dans chaque connecteur, ex. "hubspot"

    @abstractmethod
    def authenticate(self):
        """Obtient ou rafraîchit l'autorisation (OAuth) auprès du fournisseur."""

    @abstractmethod
    def test_connection(self):
        """Vérifie que la connexion fonctionne. Retourne True ou False."""

    @abstractmethod
    def fetch_events(self, since=None):
        """Récupère les événements bruts depuis une date (synchronisation incrémentale)."""

    @abstractmethod
    def normalize_event(self, raw_event):
        """Convertit un événement brut du fournisseur en NormalizedEvent."""

    def sync_events(self, since=None):
        """Récupère puis normalise les événements.

        L'enregistrement en base (avec déduplication) sera ajouté plus tard,
        avec gestion des erreurs, des retries et des logs de synchronisation.
        """

        return [self.normalize_event(raw) for raw in self.fetch_events(since)]
