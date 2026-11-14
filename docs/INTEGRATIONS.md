# Intégrations HubSpot et Gmail

État : **connecteurs écrits et testés hors ligne** (données fictives, aucun appel réseau).
**Aucun compte n'est connecté.** Documentation vérifiée le 14/11/2026.

## Règles

- Comptes de **test** uniquement. Jamais le CRM ou la boîte d'un employeur sans autorisation écrite.
- Secrets dans `.env` (exclu de Git), jamais dans le code ni dans la base.
- Permissions minimales. Contenu des emails et notes d'appel **non importé** par défaut (`include_content=False`).
- Relancer une synchronisation ne crée jamais de doublon.

## Architecture

```
integrations/base.py              interface commune (authenticate, test_connection,
                                  fetch_events, normalize_event, sync_events)
integrations/http.py              client HTTP (urllib), retries 429/5xx, Retry-After
integrations/config.py            lecture du .env
integrations/hubspot/connector.py appels, emails, contacts
integrations/gmail/connector.py   en-têtes des emails (gmail.metadata)
core/sync_service.py              rattachement aux contacts, déduplication, journal
```

Rattachement d'un événement à un contact, dans l'ordre :
1. identifiant HubSpot (`contacts.hubspot_id`) ;
2. téléphone normalisé, seulement s'il désigne un contact unique (standards partagés) ;
3. email.

Une clé ambiguë passe à la suivante. Sans contact unique, l'événement est compté
« non rattaché » et n'est pas enregistré.

Déduplication :
- même fournisseur + même identifiant externe : contrainte `UNIQUE(provider, external_id)` ;
- même email vu par Gmail **et** HubSpot : même `Message-ID` si les deux l'ont, sinon même contact,
  même sens, même objet (sans « Re: », « Fwd: »…) et moins de 3 minutes d'écart.

## HubSpot

Vérifié dans la documentation officielle :
- recherche `POST /crm/v3/objects/{objet}/search` : `filterGroups`, une seule règle de tri,
  `limit` ≤ 200, pagination `after`, **10 000 résultats max** par requête, **5 requêtes/s** ;
- appels : `hs_call_direction` (INBOUND/OUTBOUND), `hs_call_duration` en **millisecondes**,
  `hs_call_status`, `hs_call_disposition` (GUID ; résultats par défaut connus) ;
- emails : `hs_email_direction` = EMAIL / INCOMING_EMAIL / FORWARDED_EMAIL ;
- lecture du contenu des emails : scope `sales-email-read` ;
- limites : 100 requêtes / 10 s par application (Free/Starter), 190 (Pro/Enterprise).

**Non documenté — à confirmer sur un compte de test :**
- forme de la réponse de `POST /crm/v3/associations/{objet}/contacts/batch/read` ;
- présence d'un `Message-ID` : aucune propriété documentée (lu dans `hs_email_headers` s'il existe) ;
- version d'API : la documentation montre `/crm/v3/objects` et des chemins datés
  (`/crm/objects/2026-09`) ; le préfixe est réglable (`objects_prefix`).

Sources :
[Emails](https://developers.hubspot.com/docs/api-reference/crm-emails-v3/guide) ·
[Calls](https://developers.hubspot.com/docs/api-reference/latest/crm/activities/calls/guide) ·
[Search](https://developers.hubspot.com/docs/api-reference/latest/crm/search-the-crm) ·
[Scopes](https://developers.hubspot.com/docs/apps/legacy-apps/authentication/scopes) ·
[Limites](https://developers.hubspot.com/docs/developer-tooling/platform/usage-guidelines)

## Gmail

Vérifié dans la documentation officielle :
- **toutes** les autorisations de lecture (`gmail.metadata`, `gmail.readonly`, `gmail.modify`,
  `mail.google.com`) sont **restreintes** : une application publique doit passer la vérification
  Google, et un audit de sécurité si les données sont stockées sur un serveur ;
- `gmail.metadata` : en-têtes et libellés, **pas le contenu** ; le paramètre de recherche `q` est
  **interdit** avec ce scope ;
- `messages.list` : `maxResults` 100 par défaut, 500 max ; `messages.get` avec `format=metadata` ;
- synchronisation : complète, puis partielle avec `history.list(startHistoryId)` ;
  **404 = historique expiré** → synchronisation complète.

Choix REVORA : `gmail.metadata` (minimum nécessaire : qui, quand, objet, Message-ID).

**À confirmer sur une boîte de test :** unité de `internalDate` (millisecondes attendues ;
l'en-tête `Date` sert de secours), forme exacte de `messagesAdded` dans l'historique.
**Non vérifié :** une éventuelle exemption de vérification pour une application en mode test
limitée à son développeur (la page des scopes ne le dit pas).

Sources :
[Scopes Gmail](https://developers.google.com/workspace/gmail/api/auth/scopes) ·
[Synchronisation](https://developers.google.com/workspace/gmail/api/guides/sync) ·
[messages.get](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/get) ·
[messages.list](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/list) ·
[history.list](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.history/list)

## Étapes réservées à l'utilisateur (avant tout test réel)

1. HubSpot : créer un compte de **test** (ou développeur), puis une application privée avec les scopes
   minimaux ; copier le jeton dans `.env` (`HUBSPOT_ACCESS_TOKEN`).
2. Gmail : créer un projet Google Cloud, un écran de consentement en mode test, ajouter la boîte de
   **test** comme utilisateur test, générer un jeton OAuth `gmail.metadata` ; renseigner
   `GMAIL_ACCESS_TOKEN` et `GMAIL_USER_EMAIL` dans `.env`.
3. Redémarrer REVORA, puis Settings → Integrations → « Sync now ».

## Pas encore fait

- Flux OAuth complet dans l'application (obtention et renouvellement automatique des jetons).
- Webhooks HubSpot (nécessitent un serveur accessible depuis Internet, FastAPI prévu).
- Écriture des scores vers HubSpot (propriétés personnalisées à créer) : synchronisation
  bidirectionnelle **contrôlée**, à valider avant toute écriture dans le CRM.
- File des événements non rattachés (à revoir manuellement).
