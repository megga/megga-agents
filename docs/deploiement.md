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
