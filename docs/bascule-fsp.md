# Four Seasons sur le socle : de la parité à la bascule

Alix FSP (Worker `fourseasons-alix`) tourne sans interruption jusqu'à la bascule, qui ne se fait qu'avec l'accord de Julien. Chaque étape ci-dessous est réversible jusqu'à la dernière ; celles marquées **Julien** sont les siennes.

## 1. La parité (fait au 7.7)

Les 36 cas du banc noté d'Alix (`eval/cas.mjs` de son dépôt), repris en scénarios neutres (`parite/cas.json`), se jouent sur les deux agents, en local, avec le vrai Claude :
- Alix entière, comme son banc la fait tourner (`parite/alix.mjs`, qui lit son dépôt sans le modifier) ;
- l'agent de Four Seasons tel que le socle le construit (`parite/socle.py`), contre la vraie gestion du site servie en local (`parite/gestion.mjs`, la donnée du dépôt du site) ;
- les mêmes critères et le même juge pour les deux (`parite/noter.py`), un rapport côte à côte.

```bash
F=<clone de megga/fourseasonsproperties>   # avec npm ci dans alix/
node --import $F/alix/test/bouchons/enregistrer.js parite/alix.mjs $F traces/alix
.venv/bin/python -m parite.socle $F traces/socle
.venv/bin/python -m parite.noter traces/alix traces/socle rapport-parite.md
```

La clé Anthropic se lit dans `~/.config/alix-essai/anthropic.key`, jamais affichée. Un passage complet coûte quelques dollars. Le dernier rapport est dans `docs/lot7.md`.

## 2. Le numéro de test (**Julien**)

Un numéro au nom de Four Seasons Properties, dans le portefeuille WhatsApp Business de MEGGA, branché sur l'app Meta « Alix MEGGA » (dont le webhook est la porte) :
1. Dans le Business Manager de MEGGA, compte WhatsApp Business : ajouter le numéro, nom affiché « Four Seasons Properties » (catégorie immobilier).
2. Recevoir le code par SMS ou appel, et le saisir soi-même ; poser le code PIN de la vérification en deux étapes.
3. Relever l'identifiant du numéro (« Phone number ID ») : c'est `whatsapp.numero_id` de la configuration. Il n'est pas secret.
4. Soumettre les modèles de message (catégorie utilitaire), en français et en anglais au besoin, et noter leurs noms. Les usages du socle (`modeles_meta`) :

| Usage | Ce qu'il annonce | Variables |
|---|---|---|
| `message` | un message attend (le repli de tous les usages) | le nom de l'agent |
| `rappel` | un rappel demandé | le texte du rappel |
| `partenaire` | une demande de partenaire pour le courtier | le partenaire, les références |
| `livraison` | ce que le courtier fait envoyer à un partenaire | la référence |
| `demande` | une demande d'information du site, un contact, une question | le bien, le nom, l'e-mail, le téléphone |
| `reponse_visiteur` | la réponse du courtier à un visiteur | le message |
| `suivi_visiteur` (`_en`) | le courtier a bien reçu la demande | le sujet |
| `ouverture` | un message du courtier pour un contact | le nom, le sujet |
| `veille`, `zone`, `rapprochement` | une veille, un suivi de zone, un rapprochement | une phrase |

Sans un modèle, ce qui part hors des 24 heures attend le prochain message de la personne (ou le modèle `message`, s'il est réglé).

## 3. La configuration et les secrets

1. Une PR qui ajoute à `clients/four-seasons-properties.yaml` : `whatsapp: {numero_id: …}` et `modeles_meta`.
2. **Julien** : `scripts/secrets_gestion.sh four-seasons-properties <porte>` pose `GESTION_CLE`, `GESTIONNAIRES` (Greg et Julien, `{"+41…": "compte"}`) et `SITE_CLE` (saisie masquée).
3. Sur « Fusionne et déploie » de **Julien** : les PR du lot 7, dans l'ordre (7.1 à 7.7), puis la mise en service de la configuration par l'atelier.

## 4. La copie des données

1. Sur « Fusionne et déploie » de **Julien** : la route d'export d'Alix (`GET /export`, megga/fourseasonsproperties#132), avec `npx wrangler secret put EXPORT_CLE` (saisie masquée).
2. L'export, dans un fichier, sans l'afficher : `curl -sS -H "authorization: Bearer $(security find-generic-password -a megga -s fsp-export -w)" https://<fourseasons-alix>/export > export.json`.
3. L'import dans la base du client (une fois ; `--encore` pour refaire sans doubler) :
   `DATABASE_URL=… CLIENT_CONFIG_FILE=clients/four-seasons-properties.yaml .venv/bin/python -m packs.immobilier.reprise export.json`
   Il rend les comptes (partenaires, demandes, recherches, souvenirs, règles, fils, veilles, zones, relevés), jamais les données. L'historique des conversations des visiteurs et des partenaires ne se reprend pas.
4. Effacer `export.json`.

## 5. L'essai sur le numéro de test

Greg et Julien écrivent au numéro de test pendant quelques jours, comme à Alix : annonces, partenaires (un partenaire d'essai), un visiteur, le marché. Le suivi de l'atelier montre les échanges et les échecs. Alix continue de répondre sur l'ancien numéro.

## 6. La bascule (**Julien**, sur accord)

Comme le prévoit `docs/plan.md` : `fourseasons-alix` transmet les webhooks au socle au lieu d'y répondre, le routeur `megga-whatsapp` reste intact. C'est un second changement dans le dépôt d'Alix (un mode relais, réglé par une variable), à faire seulement sur l'accord de Julien. À trancher à ce moment : le numéro que le socle sert pour Four Seasons (celui d'Alix, ou le numéro de test devenu le sien), car l'annuaire de la porte ne relie qu'un numéro à un client.

**Retour arrière** : la variable du mode relais, retirée ; Alix répond de nouveau, avec ses données d'avant la copie (ce qui s'est dit sur le socle entre-temps n'y revient pas).
