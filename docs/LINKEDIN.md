# LinkedIn dans REVORA

État : **saisie manuelle uniquement.** REVORA ne se connecte pas à LinkedIn, ne visite aucune page
LinkedIn et n'automatise aucune action. Documentation officielle vérifiée le 15/11/2026.

## Ce que REVORA permet

- **URL du profil LinkedIn** sur chaque prospect (formulaire, import CSV, fiche, liste).
  L'URL est mise en forme (`https://www.linkedin.com/in/<identifiant>`) et sert à détecter
  les doublons. Le lien « Open profile » s'ouvre dans **votre** navigateur.
- **Actions LinkedIn** dans le formulaire d'interaction (type *LinkedIn*) :
  - *Connection request sent* (sortant), *Connection accepted* (entrant : c'est le prospect qui agit),
    *InMail sent* (sortant) — le sens est fixé automatiquement ;
  - messages : type *LinkedIn* avec un résultat classique (*Completed*, *Positive response*…).
- **Scoring** : une invitation acceptée vaut 10 points d'Engagement (plafond 10) ; une réponse
  LinkedIn reste à 15 (plafond 30). Une invitation acceptée **n'est pas** une réponse.
- **Performance** : invitations envoyées, taux d'acceptation, messages LinkedIn envoyés.

## Pourquoi pas de connexion automatique

Vérifié dans la documentation officielle :

- Les seules autorisations ouvertes à tous les développeurs sont *Sign in with LinkedIn*
  (nom, titre, photo et email **du membre connecté**) et *Share on LinkedIn* (publier pour lui).
  Aucune autorisation ouverte ne permet de lire les **relations, la messagerie ou les profils
  d'autres membres**.
- L'API Sales Navigator (SNAP), qui couvre la prospection (affichage de profils, messages, synchronisation
  CRM), est réservée aux partenaires, et LinkedIn indique ne plus accepter de nouveaux partenaires.
- Les conditions d'utilisation (section 8.2) interdisent le scraping, les robots, les extensions de
  navigateur et toute méthode automatisée pour accéder au service, envoyer des messages ou ajouter
  des contacts ; les comptes concernés peuvent être restreints ou fermés.

Sources :
[Getting access](https://learn.microsoft.com/en-us/linkedin/shared/authentication/getting-access) ·
[Sign In with LinkedIn (OpenID Connect)](https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/sign-in-with-linkedin-v2) ·
[Sales Navigator Application Platform](https://learn.microsoft.com/en-us/linkedin/sales/) ·
[User Agreement](https://www.linkedin.com/legal/user-agreement) ·
[Prohibited software and extensions](https://www.linkedin.com/help/linkedin/answer/a1341387)

## Ce qui pourrait changer plus tard

- Si votre entreprise dispose d'une intégration Sales Navigator **officielle** (par exemple
  via HubSpot), les activités LinkedIn pourraient arriver par ce canal — à vérifier le moment venu.
- « Sign in with LinkedIn » pourrait servir à la connexion des utilisateurs de REVORA (phase 11),
  sans accès aux prospects.
