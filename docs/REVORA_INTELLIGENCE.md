# REVORA Intelligence — conception (AI Copilot + REVORA MEMORY)

> Statut : **vision et architecture cible, non développée**. Ce document fixe la conception et le
> phasage ; aucun code n'a été écrit pour REVORA MEMORY. Rédigé le 15/11/2026 (v0.34.0).
> Signature envisagée : *Your commercial intelligence, evolving with you.*

## 1. Décision produit

Un seul espace dans la navigation : **REVORA Intelligence**. Il remplacera l'entrée « AI Copilot ».

| Onglet | Rôle |
|---|---|
| **Copilot** | Le seul espace conversationnel : questions, analyse de prospects, préparation d'appel, recommandations |
| **Memory & Knowledge** | Consulter ce que REVORA a retenu : souvenirs, habitudes, connaissances commerciales, liens |
| **Personalization** | Valider ou refuser les hypothèses, corriger, supprimer, désactiver une catégorie de mémoire |

- **REVORA MEMORY** est le moteur, invisible, qui tourne en arrière-plan.
- **Le Copilot** est la seule interface avec laquelle on parle.
- Il n'y a ni deuxième assistant, ni deuxième chat.
- Le panneau AI Copilot de la fiche prospect reste en place : c'est le même moteur, appliqué à un prospect.

Inspiration visuelle (maquette « SecondBrain » fournie) :
- **Ce qu'on reprend, le principe des trois colonnes** : la navigation, une liste de contextes (conversations, prospects, sujets) et la conversation au centre, avec les sources visibles et les réponses actionnables (copier, régénérer).
- **Ce qu'on ne reprend pas** : le nom, le logo, les textes ou l'identité graphique.
- **L'identité visuelle** reste celle du brand kit REVORA. Le violet est déjà réservé aux actions et à la sélection, ce qui colle à la maquette.

## 2. Compatibilité avec l'existant

Une bonne partie des fondations existe déjà. Le principe « provenance, faits / hypothèses, validation » est même déjà appliqué par le Copilot.

| Couche de mémoire | Déjà dans REVORA | Manque |
|---|---|---|
| **B. Prospect Memory** | `interactions` (appels, emails, LinkedIn, notes, résultat, prochaine étape), `objections` reliées à l'échange, `tasks`, `stage_changes`, `scores` + `explanation`, fiche 360° et timeline | Engagements, besoins et interlocuteurs extraits des notes comme « souvenirs » sourcés ; recherche plein texte dans les notes |
| **C. Knowledge Memory** | Catégories d'objections, `objection_responses` (playbook), exemples anonymisés, statistiques par verticale, détection d'objections par IA avec citation vérifiée | Lien objection → réponse **utilisée** → résultat ; enseignements par secteur sourcés |
| **A. User Memory** | Style d'email confirmé (`ai_email_style` : langue, ton, signature) = une **préférence confirmée** explicite ; « Not now » du Today's focus avec raison (`focus_snoozes`) = un signal de refus | **Auteur** des actions ; journal des suggestions acceptées / refusées ; détection d'habitudes |
| **D. Workflow Memory** | Dates d'échanges et de relances, ordre des priorités proposé | Date de réalisation des relances (`tasks` n'a pas de `completed_at`) ; auteur |
| **E. Team Memory** | `users` (rôles SDR / Manager), playbook partagé, vue équipe de Performance | Validation par un manager ; notion d'**organisation** |

Composants réutilisables tels quels :
- `ai/providers.py` : choix du fournisseur et sorties JSON imposées.
- `core/copilot_service.py` :
  - contexte avec identifiants de sources (`P`, `I12`, `O3`) ;
  - `validate_output` / `validate_chat` / `validate_objections`, qui écartent ce qui n'est pas sourcé ;
  - la vérification des citations mot pour mot ;
  - la séparation entre faits et hypothèses.
- `database.py` : le seul point d'accès à la base. C'est là que s'appliqueront les permissions.
- Le schéma « suggestion → Add / Dismiss » de la détection d'objections, qui deviendra « hypothèse → valider / refuser ».
- La transparence des données envoyées à l'IA (légendes, ni email ni téléphone transmis).

## 3. Données nécessaires (écarts à combler)

