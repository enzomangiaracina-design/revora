# Déployer le pilote REVORA sur Render (phase 12.2, voie A)

> **Pilote = données de démonstration fictives uniquement.** Aucune donnée réelle (Noota, employeur)
> tant que le RGPD, l'hébergement et le fournisseur d'IA n'ont pas été validés.

Ce que le dépôt contient déjà :

| Fichier | Rôle |
|---|---|
| `render.yaml` | Blueprint Render : service web Python, région **Francfort**, disque permanent de 1 Go monté sur `/opt/render/project/src/storage`, contrôle de santé `/_stcore/health`, **pas de déploiement automatique** |
| `deploy/render_start.py` | Au démarrage : crée la base de démo sur le disque si elle manque (jamais d'écrasement), ajoute `REVORA_ADMIN_EMAIL` comme premier manager, puis lance Streamlit sur `0.0.0.0:$PORT` avec les secrets de Render |
| `REVORA_REQUIRE_SIGN_IN=1` | En ligne, REVORA **refuse de s'ouvrir** tant que la vraie connexion n'est pas configurée : jamais de « Signed in as » sans mot de passe sur Internet |

Coût vérifié le 16/11/2026 sur render.com/pricing :
- l'instance de 512 Mo coûte **7 $/mois** ;
- le disque coûte **0,25 $/Go/mois** ;
- soit environ **7,25 $/mois** au total.

## Étapes (toutes faites par vous ; aucune n'est faite par Claude)

### 1. Créer le compte Render
Créez un compte sur render.com et reliez-le à GitHub. Un moyen de paiement est exigé, parce que le disque permanent n'existe pas sur l'offre gratuite.

### 2. Créer le service à partir du Blueprint
1. Dans Render, cliquez sur **New › Blueprint** et choisissez le dépôt `revora`.
2. Render lit `render.yaml` et vous demande trois valeurs :
   - `REVORA_ADMIN_EMAIL` : l'email du compte Google avec lequel vous vous connecterez. Vous deviendrez le premier manager.
   - `REVORA_ADMIN_NAME` : votre nom, tel qu'il apparaîtra dans REVORA.
   - `GEMINI_API_KEY` : facultative. Laissez-la vide pour l'instant. Si vous la remplissez, n'utilisez que des données de démo, parce que l'offre gratuite de Gemini réutilise les données envoyées.
3. Validez. Le premier déploiement démarre.
4. Une fois en ligne, l'adresse affiche **« Sign-in is not configured »**. C'est normal et voulu.

Notez l'adresse du service, par exemple `https://revora-pilot.onrender.com`. L'adresse exacte est affichée par Render.

### 3. Ajouter l'adresse de retour chez Google
Dans la console Google (Google Auth Platform › **Clients**), ouvrez votre client OAuth. Sous **Authorized redirect URIs**, ajoutez :

```
https://<votre-adresse>.onrender.com/oauth2callback
```

Gardez aussi l'adresse `http://localhost:8501/oauth2callback` pour les essais en local. Enfin, dans **Audience › Test users**, vérifiez que votre email y figure.

### 4. Donner les secrets à Render
Dans Render, ouvrez le service, puis **Environment › Secret Files › Add Secret File** :
- **Nom du fichier** : `secrets.toml`.
- **Contenu** : le modèle `.streamlit/secrets.toml.example`, avec :
  - `redirect_uri = "https://<votre-adresse>.onrender.com/oauth2callback"` ;
  - un **nouveau** `cookie_secret`, différent de celui de votre Mac ; pour le générer :
    ```bash
    python3 -c "import secrets; print(secrets.token_urlsafe(32))"
    ```
  - vos `client_id` et `client_secret` Google.

Enregistrez, puis lancez **Manual Deploy › Deploy latest commit**. Render place ce fichier dans `/etc/secrets/secrets.toml`, et REVORA le lit à cet endroit.

### 5. Se connecter
Ouvrez l'adresse du service, puis cliquez sur **Sign in**. Vous entrez comme manager. Ajoutez les autres testeurs dans Settings › Team, avec leur email. Ils doivent aussi figurer dans les « Test users » de Google.

## Mettre à jour le pilote
Le déploiement automatique est **désactivé**. Après un `git push`, rien ne change en ligne tant que vous n'avez pas cliqué sur **Manual Deploy**. Chaque mise à jour coupe le service quelques instants, à cause du disque permanent.

## Sauvegardes en ligne
- **Côté REVORA** : une copie par jour dans `storage/backups/auto/demo/`, les 14 dernières étant gardées. Le journal des erreurs est dans `storage/logs/`.
- **Côté Render** : une copie du disque toutes les 24 heures, gardée 7 jours.

## Arrêter ou supprimer
- **Suspend** arrête le service.
- **Delete** le supprime, **ainsi que son disque**, et donc la base. Faites d'abord une sauvegarde.

## Points à vérifier au premier déploiement
- **La version de Python 3.15.2** (celle des tests) doit être disponible chez Render. Si la construction échoue, mettez `PYTHON_VERSION` sur la version par défaut indiquée dans la documentation de Render (3.14.10 au 16/11/2026).
- **La mémoire de 512 Mo** n'a pas été mesurée. Si le service redémarre en boucle (manque de mémoire), passez au palier supérieur.
- **La forme exacte de `render.yaml`** n'a pas pu être comparée à un exemple officiel copié tel quel. Si Render signale une erreur, notez-la et corrigeons-la ensemble.
