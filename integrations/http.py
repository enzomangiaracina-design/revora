"""Client HTTP commun aux connecteurs, avec nouvelles tentatives (retries).

Choix : la bibliothèque standard (urllib) plutôt qu'une dépendance externe.

Concept (injection de dépendance) : la fonction qui envoie réellement la
requête (`transport`) est un paramètre. En production, c'est `urllib_transport`
qui appelle Internet ; dans les tests, on passe une fausse fonction qui
renvoie des réponses préparées. Les tests n'appellent donc JAMAIS une vraie API.
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request

# Codes HTTP pour lesquels une nouvelle tentative a du sens :
# 429 = trop de requêtes (limite de débit), 5xx = erreur temporaire du serveur.
RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


class IntegrationError(Exception):
    """Erreur d'un connecteur (configuration, authentification, API)."""

    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


def urllib_transport(method, url, headers, body, timeout=30):
    """Envoie une vraie requête HTTP. Retourne (status, en-têtes, corps JSON ou None)."""

    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            return response.status, dict(response.headers), json.loads(raw) if raw else None

    except urllib.error.HTTPError as error:
        raw = error.read()
        try:
            payload = json.loads(raw) if raw else None
        except ValueError:
            payload = {"message": raw.decode(errors="replace")}
        return error.code, dict(error.headers or {}), payload


class HttpClient:
    """Envoie des requêtes JSON avec un jeton d'accès et des retries."""

    def __init__(self, base_url, token, transport=None, max_retries=3, sleep=time.sleep):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.transport = transport or urllib_transport
        self.max_retries = max_retries
        self.sleep = sleep

    def request(self, method, path, params=None, body=None):
        """Retourne le corps JSON de la réponse, ou lève IntegrationError."""

        url = self.base_url + path

        if params:
            url += "?" + urllib.parse.urlencode(params, doseq=True)

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        for attempt in range(self.max_retries + 1):
            status, response_headers, payload = self.transport(method, url, headers, body)

            if 200 <= status < 300:
                return payload or {}

            if status in RETRYABLE_STATUSES and attempt < self.max_retries:
                self.sleep(self._wait_seconds(response_headers, attempt))
                continue

            message = (payload or {}).get("message") or (payload or {}).get("error") or "Unknown error"
            if isinstance(message, dict):
                message = message.get("message", str(message))

            raise IntegrationError(f"HTTP {status} on {method} {path}: {message}", status=status)

        raise IntegrationError(f"Too many retries on {method} {path}")  # pragma: no cover

    @staticmethod
    def _wait_seconds(headers, attempt):
        """Respecte l'en-tête Retry-After s'il existe, sinon attente exponentielle (1, 2, 4 s)."""

        retry_after = {k.lower(): v for k, v in (headers or {}).items()}.get("retry-after")

        try:
            return min(float(retry_after), 60)
        except (TypeError, ValueError):
            return 2 ** attempt