Ces ajouts sont **additifs**, comme les migrations précédentes. Ils sont listés par ordre d'utilité.

1. **Auteur de chaque action** : `created_by` sur `interactions`, `tasks`, `objections` et `stage_changes`. Sans cela, impossible d'apprendre les habitudes d'une personne.
2. **Journal d'événements** (`activity_events`) : qui a fait quoi, quand, sur quel objet. On y range notamment les suggestions IA proposées, acceptées, refusées et corrigées, ainsi que les brouillons gardés.
3. **`tasks.completed_at`** : pour mesurer le vrai rythme de relance.
4. **Réponse utilisée face à une objection** : un lien objection → réponse employée → issue.
5. **Organisation** (`organization_id` partout) : obligatoire avant d'accueillir plusieurs entreprises (phase 12).
6. **Vraie identité** (phase 12) : avec « Signed in as » sans mot de passe, n'importe qui peut prendre le nom d'un autre. **Une mémoire personnelle n'a pas de sens sans authentification.**

## 4. Architecture proposée

### 4.1 Stockage (relationnel, sans base graphe)

```
memory_items      id, organization_id, owner_user_id (NULL = mémoire d'équipe), layer (user/prospect/
                  knowledge/workflow/team), kind, subject_type, subject_id, content (JSON),
                  status (observation / hypothesis / confirmed / rejected / archived),
                  evidence_count, distinct_days, confidence, first_seen, last_seen,
                  created_at, updated_at, review_at
memory_sources    memory_id, source_type (interaction / objection / task / event / user_input),
                  source_id, quote            -> provenance obligatoire (au moins une ligne)
memory_links      from_type, from_id, relation, to_type, to_id, created_by, created_at
                  -> le « réseau de connaissances » (objection —répondue par→ réponse, etc.)
memory_settings   user_id, layer, enabled    -> désactiver une catégorie
```

Les clés étrangères actuelles forment déjà un graphe : interaction → prospect → entreprise, et objection → interaction. `memory_links` ajoute seulement les relations qu'on ne peut pas déduire. **Pas de base graphe dédiée** : des requêtes SQL sur deux ou trois niveaux suffisent.

### 4.2 Memory Engine (en dehors des affichages)

- **Habitudes : des détecteurs statistiques d'abord, pas d'IA.**
  - Exemple : 70 % des appels entre 9 h et 11 h, sur au moins 15 appels répartis sur au moins 5 jours différents.
  - Le résultat est d'abord une **observation**. Elle devient une **hypothèse** proposée à l'utilisateur, puis une **préférence confirmée** seulement s'il la valide.
  - **Jamais à partir d'un événement isolé**, avec des seuils réglables.
- **Contenu des notes : extraction par IA**, avec le même garde-fou que pour les objections :
  - une citation mot pour mot obligatoire ;
  - une source vérifiée ;
  - rien d'enregistré sans validation.
- **Évolution** :
  - `last_seen` et `review_at` font qu'une hypothèse qui n'est plus observée s'efface ;
  - une préférence confirmée est revue périodiquement (« Toujours vrai ? »), sans devenir une règle éternelle.
- **Contradictions** : un nouveau comportement contraire à une préférence confirmée crée une hypothèse « changement ? ». La préférence n'est jamais écrasée en silence.
- **Exécution** : en tâche de fond ou à la demande, **pas à chaque rechargement de Streamlit**, pour des raisons de performance.

### 4.3 Retrieval & Personalization

1. **Les permissions d'abord, dans `database.py`** : organisation, puis propriétaire (ses souvenirs et la mémoire d'équipe), puis catégories activées. On ne compte jamais sur l'IA pour « ne pas regarder ».
2. **Ensuite le tri**, selon le prospect ou la page en cours, la question et la fraîcheur des souvenirs.
3. **La recherche**, en deux temps :
   - SQLite FTS5 (recherche plein texte intégrée) tant que la base reste SQLite ;
   - plus tard, une **recherche sémantique avec pgvector**, une fois sur PostgreSQL.
4. **Les souvenirs entrent dans le contexte du Copilot avec leurs identifiants** (`M45`). Ils sont donc cités comme sources, au même titre que les échanges.

### 4.4 Exemple de question cible

« Quelles réponses ont été utilisées face à l'objection *No budget* dans le secteur SaaS ? »

