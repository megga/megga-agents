# L'admin MEGGA : piloter et suivre la plateforme (conception)

Le 18.11.2026. Demandé par Thomas. Périmètre nouveau : le plan du lot 8 cite « la vue MEGGA sur tous les clients » comme faite côté moteur, mais aucun lot n'en prévoit l'écran. À faire relire par Julien en PR ; rien n'est fusionné ni déployé sans « Fusionne et déploie » de Julien.

## L'intention

MEGGA n'a aucun écran pour tenir sa plateforme. L'atelier (lot 5) sait presque tout faire pour le rôle MEGGA, mais par API et par scripts (`scripts/pilotage.py`, `scripts/inscrire_client.py`). La console (lot 8.1) ne sert que les clients. L'admin donne à Thomas et Julien, puis à une équipe et à des invités externes aux pouvoirs limités, un endroit pour voir ce qui se passe et agir : quel client va mal, ce que la plateforme coûte, qui s'inscrit, et les gestes du quotidien (mettre en service, revenir en arrière, donner un jeton, suspendre un compte).

## Ce qui est décidé par Thomas (18.11.2026)

1. L'admin porte sur les deux populations : les clients du moteur (par l'atelier) et les comptes de la console (Better Auth et leurs agents).
2. Thomas et Julien sont superadmins. Des niveaux de rôles se créent à l'écran, « selon les standards du SaaS ». Des utilisateurs externes s'ajoutent, avec des pouvoirs limités.
3. La même apparence que la console des clients.
4. Toutes les fonctions qui permettent de piloter et de suivre : pas seulement de la lecture.
5. Un invité externe voit et propose : il suit les clients de son périmètre, et prépare un brouillon limité aux réglages simples. Mettre en service, les jetons, les clés et les installations restent à un membre interne.

Tout le reste de ce document est une proposition de Claude, à corriger. Le plan du lot 8 auquel il renvoie (« 8.8 », « décision 6 », « lot 11 ») est `docs/lot8.md`, dans la PR #55, pas encore sur `main`.

## Les objectifs

1. Un espace `/admin` dans l'application `console/`, aux jetons de la maquette (`globals.css`), en clair et en « Nuit douce », utilisable à 390 px de large.
2. Un contrôle d'accès complet : superadmins, rôles créés à l'écran, membres, invitations, invités externes limités à certains clients et dans le temps. Tout est vérifié côté serveur ; chaque geste est noté dans un journal.
3. Suivre : une vue d'ensemble, les clients du moteur (état, activité, coûts, alertes, conversations, versions, installation), les comptes de la console (inscriptions, agents, messages).
4. Piloter : créer un client, préparer une version, l'essayer, la mettre en service ou revenir en arrière, reprendre la main, délivrer et retirer jetons et clés, régler les tarifs, piloter une installation hors Cloudflare ; suspendre et réactiver un compte de la console.
5. Des tests, la CI de la console étendue, une PR en français simple avec des captures.

## Les non-objectifs

