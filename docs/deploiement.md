# Premier déploiement : l'agent d'essai

But : l'agent `clients/essai-megga.yaml` répond sur WhatsApp, au numéro de l'app « Alix MEGGA », en zone Europe. Alix FSP, son numéro (+1 650-710-7070) et le routeur `megga-whatsapp` ne changent pas : autre app, autre webhook.

Aucun secret ne passe par Claude ni par le dépôt : chacun se saisit en masqué.

## Avant (Julien, une seule fois)

1. **Meta** : le numéro de l'essai est le +41 22 567 04 07 (Telnyx). Le 15.11.2026, il a été ajouté sur un compte WhatsApp « MEGGA » à part, dans le portefeuille MEGGA, puis vérifié par appel (renvoyé chez Telnyx vers le mobile de Julien) et inscrit. Reste :
   - fait : l'app « Alix MEGGA » (4746973982197378, portefeuille MEGGA, usage WhatsApp) est créée, et le compte « MEGGA » lui envoie ses événements. Alix FSP n'a pas bougé : son app garde son webhook et ses comptes ;
   - publier l'app (elle est en développement) ;
   - garder sa clé secrète (Paramètres, De base) ;
   - créer un jeton d'utilisateur système (MEGGA Agents) ; il doit avoir l'app, le compte WhatsApp ET le compte de messagerie « MEGGA » en accès total, sinon Meta ne transmet rien à l'agent (constaté le 15.11.2026) ;
   - ajouter un moyen de paiement au compte « MEGGA » (sans lui, les modèles Meta ne partent pas).
2. **Neon** : fait le 15.11.2026. Le projet `calm-king-39242423` (AWS Francfort, Postgres 18) est lié au dépôt par `neon init`. Ses adresses sont dans `.env.local`, jamais suivi par git ; connexion vérifiée sans les afficher.
3. **Cloudflare** :
   - vérifier que le compte est en Workers Paid (obligatoire pour les conteneurs) ;
   - créer un jeton d'API (Workers, Containers, D1, Durable Objects en écriture) ;
   - le poser dans les secrets GitHub du dépôt, sous `CLOUDFLARE_API_TOKEN`, avec `CLOUDFLARE_ACCOUNT_ID`.

## Sur « Fusionne et déploie »

4. **Claude** : créer l'annuaire et reporter son identifiant dans `porte/wrangler.jsonc` (petite PR) :
   ```bash
   cd porte && npx wrangler d1 create megga-agents-annuaire --jurisdiction eu
   ```
5. **Claude** : lancer le déploiement (Actions, « déployer », en écrivant « Fusionne et déploie »).
6. **Julien** : poser les secrets du Worker, saisie masquée :
   ```bash
   scripts/secrets_worker.sh
   ```
   Le jeton de vérification du webhook arrive dans le presse-papiers ; le jeton d'administration va dans le trousseau.
7. **Julien** : dans l'app Meta, Webhooks :
   - adresse : `https://megga-agents.<sous-domaine>.workers.dev/meta` ;
   - jeton : coller le presse-papiers ;
   - s'abonner au champ `messages`.
8. **Claude** : inscrire l'agent d'essai dans l'annuaire. Puis **Julien** : poser l'adresse de sa base Neon (saisie masquée) :
   ```bash
   .venv/bin/python scripts/inscrire_client.py clients/essai-megga.yaml
   ```
   ```bash
   scripts/secrets_client.sh essai-megga https://megga-agents.<sous-domaine>.workers.dev .env.local
   ```
   L'adresse est lue dans `.env.local` (celle sans le regroupeur de connexions de Neon, mieux adaptée à un conteneur qui garde ses connexions), sans s'afficher.
9. **Julien** : écrire au numéro, puis envoyer un vocal. Le premier message réveille le conteneur (quelques secondes).

## Revenir en arrière

Dans l'app Meta, retirer l'adresse du webhook : plus rien n'arrive à la porte. Ou supprimer le Worker `megga-agents`. Alix FSP n'est pas concernée.

## Les versions de l'image (lot 6)

Une seule image, construite une fois par version, signée, la même partout : Cloudflare, la zone suisse, chez le client.