REVORA :
1. filtre les objections *No budget* des prospects SaaS que l'utilisateur a le droit de voir ;
2. suit les liens objection → réponse utilisée → issue ;
3. affiche les réponses, avec leurs sources et le nombre de cas.

Le Copilot doit préciser que **réponse suivie d'un rendez-vous ne veut pas dire que la réponse a provoqué le rendez-vous**. Les petits échantillons sont signalés (même règle que « Low volume » dans Performance).

## 5. Confidentialité et performance

- **Séparation des mémoires** :
  - la mémoire personnelle n'est visible que par son propriétaire, **y compris face à un manager** ;
  - la vue équipe de Performance montre des résultats, pas les habitudes privées.
- **Droit du travail et RGPD** : analyser les habitudes d'un salarié (horaires, rythme) peut être assimilé à de la surveillance. Il faut :
  - informer clairement l'utilisateur ;
  - limiter l'usage à son propre bénéfice ;
  - lui donner l'accès, la correction et la suppression ;
  - fixer des durées de conservation.
  **À faire valider juridiquement avant toute utilisation réelle.**
- **Fournisseur d'IA** : l'offre gratuite de Gemini utilise les données envoyées pour améliorer ses produits. **Elle est interdite pour la mémoire et pour les vraies données** ; il faut une offre payante sans réutilisation des données, ou Claude.
- **Minimisation** : pas d'email, de téléphone ni d'URL dans le texte des souvenirs, comme pour le Copilot aujourd'hui.
- **Provenance et dates** : chaque souvenir a au moins une source, une date de création, une date de mise à jour et un statut. Une hypothèse est toujours affichée comme telle.
- **Performance** : les calculs se font en tâche de fond avec mise en cache, et la recherche est indexée. Les coûts de l'IA et des embeddings (représentations numériques du texte pour la recherche sémantique) doivent être estimés, puis plafonnés.

## 6. Phasage et place dans la roadmap

| Étape | Contenu | Prérequis | Base |
|---|---|---|---|
| **I0 — Regroupement** | L'entrée « AI Copilot » devient **REVORA Intelligence** avec les 3 onglets ; Copilot = chat actuel | Aucun | SQLite |
| **Fondations mémoire** | `created_by`, journal d'événements, `tasks.completed_at`, Add / Dismiss enregistrés | Aucun (additif) | SQLite |
| **M1 — Interaction Memory** | Recherche plein texte dans les échanges ; souvenirs prospect (besoins, engagements, interlocuteurs) extraits avec citation et validation | Fondations | SQLite (FTS5) |
| **M2 — User Memory** | Détecteurs d'habitudes ; hypothèse → validation ; onglet Personalization | **Vraie connexion** (phase 12.1) | SQLite |
| **M3 — Knowledge Memory** | Liens objection → réponse → issue ; enseignements par secteur sourcés | M1 | SQLite, puis PostgreSQL |
| **M4 — Personalized Copilot** | Souvenirs autorisés injectés dans le contexte et cités | M2, M3 | PostgreSQL + pgvector conseillés |
| **M5 — Team Memory** | Pratiques validées par un manager ; isolation par organisation | Organisations (phase 12) | PostgreSQL |

Ordre conseillé dans la roadmap globale :
1. On termine d'abord les fondations en cours : phase 12.1 (vraie connexion en local), identité visuelle, ergonomie.
2. Viennent ensuite I0 et les fondations mémoire, qui sont peu risquées.
3. M1 et M2 peuvent tourner sur SQLite.
4. **À partir de M3 / M4, la mémoire justifie le passage à PostgreSQL + pgvector** (la voie B de la phase 12). Le pilote SQLite (voie A) reste valable d'ici là.

## 7. Décisions ouvertes

1. Durées de conservation par couche : par exemple, une hypothèse non confirmée s'efface au bout de 90 jours.
2. Seuils d'apprentissage : nombre minimal d'événements et de jours distincts.
3. Qui valide la Team Memory : un manager seul, ou plusieurs ?
4. Le fournisseur d'IA autorisé pour les vraies données.
5. Une visualisation du réseau de connaissances (graphe interactif) est-elle utile, ou une liste de liens suffit-elle ? Un graphe demanderait un composant dédié hors Streamlit standard.