- Le moteur (`noyau`, `atelier`, `porte`, `pilote`, `packs`) : rien n'y est modifié. L'admin n'appelle que les routes de l'atelier qui existent sur `main` (`docs/atelier.md`).
- Le déploiement et le branchement à l'atelier réel : Julien pose `ATELIER_URL` et `ATELIER_JETON`. On ne développe jamais contre la production.
- L'envoi de courriels : le projet n'a pas de messagerie. Une invitation est un lien, montré une fois, à envoyer soi-même.
- La double authentification des membres : à décider avec Julien (Better Auth la fournit), pas dans ce lot.
- Se connecter à la place d'un client, supprimer un compte, exporter le journal, la facturation et les abonnements.
- Marquer une alerte comme traitée : l'admin montre ce que dit le moteur, sans état à lui.
- Un formulaire champ par champ pour la configuration d'un agent : c'est l'écran des réglages du client (8.8). L'admin prépare une version d'après un modèle par métier, ou d'après des changements écrits en JSON et validés par l'atelier.
- Les écrans du lot 9 (accords, audit des outils, connaissances, demandes, valeur) : leurs routes sont dans des PR ouvertes (#38 à #44), pas sur `main`.
- Les gestes d'entretien que seule la porte expose (oublier une personne, rappels, redémarrer tous les conteneurs, secrets).

## Les anti-objectifs (un échec, même si tout marche)

- Un membre limité ou un invité qui voit ou fait plus que ses droits : un coût, une conversation, un client hors de son périmètre ; par une adresse tapée à la main, par une route, ou par un total qui compterait des clients qu'il ne voit pas.
- Le jeton MEGGA dans le navigateur. Un jeton de client ou une clé de logiciel ailleurs que dans son affichage unique : ni dans le journal, ni dans un message d'erreur, ni dans une adresse.
- Un geste sur la production sans confirmation qui dit son effet, ou sans trace dans le journal.
- Plus aucun superadmin : le dernier ne peut ni partir ni être retiré.
- Une couleur, une police ou un contour hors des jetons de la console ; un bouton qui ne fait rien ; un texte visible avec un point médian, un tiret long ou demi-cadratin.
- La console des clients ralentie ou cassée par l'admin (le compteur de messages ne retarde jamais une réponse).

## Les approches

| | Ce que c'est | Ce que ça coûte |
|---|---|---|
| **A. Des tables de l'admin dans la base de la console** (retenue) | Rôles, membres, invitations et journal dans des tables à nous ; un seul point de contrôle côté serveur, essayé droit par droit | Du code à nous pour les invitations et les rôles |
| B. Les extensions de Better Auth (`organization`, rôles dynamiques, invitations) | MEGGA devient une « organisation » ; rôles et invitations fournis | Ce modèle est celui des entreprises clientes et de leurs collègues (lot 11) : y ranger l'équipe MEGGA mélange les deux. Le périmètre par client n'y existe pas |
| C. Les rôles dans le moteur (un jeton par membre, vérifié par l'atelier) | La limite d'un invité est tenue à la source | Modifie le moteur en production ; trop large pour ce lot |

Thomas a laissé le choix à Claude : **A**. Sa conséquence : le serveur de la console détient le jeton MEGGA, donc les limites d'un membre sont tenues par la console seule. C devient utile si les externes se multiplient ; c'est noté pour Julien (« Ce qui manque à l'API »). Une application à part a été écartée : Thomas demande une section, et une seule application garde d'office la même apparence et la même connexion.

## L'accès

### Qui entre

- `/admin` et `/api/admin` demandent une session et une ligne de membre en cours (ni expirée, ni retirée). Sans session : la connexion, puis retour à `/admin`. Avec une session sans droit : 404, comme si l'admin n'existait pas.
- Le contrôle se fait à chaque requête, dans une seule fonction (`garde`), jamais dans l'écran seul. Un droit retiré s'applique à la requête suivante.
- Les écritures vérifient l'origine de la requête (même site).
- Le menu du compte de la console montre « Administration » aux seuls membres ; l'admin a « Retour à la console ».

### Les droits

Treize droits, fixés dans le code (un rôle ne peut cocher que ceux-là) :

| Droit | Permet |
|---|---|
| `clients.voir` | la liste, la fiche, l'activité, les alertes, les versions et l'installation, en lecture |
| `couts.voir` | les coûts et les tarifs, en lecture |
| `conversations.lire` | les conversations des clients hébergés par MEGGA |
| `clients.creer` | créer un client |
| `versions.preparer` | préparer un brouillon, le valider, l'essayer |
| `clients.piloter` | mettre en service, revenir à une version, forcer, reprendre ou rendre la main |
| `acces.gerer` | les jetons d'un client et les clés de ses logiciels |
| `installations.gerer` | enregistrer ou révoquer la clé d'une installation, proposer une image |
| `tarifs.regler` | changer les tarifs |
| `comptes.voir` | les comptes de la console et leurs agents |
| `comptes.gerer` | suspendre, réactiver, déconnecter partout |
| `equipe.gerer` | membres, invitations, rôles |
| `journal.voir` | le journal |

### Les rôles

- Un rôle : un nom, une description, des droits cochés. Ils se créent, se modifient et se retirent à l'écran (un rôle encore porté par un membre ne se retire pas).
- **Superadmin** est fixe : tous les droits, aucun périmètre, ni modifiable ni retirable. Seul un superadmin nomme ou retire un superadmin.
- Quatre rôles de départ, modifiables : **Administration** (tout), **Exploitation** (clients, conversations, versions, pilotage, accès, installations, comptes), **Finance** (`clients.voir`, `couts.voir`, `tarifs.regler`, `comptes.voir`), **Lecture** (`clients.voir`, `comptes.voir`).
- Pas d'escalade (proposition de Claude), avec `equipe.gerer` et sans être superadmin :
  - on ne donne qu'un rôle dont tous les droits sont déjà les siens ;
  - on ne crée ou ne modifie un rôle qu'avec des droits qu'on a déjà, et jamais le rôle qu'on porte ;
  - on ne touche ni à sa propre ligne ni à un superadmin.
- Avec `comptes.gerer`, suspendre le compte d'un membre de l'admin est réservé aux superadmins. Le compte d'un superadmin ne se suspend pas (lui retirer d'abord ce rôle), ni le sien.

### Les membres, le périmètre, les externes

- Un membre : un compte Better Auth, un rôle, un périmètre (tous les clients, ou une liste), une date de fin facultative, la marque « externe ».
- Le périmètre borne tout ce qui touche un client : listes, fiches, totaux de la vue d'ensemble, alertes. Un client hors périmètre répond 404.
- Un membre interne limité à une liste (proposition de Claude) ne crée pas de client (il naîtrait hors de son périmètre) ; son journal ne montre que ses propres gestes et ceux qui touchent ses clients ; les tarifs, qui valent pour tous, lui restent ouverts selon ses droits.
- Un **externe** (décision 5) a toujours un périmètre d'au moins un client. Quels que soient les droits de son rôle, il ne garde que `clients.voir`, `conversations.lire` et `versions.preparer`. L'écran le dit quand on choisit son rôle.
- Pour un externe, `versions.preparer` se limite aux réglages simples d'un client, ceux que le catalogue de l'atelier nomme `champs_client` (métier, prénom, voix, ton, outils). La console refuse tout autre réglage avant d'appeler l'atelier, comme `atelier/regles.py` (`appliquer`) le fait pour le rôle client : la voix se donne par son identifiant, changer de métier retire les outils qu'il ne permet pas. Il ne prépare pas d'après un modèle par métier (appliqué au nom de MEGGA, le modèle remplacerait les consignes sur mesure). Ce filtre a ses essais : c'est le premier anti-objectif.

### Les invitations et les premiers superadmins

- Une invitation : courriel, rôle, externe ou non, périmètre, fin d'accès. Elle donne un lien `/admin/invitation/<jeton>`, montré une fois ; la base n'en garde que l'empreinte (SHA-256). Valable 7 jours, une seule fois, retirable.
- La page du lien : connecté avec le courriel invité, un bouton pour rejoindre ; sinon, créer son compte (nom, mot de passe ; le courriel est celui de l'invitation) ou se connecter. Un autre courriel est refusé avec une phrase claire.
- Les premiers superadmins viennent d'une commande lancée sur le serveur (`npm run admin:inviter -- <courriel>`), qui imprime un lien d'invitation superadmin. Pas de liste de courriels dans l'environnement : l'inscription est ouverte et les courriels ne sont pas vérifiés, une adresse de la liste pourrait être prise par un autre.

### Le journal

Chaque écriture de l'admin, réussie ou refusée, et chaque conversation ouverte : quand, qui (identifiant et courriel au moment du geste), l'action, la cible (client, compte, rôle, membre), le résultat, un détail sans secret (jamais un jeton, une clé, un mot de passe ; un numéro de personne est réduit à ses quatre derniers chiffres). Gardé sans limite dans ce lot.

## Les écrans

La coquille reprend la console : un rail à gauche (`bg-side`, 304 px, 76 px sous 760 px) avec la tête de la mascotte, les entrées que les droits du membre ouvrent, et le menu du compte en bas (thème, retour à la console, se déconnecter). À droite, la page : un titre, des tuiles et des tableaux aux contours `--fin`. États : `--ok`, `--warn`, `--accent`, `--faint`. Aucune couleur nouvelle, aucune bibliothèque de graphiques (des barres en CSS).

```
/admin
├─ Vue d'ensemble
├─ Clients ─ fiche : Suivi, Alertes, Conversations, Versions, Accès, Installation
├─ Alertes
├─ Installations
├─ Comptes ─ fiche
├─ Tarifs
├─ Équipe : Membres, Invitations, Rôles
└─ Journal
```

**Vue d'ensemble** (`clients.voir`). Période : 24 heures, 7 jours, 30 jours (des périodes glissantes, comme l'atelier les compte). Tuiles : clients en service, soucis en cours, tours, personnes, coût (`couts.voir`), et pour la console (`comptes.voir`) comptes, agents, messages. « À surveiller » : les clients qui ont un souci en cours ou des échecs sur la période, le plus grave d'abord. « Activité par client » : tours, personnes, échecs, secours, coût. « Console » : inscriptions et messages par jour.

**Ce qu'est un souci en cours** (proposition de Claude). Le moteur ne dit « résolue » que pour les pannes d'un conteneur. Sont donc en cours : une panne de conteneur non résolue, et les états de l'instant (écart, porte ou conteneur injoignable, installation silencieuse ou révoquée, licence expirée). Tout le reste (tour, envoi, vocal ou rappel en échec, envoi refusé par Meta, message reçu trop tard, plafond du jour) est un fait passé : il se liste sur la période, sans état.

**Clients**. Le tableau de `GET /atelier/clients` : entreprise, agent, identifiant, version en service et dernière version, état (en service, jamais mis en service, écart, tenu par MEGGA ; l'état du conteneur d'après l'annuaire), installation. Si la porte ne répond pas, un bandeau le dit pour toute la liste. Recherche. « Nouveau client » (`clients.creer`) : un modèle par métier, l'identifiant, l'entreprise, la zone, le numéro WhatsApp facultatif, le prénom de l'agent ; ou une configuration entière collée.

**Fiche d'un client**, par onglets :
- *Suivi* : la période ; tours (dont ceux venus par API), échecs, secours, personnes, rappels en attente, voix et vocaux ; par modèle : tours et jetons ; avec `couts.voir`, le coût par poste, le total, et les modèles sans tarif signalés.
- *Alertes* : quand, quoi (dit en clair), le détail ; pour une panne de conteneur, résolue ou non.
- *Conversations* (`conversations.lire`) : les personnes, la plus récente d'abord, puis le fil d'une personne, en bulles comme la console, en lecture seule. Pour une installation chez le client : la phrase de l'atelier (elles ne la quittent jamais).
- *Versions* : l'historique (numéro, brouillon ou publiée, en service, préparée par MEGGA ou par le client : l'atelier ne garde que ce rôle, le membre se lit au journal de l'admin) ; la configuration d'une version, lisible ; ce qui change par rapport à celle en service. Préparer : d'après un modèle par métier, ou d'après des changements en JSON, avec « Valider » qui montre le résultat ou les erreurs champ par champ. Essayer : une petite conversation avec le brouillon, le rôle au choix, avec la mention qu'un essai consomme des jetons. Mettre en service, revenir à une version, forcer : chacun derrière une confirmation qui dit son effet (le conteneur du client redémarre dès qu'il a fini ses tours).
- *Accès* (`acces.gerer`, la main avec `clients.piloter`) : qui tient l'agent (reprendre ou rendre la main) ; les jetons du client (en créer un, montré une fois ; tous les retirer, l'atelier disant combien l'ont été ; aucune route ne les liste, l'écran ne peut donc pas dire s'il en existe) ; les clés des logiciels (nom, débit par minute ; en créer une, montrée une fois ; en retirer une).
- *Installation* (hors Cloudflare seulement) : le dernier relevé, le pilotage, l'écart, les vingt derniers ordres, le journal du pilotage ; avec `installations.gerer` : enregistrer la clé publique, la révoquer, proposer une image.

**Alertes**. Celles de tous les clients du périmètre sur la période, les soucis en cours d'abord ; tri par client et par genre.

**Installations**. `GET /atelier/installations` : client, dernier relevé (silencieuse au-delà de 5 minutes), pilotage, mises à jour, écart ; et si l'atelier a sa clé pour signer.

**Comptes** (`comptes.voir`). Les comptes de la console : entreprise, courriel, inscrit le, dernière connexion, agents, messages sur 30 jours, état, membre de l'admin ou non. La fiche : ses agents (tête, prénom, métier, créé le, messages), ses sessions. Avec `comptes.gerer` : suspendre (avec un motif), réactiver, déconnecter partout. Un compte suspendu ne se connecte plus, perd ses sessions tout de suite, et lit une phrase claire.

**Tarifs** (`couts.voir` pour lire, `tarifs.regler` pour changer). La devise ; par modèle : entrée, sortie, lecture et écriture du cache, par million de jetons ; la voix pour 1000 caractères ; l'écoute par vocal. Les modèles vus dans l'activité sans tarif se proposent à l'ajout.

**Équipe** (`equipe.gerer`). *Membres* : nom, courriel, rôle, interne ou externe, périmètre, fin d'accès, dernière connexion ; changer le rôle, le périmètre, la fin ; retirer. *Invitations* : en créer une, voir celles en attente, en retirer. *Rôles* : les droits cochés par groupe, le nombre de membres ; créer, modifier, retirer.

**Journal** (`journal.voir`). Quand, qui, quoi, sur quoi, le résultat ; tri par membre, action, client, période ; par pages.

## Les données

### La base de la console (des tables de plus)

- `admin_role` : identifiant, nom, description, droits, marque « système », dates.
- `admin_membre` : le compte, le rôle, externe, périmètre, fin d'accès, ajouté par, ajouté le.
- `admin_invitation` : empreinte du jeton, courriel, rôle, externe, périmètre, fin d'accès, valable jusqu'à, créée par, acceptée le et par, retirée le.
- `admin_journal` : quand, qui, courriel, action, cible, résultat, détail.
- `usage_agent` : agent, jour, messages. Un de plus à chaque tour envoyé à un agent par `/api/copilotkit`, écrit après coup, sans texte.

SQLite intégré à Node, comme la table `agent` ; tout le SQL reste derrière des fonctions de `src/lib/admin/`, pour le passage à Postgres au déploiement.

### L'atelier

- Un client côté serveur (`src/lib/admin/atelier.ts`, `server-only`) : `ATELIER_URL` et `ATELIER_JETON` (le jeton MEGGA). Une fonction par route de `docs/atelier.md`. Un refus de l'atelier montre sa phrase (`erreur`) et, quand `details` est une liste de `{champ, message}`, ces messages champ par champ. Les autres détails (la réponse brute de la porte, `annuaire_retabli`) ne s'affichent pas ; une réponse d'une autre forme (le 422 de FastAPI pour un corps absent) donne une phrase générale.
- Sans `ATELIER_URL` : les écrans du moteur disent que le moteur n'est pas branché ; Comptes, Équipe et Journal marchent.
- La réponse de l'atelier porte les coûts dès que le jeton est celui de MEGGA : la console les retire avant tout affichage à qui n'a pas `couts.voir`. De même, le périmètre filtre la liste des clients avant tout calcul.
- La vue d'ensemble lit le suivi de chaque client, quelques-uns à la fois ; un client injoignable n'empêche pas les autres. Les lectures sont gardées un court instant côté serveur, avant le filtre des droits.

### L'atelier d'essai local

À côté du serveur d'agents de l'essai (`console/agents/`), un petit programme qui lance le vrai atelier (`atelier.app.creer`) sur SQLite, avec une porte simulée qui invente l'activité, les alertes, les conversations et les clés de quelques clients fictifs : un qui va bien, un avec des alertes, un avec un écart. Les modèles à suivre : `FaussePorte` (`tests/test_lot5.py`) pour la mise en service et l'annuaire, `PorteSuivie` (`tests/test_suivi.py`) pour le suivi, `PorteAuxCles` (`tests/test_lot6_api.py`) pour les clés. Une installation hors Cloudflare inventée, dont le relevé signé se rejoue par `noyau.pilotage.entetes`, comme `releve_signe` dans `tests/test_lot6_pilote.py`. Il n'écoute que sur `127.0.0.1`, derrière un jeton partagé. Il sert au développement et aux essais de bout en bout. Aucun nom de vrai client n'y figure.

## Les essais

- Vitest : chaque droit, le périmètre, le plafond des externes et leur brouillon limité aux réglages simples, la fin d'accès, l'escalade refusée (rôle donné, rôle modifié, compte d'un membre suspendu), le dernier superadmin ; les invitations (une fois, 7 jours, courriel, empreinte seule en base) ; le journal sans secret ; le client de l'atelier (coûts retirés sans le droit, erreurs) ; les textes de l'admin (mêmes règles que `textes.ts`).
- Les routes : une liste de toutes les routes de `/api/admin`, chacune essayée sans session (401), sans être membre (404), sans le droit (403), hors périmètre (404). Une route ajoutée sans passer par `garde` fait échouer l'essai.
- Pytest : l'atelier d'essai démarre, exige son jeton, sert ses clients.
- Playwright : un superadmin invité par la commande rejoint l'admin, voit la vue d'ensemble, ouvre un client, met une version en service (confirmation), le retrouve au journal ; il invite un externe limité à un client, qui ne voit que ce client, ni coûts ni Équipe, et ne peut pas mettre en service ; un compte ordinaire reçoit 404 sur `/admin`.

## L'ordre de construction

1. L'accès : tables, droits, garde, journal, invitations, commande des superadmins ; la coquille ; Équipe et Journal.
2. L'atelier d'essai et le client de l'atelier ; Clients, la fiche (Suivi, Alertes), la vue d'ensemble, Alertes.
3. Les coûts, Tarifs, Conversations.
4. Piloter : Versions, Accès, nouveau client, Installations.
5. Les comptes de la console : le compteur de messages, la liste, la fiche, la suspension.
6. Les essais de bout en bout, les captures, la PR.

## Ce qui reste au constructeur

Le découpage en fichiers et en composants, le SQL, les pièces shadcn à ajouter (tableau, onglets, cases, pastilles), les durées de garde en mémoire, la façon de suspendre un compte (l'extension `admin` de Better Auth pour le seul bannissement, ou une table à nous), la détection d'un tour dans `/api/copilotkit`, le détail des écrans dans les jetons de la console. Lire la documentation de Next.js 16 dans `node_modules/next/dist/docs/` avant d'écrire (`console/AGENTS.md`).

## Les textes

Tous dans un fichier à part de l'admin, aux règles de `textes.ts` (français, courts, ni point médian ni tiret long), listés dans la PR pour que Julien les relise.

## Ce qui manque à l'API (noté pour Julien, pas codé dans le moteur)

1. L'activité jour par jour : l'atelier rend des totaux sur une période. Sans elle, pas de courbe ni de coût par mois pour le moteur.
2. Des rôles tenus par l'atelier (un jeton par membre) : aujourd'hui la console tient seule les limites d'un invité.
3. Le lien entre un compte de la console et un client de l'atelier (déjà noté au 8.1) : sans lui, les deux populations restent côte à côte.
4. La zone d'un client dans la liste (il faut lire chaque configuration pour l'afficher).
5. Les gestes d'entretien de la porte (oublier une personne, rappels) par l'atelier.
6. La liste des jetons d'un client (aujourd'hui : en créer un, ou tous les retirer).
7. L'auteur d'une version : l'atelier garde le rôle (`megga` ou `client`), pas la personne.

## À décider avec Julien (sans bloquer ce lot)

La double authentification des membres de l'admin ; l'inscription ouverte ou sur invitation (décision 6 du lot 8) ; où tourne la console et qui pose `ATELIER_JETON`.