**La version** est celle de `pyproject.toml`. Chaque conteneur la montre sur `/sante`, avec le commit d'où vient l'image et la version de ses tables. Chez Cloudflare, le commit vient de l'étiquette du déploiement (`wrangler deploy --tag <commit>`) :

```json
{"ok": true, "version": "0.2.0", "revision": "<commit>", "config": 1, "schema": 1}
```

**Deux versions soutenues à la fois**, la dernière et la précédente. Les migrations de nos tables se jouent au démarrage (`stockage.migrer`) et restent additives : une image démarre aussi sur une base migrée par la version suivante, pour qu'un retour arrière soit toujours possible. Au-delà, elle refuse de démarrer.

### Une seule fois : la clé de signature (Julien)

```bash
scripts/cle_signature.sh
```

Le mot de passe de la clé se saisit en masqué. La clé privée et son mot de passe vont dans les secrets GitHub du dépôt, rien ne s'affiche ; seule la clé publique reste, dans `socle/cosign.pub`, à commiter. Il faut `cosign` et `gh` (`brew install cosign gh`).

### Une seule fois : la clé de pilotage (Julien)

Elle signe les ordres que l'atelier envoie aux installations hors Cloudflare (lot 6.3), distincte de la clé des licences :

```bash
.venv/bin/python scripts/pilotage.py cle
```

La clé privée va dans le trousseau, rien ne s'affiche ; la clé publique dans `noyau/pilotage.pub`, à commiter : elle part dans l'image. Puis, la porte déployée, la remettre à l'atelier (sans l'afficher ; il redémarre) :

```bash
.venv/bin/python scripts/pilotage.py poser https://megga-agents.api-963.workers.dev
```

`GET /atelier/installations` dit alors `"cle_pilotage": true`. Une installation se met en service avec la clé publique qu'elle remet (`python -m pilote cle`, chez le client) :

```bash
.venv/bin/python scripts/pilotage.py installation <id-du-client> https://megga-agents.api-963.workers.dev <clé publique>
```

### Publier une version

1. Changer la version dans `pyproject.toml` (une PR, comme le reste). Une version publiée ne se republie jamais.
2. GitHub, Actions, « publier », en écrivant « Publie » : l'image est construite une fois et publiée dans le registre privé de MEGGA (`ghcr.io/megga/megga-agents`, choisi par Julien le 15.11.2026) par son empreinte seule ; elle est essayée (elle démarre et dit sa version), signée, vérifiée avec la clé publique du dépôt, et alors seulement elle reçoit son numéro (`:<version>`), sur la même empreinte. Un échec en route ne laisse aucune version numérotée. Le résumé donne l'empreinte.
3. Pour la vérifier ailleurs (avant un déploiement, chez un client) :

   ```bash
   scripts/verifier_image.sh ghcr.io/megga/megga-agents@sha256:<empreinte>
   ```

Cloudflare ne tire pas depuis GitHub : `scripts/vers_cloudflare.sh <version>` vérifie la signature et copie la même image (même empreinte) dans son registre. Pour l'instant, `wrangler deploy` construit encore l'image depuis `socle/Dockerfile` ; le passage de Cloudflare à l'image publiée viendra avec les mises à jour signées (lot 6, partie 4).

### Déployer chez Cloudflare

Depuis le Mac, avec l'étiquette du commit (le workflow « déployer » fait de même) :

```bash
cd porte && npx wrangler deploy --tag "$(git rev-parse --short=12 HEAD)"
```

### Après un déploiement chez Cloudflare

Un conteneur déjà allumé garde l'ancienne image jusqu'à son sommeil (15 minutes sans message), et les applications de conteneurs se provisionnent quelques minutes après un `wrangler deploy` (un conteneur qui démarre pendant ce temps répond « aucune instance disponible »). Une fois le déploiement fini :

```bash
scripts/apres_deploiement.sh https://megga-agents.api-963.workers.dev
```

Le script attend que les applications soient prêtes, puis demande à la porte (`POST /admin/redemarrer`) de faire repartir chaque conteneur allumé sur la nouvelle image : celui d'un client finit d'abord ses tours en cours ; celui de l'atelier, sa requête en cours (une mise en service va au bout).
