# Plateforme d'agents MEGGA : Agno sur Cloudflare Containers

Plan du 15.11.2026, à valider par Julien. Rien n'est créé ni déployé avant son accord.

## Le principe

Quatre couches. Un nouveau client = une configuration. Un nouveau métier = un pack.

1. **Socle** : Agno (Apache-2.0, Python), son serveur AgentOS (FastAPI). Sans os.agno.com (payant pour les connexions en direct) et sans télémétrie (`AGNO_TELEMETRY=false`).
2. **Noyau MEGGA** : WhatsApp, vocaux, voix ElevenLabs, mémoire, rappels, garde-fous, typographie, Claude Sonnet 5.5 avec DeepSeek en secours (`fallback_models` d'Agno).
3. **Packs métier** : l'immobilier d'abord, repris d'Alix FSP.
4. **Configuration client** : nom de l'agent, numéro, ton, langue, outils actifs, données, modèles Meta.

## L'installation

**Nouveau dépôt privé `megga/megga-agents`** :

```
socle/      Dockerfile (Python, Agno à version figée), lancement d'AgentOS
noyau/      le paquet Python du noyau
packs/      immobilier/ (puis les autres métiers)
clients/    une configuration par client, sans aucun secret
porte/      le Worker d'entrée (TypeScript)
scripts/    nouveau-client, tests de bout en bout
```

**Le chemin d'un message** :

1. Meta envoie le webhook de l'app « Alix MEGGA » au Worker `megga-agents` (adresse publique, à lui seul).
2. Le Worker vérifie la signature, lit l'identifiant du numéro, en déduit le client.
3. Il transmet le message au conteneur de ce client (`getByName(client)`), signature comprise.
4. Le conteneur répond lui-même à Meta.

**Séparation des clients** : un conteneur par client (son processus, ses secrets, sa mémoire), une base Postgres par client avec son propre rôle, un préfixe R2 par client. Un client ne peut ni lire ni joindre les données d'un autre. Dans une base, `user_id` sépare les interlocuteurs du client.

**Stockage** : le disque d'un conteneur est effacé à chaque réveil. Tout ce qui doit durer va ailleurs :
- Postgres géré (Neon conseillé : une base par client, en veille quand elle ne sert pas ; tarif à vérifier), avec pgvector pour la recherche par le sens ;
- R2 pour les fichiers (photos, vocaux, PDF) ;
- D1 pour l'annuaire des clients (numéro vers client, état), lu par le Worker.

**Secrets** : jamais dans le dépôt ni dans une configuration. Ceux de MEGGA (Anthropic, DeepSeek, ElevenLabs, jeton Meta de l'app) en secrets du Worker ; ceux d'un client (l'adresse de sa base, ses clés propres) dans le stockage de son propre objet Cloudflare, posés par une route d'administration en écriture seule, remis à son seul conteneur au démarrage.

**Journaux** : observabilité Cloudflare (7 jours, exportables) pour le Worker et les conteneurs ; les traces d'Agno (tours, outils, jetons) dans la base du client, lues par la console.

**Déploiement** : `wrangler deploy` construit l'image et la déploie, par étapes. Tests à chaque PR ; mise en production seulement à la main, sur « Fusionne et déploie ». Changer la configuration d'un client ne redéploie rien.

**Nouveau client en moins d'une journée** : `scripts/nouveau-client` crée la base, les secrets, l'entrée de l'annuaire et la configuration. Restent à la main : le numéro chez Meta et l'approbation de ses modèles.

## Les coûts estimés

Tarifs Cloudflare lus le 15.11.2026, hors modèles, voix et Meta, qui resteront la plus grosse part.

| | Par client et par mois |
|---|---|
| Conteneur « basic » (1/4 vCPU, 1 Gio), réveillé 4 h par jour | environ 1,5 $ |
| Le même, allumé jour et nuit | environ 7,5 $ |
| Conteneur « standard-1 » (1/2 vCPU, 4 Gio), jour et nuit | environ 27 $ |

Plus 5 $ par mois pour le compte (Workers Paid). Un conteneur endormi ne coûte rien ; il se rendort après 15 minutes sans message et se réveille en 1 à 3 secondes. La mémoire nécessaire à Agno n'est pas documentée : à mesurer au lot 1 avant de choisir la taille.

## Le branchement WhatsApp

- L'app Meta « Alix MEGGA » (la troisième), avec un nouveau numéro, a pour webhook le Worker `megga-agents`.
- Le routeur `megga-whatsapp` (megga-erp, `aiguillage.js`) et l'app « Alix FSP » ne sont pas touchés : autre app, autre webhook.
- Le noyau reprend le WhatsApp d'Alix (`meta.js`) : regroupement des messages de 2,5 s, vocaux, fenêtre de 24 h, modèles Meta. L'interface WhatsApp d'Agno ne sert qu'au premier essai.
- Les rappels : une tâche planifiée côté Cloudflare réveille le conteneur à l'heure dite.

## Deux modes d'installation

Même code, même pack métier, choisis client par client.

1. **Hébergé par MEGGA** (par défaut) : Cloudflare Containers, comme ci-dessus.
2. **Chez le client** (offre premium) : son serveur ou son cloud (Azure, AWS…). Ses données ne quittent pas son infrastructure.

**Une seule image Docker**, construite une fois par version, signée, publiée dans un registre privé de MEGGA. Cloudflare et le client tirent la même. Le noyau ne dépend jamais de Cloudflare directement : trois points d'échange suffisent.

| | Mode 1, MEGGA | Mode 2, client |
|---|---|---|
| Entrée WhatsApp | le Worker `megga-agents` | l'adresse du client, webhook vers son conteneur |
| Base | Postgres géré par MEGGA | le Postgres du client |
| Fichiers | R2 | son stockage compatible S3, ou un volume local |
| Secrets | Secrets Store | ses variables, ou son coffre (Key Vault, Secrets Manager) |

**La configuration** : le même format partout, avec un numéro de version. En mode 1, dans l'annuaire ; en mode 2, un fichier chez le client. Les modèles se règlent aussi par client : un client qui l'exige passe par ses propres comptes (Claude chez AWS Bedrock ou Azure, par exemple). Le client doit savoir que ce qu'il envoie au modèle quitte son infrastructure pour le fournisseur qu'il a choisi.

**Le pilotage à distance** :
- Toujours sortant : l'installation du client appelle la console de MEGGA, en HTTPS. Aucun port ouvert chez le client, aucun accès entrant.
- Authentifié : une clé propre à chaque installation, créée chez le client ; MEGGA en enregistre la partie publique à la mise en service ; révocable des deux côtés. Chaque requête est signée (Ed25519, avec l'heure et un nonce contre le rejeu) : un vrai certificat client demanderait un domaine de MEGGA chez Cloudflare, `workers.dev` ne le permettant pas (lot 6.3, à confirmer par Julien).
- Avec l'accord du client : un réglage chez lui, `PILOTAGE`, à « non », « suivi » (état et alertes seulement) ou « complet ». Il peut aussi demander que chaque changement attende son oui.
- Sans contenu : le suivi remonte l'état, les volumes, les coûts et les erreurs, jamais les conversations.
- Borné : la console ne peut que changer un réglage prévu ou proposer une version. Aucune commande libre. Chaque ordre est signé par MEGGA, vérifié par l'installation, et inscrit au journal des deux côtés.

**Les mises à jour** : un petit conteneur « pilote » à côté de l'agent (Docker Compose, ou une chart Helm) reçoit la version proposée. Il vérifie la signature de l'image, attend l'accord si le client l'a demandé, sauvegarde la base, lance la mise à jour et revient à la version d'avant si le contrôle de santé échoue. Le pilote décide sans aucun droit : sous Compose, un petit script du serveur (lancé par cron) remplace l'image quand le pilote le demande, et rien d'autre ; sous Kubernetes, son compte de service ne peut changer que l'image de deux Deployments nommés (lot 6.4).

**La maintenance que ça implique** :
- deux versions soutenues à la fois (la dernière et la précédente) ;
- les migrations de base jouées au démarrage, testées sur les deux modes à chaque PR ;
- un correctif de sécurité au moins une fois par mois, et chaque client du mode 2 à suivre jusqu'à ce qu'il l'ait installé ;
- un guide d'installation et un contrôle de santé (`/sante`) ;
- une clé de licence par installation, vérifiée sans appel extérieur.

## Les zones

Chaque client a une **zone**, choisie à l'installation : là où tournent son agent, sa base et ses fichiers, et où ses données restent. Décision de Julien du 15.11.2026.

| Zone | Pour qui | Agents | Base | Fichiers |
|---|---|---|---|---|
| `suisse` | clients suisses | Exoscale (Genève ou Zurich) | Postgres géré d'Exoscale, avec copie de secours | stockage Exoscale en Suisse |
| `europe` | clients de l'UE (RGPD) | Cloudflare, `jurisdiction: "eu"` | Neon, Francfort | R2, juridiction UE |
| `etats-unis` | clients américains | Cloudflare, `jurisdiction: "us"` | Neon, États-Unis | R2, juridiction États-Unis |
| `client` | installation chez le client | son infrastructure | son Postgres | son stockage |

**Les règles des zones** :
- Une zone ne change pas en cours de route : la changer, c'est déménager le client (copie, vérification, bascule), sur demande.
- Le Worker d'entrée ne fait que transmettre : il ne garde aucun message, et ses journaux ne contiennent ni texte ni numéro en clair.
- Le numéro WhatsApp est enregistré avec le stockage de Meta dans la zone quand Meta le propose (`CH` pour la Suisse, l'UE pour l'Europe).
- Les services autour suivent la zone quand c'est possible : Claude par une voie européenne pour un client européen qui l'exige (AWS Bedrock, profil Europe), ElevenLabs et les autres fournisseurs à vérifier un par un avant le premier client de chaque zone.
- La console ne reçoit d'aucune zone que l'état, les volumes, les coûts et les alertes, jamais de conversation.

**Coûts de départ de la zone suisse** (Exoscale, tarifs du 15.11.2026, hors TVA) : un serveur de 4 processeurs et 8 Go, 68 € par mois ; Postgres géré avec une copie de secours (Business-4), 195 € par mois ; soit environ 263 € par mois, partagés entre les clients suisses.

**La zone suisse** tourne avec la même image que le mode 2 :
- un conteneur par client, une base Postgres par client, des fichiers et des sauvegardes, tout en Suisse ;
- le webhook WhatsApp d'un client suisse va directement au serveur suisse, sans passer par Cloudflare ;
- le numéro WhatsApp enregistré avec le stockage en Suisse (`data_localization_region: CH`) ; Meta traite toutefois un message jusqu'à 60 minutes hors de Suisse ;
- piloté par la console comme une installation client (canal sortant, signé), sans aucune conversation qui en sorte ;
- le modèle : un modèle hébergé en Suisse si rien ne doit sortir, ou Claude par l'Europe si le client l'accepte par contrat.

**Hors WhatsApp** : pour un logiciel (par exemple médical), le noyau offre aussi une entrée par API, appelée depuis le logiciel du client. Les données de patients n'ont alors pas à passer par Meta. Fait au lot 6.6 : `POST /api/messages` (chez MEGGA, `https://api.megga.ai/api/<client>/messages`, servi par la porte), une clé par logiciel gardée en empreinte dans la base du client, WhatsApp devenu facultatif ; le guide du développeur : `docs/api.md`.

Plusieurs clients suisses partagent le serveur, séparés comme sur Cloudflare ; un client premium peut avoir son serveur à lui.

## Intégrer Alix FSP

Alix FSP tourne sans interruption pendant toute la construction. Elle ne bascule qu'à parité, avec l'accord de Julien.

**Ce qui va au noyau** : la boucle et le secours de modèle (`agent.js`), WhatsApp (`meta.js`, `message.js`), vocaux et voix (`vocal.js`, `voix.js`, `oral.js`), humeur et réactions (`humeur.js`, `reaction.js`), mémoire (`memoire.js`), rappels et point (`initiative.js`), typographie (`typographie.js`).

**Ce qui devient le pack immobilier** : annonces, brouillon, rédaction, garde-fous d'annonce, photos, vidéos, accès, transfert, recherche, carrousel, formulaire, marché et veille, demandes du site, partenaires. Ces outils parlent déjà à la gestion par son API : le pack les branche sur une gestion par client, la vraie pour FSP, une gestion clonée aux faux biens pour la démo.

**Ce qui reste à Four Seasons** : sa configuration (Greg, ses numéros, ses consignes, sa gestion, son logo et ses polices de fiche). Rien de Four Seasons dans le noyau, le pack ou la démo.

**La fiche PDF** : gardée en JavaScript (`pdf-lib`), appelée comme un service, plutôt que réécrite.

**La bascule** : les scénarios de test d'Alix (`test/simulation-*.js`) passent sur les deux ; puis un numéro de test FSP sur le socle ; puis, sur accord, `fourseasons-alix` transmet au socle au lieu de répondre (changement dans le dépôt FSP, routeur intact). Souvenirs, partenaires et rappels sont copiés dans la base du client FSP. Retour arrière : une variable.

## Les lots, une branche et une PR chacun

1. **Socle** : dépôt, image Agno unique, Worker d'entrée, un conteneur par client, base, secrets, journaux. Les trois points d'échange (entrée, base, fichiers) sont posés dès ici, pour que le mode 2 ne soit pas une réécriture. La zone est dans la configuration dès ce lot. Un agent d'essai répond par écrit sur WhatsApp ; aucun client ni agence de démo dans ce lot.
2. **Noyau WhatsApp** : vocaux, voix, regroupement, fenêtre de 24 h, modèles Meta, réactions.
3. **Mémoire, rappels, garde-fous.**
4. **Pack immobilier**, puis l'agence de démo MEGGA Estates (faux biens, son propre numéro), quand Julien le décide.
5. **Console** : un espace par client (état, conversations, coûts, alertes), sur le design que Julien construit dans Claude Design. La console sert aussi à **construire** les agents, pas seulement à les suivre (exigence de Julien, 15.11.2026) :
   - **le client** (logiciel par abonnement) construit le sien très simplement : métier, prénom, voix, ton, outils à cocher, essai, activation ;
   - **MEGGA** gère tous les agents de tous les clients, en construit sur mesure, règle l'avancé (modèles, outils, zones, coûts) et peut reprendre la main sur ce qu'un client a fait ;
   - un seul moteur : l'interface ne fait que remplir la configuration du client (`noyau/config.py`). Côté code, il faut donc :
     - une API d'administration pour créer, valider, essayer et activer une configuration ;
     - des droits par rôle (client ou MEGGA) ;
     - un mode d'essai avant la mise en service ;
     - un historique des versions de configuration, avec retour à une version précédente.
   - partir des fondations d'Agno plutôt que tout refaire (validé par Julien, 15.11.2026). AgentOS (Agno 3.2) a déjà les routes de composants, vérifiées dans le code : `/components`, `/components/{id}/configs`, `.../configs/current`, `.../configs/{version}`, `.../configs/{version}/set-current`, `/components/{id}/restore` et `/registry`. Elles couvrent l'agent en base, l'historique des versions, la version en service et le retour en arrière. À construire par-dessus : l'assistant simple des clients, les droits par rôle, le mode d'essai avant activation, et le lien avec notre configuration et l'annuaire des zones. Le « Studio » d'os.agno.com n'est pas retenu (marque Agno, connexion en direct payante, fait pour des développeurs).
   L'interface elle-même reste à Julien, dans Claude Design : le plan ne la fige pas.
6. **Installation chez le client et zone suisse** : Docker Compose et chart Helm, conteneur pilote, canal de pilotage, mises à jour signées, guide, puis la zone suisse chez Exoscale et l'entrée par API. Avancé dès qu'un client suisse signe.
7. **Alix FSP sur le socle** : parité, essai, bascule sur accord.

## Décidé

- Dépôt de la plateforme : `megga/megga-agents` (Julien, 15.11.2026). L'agence de démo s'appellera MEGGA Estates ; elle attend que Julien la lance.
- Zones : Suisse chez Exoscale, Europe et États-Unis chez Cloudflare (Julien, 15.11.2026).
- Postgres des zones Europe et États-Unis : Neon au départ (environ 15 $ par mois pour 10 clients). La migration vers une base maison chez Cloudflare (SQLite par client) se décide vers la centaine de clients, mais se prépare dès le lot 1 :
  - un seul module du noyau parle à la base ; rien d'autre n'y touche ;
  - nos tables sont décrites et versionnées dans le dépôt ;
  - un outil exporte et importe un client entier (il sert aussi au changement de zone et au mode 2) ;
  - les tests tournent aussi sur SQLite, le moteur de la base Cloudflare, pour qu'aucune particularité de Postgres ne s'installe dans le code.

