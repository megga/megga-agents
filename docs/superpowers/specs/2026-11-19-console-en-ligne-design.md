# La console en ligne : conception

Le 19.11.2026. Demande de Thomas : « Installe la console sur le site », puis « Seuls Julien et moi sommes admin pour l'instant ». Thomas rapporte l'accord de Julien le même jour. Rien n'est fusionné ni déployé sans « Fusionne et déploie » de Julien.

Ce travail s'empile sur la PR #65 (la section admin, `docs/superpowers/specs/2026-11-18-admin-design.md`), pas encore relue ni fusionnée.

## L'intention

Thomas et Julien pilotent les vrais clients depuis l'admin, en ligne, à une adresse de megga.ai, avec une entrée dans l'admin du site. Aujourd'hui l'admin ne tourne qu'en local, sur six clients fictifs.

## Les buts

1. La console, dont `/admin`, répond à `https://console.megga.ai`, chez Cloudflare, sur le compte de MEGGA, comme le moteur.
2. Sa base tient dans Postgres, chez Neon : comptes, sessions, rôles, membres, invitations, journal, compteurs. Rien ne se perd quand le conteneur s'endort.
3. Seul un invité peut y créer un compte.
4. L'admin lit le vrai atelier, par le jeton que Julien pose.
5. L'admin du site a une entrée « Agents » qui y mène.
6. Julien met en ligne par un geste qu'il connaît : « Fusionne et déploie ».

## Hors du périmètre

- Une seule connexion pour le site et la console (les comptes Supabase du site). Deux connexions distinctes, assumées.
- Réécrire les écrans de l'admin dans le site.
- Ouvrir la console aux clients, et le vrai serveur d'agents (lot 11). En ligne, l'équipe d'agents de la racine `/` n'est pas branchée.
- La double authentification, plusieurs conteneurs à la fois, des sauvegardes au-delà de celles de Neon.
- Toucher au moteur (`noyau/`, `atelier/`, `porte/`, `pilote/`, `packs/`, `tests/` à la racine) ou à son workflow « déployer ».
- Reprendre des données : aucune base de production n'existe encore.

## Ce qui serait un échec

- Une page d'inscription ouverte à tous sur Internet.
- Un compte, un rôle ou une ligne de journal perdus.
- Un droit accordé par erreur parce qu'une vérification n'a pas été attendue.
- Un secret dans le dépôt, dans une adresse, dans un journal, ou passé par Claude.
- Un essai ou un développement contre la base ou l'atelier de production.
- Une mise en ligne sans le geste de Julien.

## Les contraintes

- **Le disque d'un conteneur Cloudflare est effacé à chaque veille** (documentation de Cloudflare, Containers, FAQ : « All disk is ephemeral by default »). La base de la console est aujourd'hui un fichier SQLite sur ce disque (`console/src/lib/base.ts`).
- **Le moteur est déjà chez Cloudflare** : un Worker (`porte/`) et des conteneurs pilotés par l'API `ctx.container` (`porte/src/agent.js`, classe `Conteneur`), la zone `megga.ai` sur le compte de MEGGA, `api.megga.ai` servi en domaine personnalisé (`porte/wrangler.jsonc`). Le déploiement part du Mac de Julien ou du workflow « déployer » (`docs/deploiement.md`).
- **La conception du socle prévoyait Postgres** : « Le passage à Postgres (Neon) se fera au déploiement, par l'adaptateur de Better Auth, sans changer le reste » (`2026-11-17-console-socle-design.md`). Le reste change pourtant : les fonctions qui parlent à la base sont synchrones.
- Les textes visibles restent en français, dans `T` et `TA`, sans point médian ni tiret long ; seuls les jetons de `console/src/app/globals.css`.
- Le poste de Thomas n'a pas de Postgres : tout doit continuer à tourner en local sans en installer un.

## Les voies considérées

### Où installer la console

| Voie | Ce qu'elle donne | Ce qu'elle coûte |
|---|---|---|
| **A. Hébergée à part, avec un lien dans l'admin du site** (retenue) | Sa propre adresse, son propre compte. Rien à défaire dans le site. | Deux connexions distinctes. |
| B. Un seul compte pour les deux | Un admin du site est admin de la console. | Refaire la connexion de la console, que Julien a voulue sur Better Auth. |
| C. Les écrans réécrits dans le site | Tout au même endroit. | Un projet entier, et deux versions à tenir. |

Thomas n'a pas objecté à la voie A, proposée le 19.11.2026 ; elle est retenue.

### Où ranger la base

| Voie | Ce qu'elle donne | Ce qu'elle coûte |
|---|---|---|
| **1. Postgres chez Neon** (choisie par Thomas le 19.11.2026) | Comme le moteur, et comme Julien l'a écrit. Rien de neuf à exploiter. | Rendre asynchrones les fonctions de base et jouer les essais sur deux moteurs. |
| 2. Le fichier SQLite copié en continu vers R2 | Presque aucun code à changer. | Une pièce de plus dans l'image, un seul conteneur, jusqu'à une seconde d'écritures perdue sur un arrêt brutal, à refaire quand des clients arriveront. |
| 3. Un hébergeur avec un vrai disque | Aucun code à changer. | Un nouvel hébergeur et sa facture, hors de Cloudflare. |

## La conception

Trois parties, dans cet ordre. Chacune a sa PR.

### Partie 1 : la base passe à Postgres

**Une interface, deux moteurs.** Tout le SQL de `console/src/lib` passe par une petite interface asynchrone (lire une ligne, lire plusieurs lignes, écrire, ouvrir une transaction). Deux moteurs la servent :

- `node:sqlite`, comme aujourd'hui : le moteur du local et des essais, pris quand rien n'est réglé ;
- Postgres : pris quand `CONSOLE_BASE_URL` est posée. C'est le moteur de la production.

SQLite reste pour que personne n'ait à installer Postgres sur son poste, et parce que le moteur suit déjà cette règle (`docs/plan.md`, « les tests tournent aussi sur SQLite »).

**Ce qui devient asynchrone.** Une quarantaine de fonctions exportées de `console/src/lib` prennent la base, presque toutes synchrones ; leur liste se tire du code, pas de ce nombre. Elles deviennent asynchrones, avec leurs fonctions internes et tous leurs appelants : les routes, les pages, `garde`, `gardeSession`, `gardePage`, le compteur de `api/copilotkit`, le script `admin-inviter`.

**Le SQL s'écrit une fois**, dans ce que les deux moteurs comprennent. Ce qui est propre à SQLite aujourd'hui, à remplacer :

- `rowid` dans cinq tris (`agents.ts`, `membres.ts`, `invitations.ts`, `comptes.ts`, `roles.ts`) : trier sur une colonne qui existe des deux côtés ;
- `json_each` (`usage.ts`, `journal.ts`) ;
- `COLLATE NOCASE` pour le nom d'un rôle (`tables.ts`, `roles.ts`) ;
- `INTEGER PRIMARY KEY AUTOINCREMENT` pour le journal (`tables.ts`) ;
- `INSERT OR IGNORE` (`tables.ts`) ;
- `MAX(a, b)` à deux valeurs (`usage.ts`) ;
- `LIKE`, insensible à la casse chez SQLite et sensible chez Postgres (`comptes.ts`) : la recherche de comptes reste insensible à la casse ;
- les `PRAGMA` de `base.ts` ;
- les colonnes de Better Auth en casse mixte (`createdAt`, par exemple), à citer entre guillemets pour Postgres ;
- les valeurs rendues par les tables de Better Auth : booléens et dates n'ont pas la même forme sous les deux moteurs, à ramener à une seule forme à la lecture.

**Better Auth** reçoit la base du moteur choisi. Ses tables et celles de la console se créent au premier appel qui en a besoin, comme aujourd'hui (`migrer` dans `auth.ts`, `base` dans `base.ts`), sans effet si elles existent, sous les deux moteurs.

**Les règles qui tenaient à ce que SQLite fait une chose à la fois.** En asynchrone, deux requêtes peuvent se croiser entre une lecture et l'écriture qui en dépend. Chaque fonction qui lit puis écrit d'après ce qu'elle a lu est donc tenue par une transaction ou par une écriture conditionnelle. Au moins :

- une invitation ne sert qu'une fois (`accepterInvitation`) ;
- il reste toujours un superadmin en cours (`modifierMembre`, `retirerMembre`, et la suspension d'un compte) ;
- un nom de rôle est unique, sans tenir compte de la casse (`creerRole`, `modifierRole`) ;
- un rôle porté par un membre, ou nommé par une invitation en attente, ne se retire pas (`retirerRole`), même si le membre ou l'invitation arrive au même instant ;
- ce qu'une écriture vérifie sur sa cible vaut au moment de l'écriture : le rôle qu'on donne existe encore et porte les droits qu'on a lus, le membre qu'on modifie est tel qu'on l'a lu (`ajouterMembre`, `modifierMembre`, `creerInvitation`).

L'accès de celui qui agit, lui, reste lu une fois par requête par `garde`, comme aujourd'hui : un droit retiré vaut à la requête suivante. `garde` et son `Contexte` ne changent pas de forme, sinon pour attendre.

Chacune de ces cinq règles a un essai qui lance deux opérations en même temps sur Postgres et vérifie que la règle tient (une seule acceptation, un superadmin qui reste, un seul rôle de ce nom, aucun membre sur un rôle retiré, aucun droit donné d'après un rôle qui vient de changer).

**Les garde-fous de la conversion.**

- Le lint typé passe en erreur sur `console/src`, `console/scripts` et `console/tests` : une promesse laissée sans attente, une promesse dans une condition, un `await` sur ce qui n'est pas une promesse.
- Tous les essais Vitest jouent sur les deux moteurs dans la CI (un service Postgres, comme `tests.yml` le fait pour le moteur), et sur SQLite seul en local.
- Les parcours Playwright jouent sur Postgres dans la CI, puisque c'est le moteur de la production, et sur SQLite en local.
- Les 339 essais et les 8 parcours d'aujourd'hui passent sans qu'aucune attente de comportement ne change.

**`npm run admin:inviter`** marche sous les deux moteurs.

### Partie 2 : la mise en ligne

**L'image.** `console/Dockerfile` : Node 24, la console construite en sortie autonome de Next, un utilisateur sans droits, les images de base par leur empreinte (comme `socle/Dockerfile`). Ni le serveur d'agents de l'essai ni l'atelier d'essai n'y entrent.

**Le Worker.** Un Worker à part, `megga-console`, dans `console/hebergement/` (son `wrangler.jsonc`, son code, ses essais). Il ne partage rien avec `porte/`, qui ne bouge pas. Il porte une classe de conteneur, sur le modèle de `Conteneur` dans `porte/src/agent.js` :

- un seul conteneur, toujours le même, en juridiction `eu`, de type `basic` ;
- il s'endort après un temps sans visite ; le premier visiteur attend alors quelques secondes ;
- le domaine personnalisé `console.megga.ai`, sans adresse `workers.dev` ni adresses d'aperçu : une seule origine, celle de `BETTER_AUTH_URL`.

Le Worker transmet tout au conteneur, et fait trois choses de plus :

- il attend que le conteneur réponde sur `/api/sante` avant de transmettre ;
- il écrit `x-forwarded-for` avec l'adresse que Cloudflare a vue (`cf-connecting-ip`), en écrasant ce que le client a envoyé. Better Auth compte alors les connexions par visiteur, et personne ne choisit son adresse ;
- si le conteneur ne démarre pas, il répond une page courte en français, pas une erreur brute.

**`/api/sante`.** Sans session : dit que la console tourne, avec le commit de l'image. Aucun secret. Elle ne touche pas à la base : le Worker n'a pas besoin de Neon pour savoir que le conteneur est prêt.

**Ce que le conteneur reçoit.**

| Nom | Nature | Qui le pose |
|---|---|---|
| `BETTER_AUTH_URL` | `https://console.megga.ai` | le `wrangler.jsonc` |
| `ATELIER_URL` | l'adresse de l'atelier derrière la porte | le `wrangler.jsonc` |
| `BETTER_AUTH_SECRET` | secret | Julien |
| `CONSOLE_BASE_URL` | secret : l'adresse de la base Neon | Julien |
| `ATELIER_JETON` | secret : le jeton MEGGA de l'atelier | Julien |

Julien pose les secrets en saisie masquée, par un script `console/hebergement/secrets.sh` sur le modèle de `scripts/secrets_worker.sh`. Rien ne s'affiche, rien ne passe par Claude.

**L'inscription sur invitation.** Elle est réglée par `CONSOLE_INSCRIPTION` : `invitation` par défaut, `ouverte` seulement si on l'écrit. Le local et les parcours écrivent `ouverte`, pour que la console des agents garde son inscription libre tant qu'elle se développe. En mode `invitation` :

- **Un compte ne se crée qu'avec le lien d'invitation en main.** Les courriels ne sont pas vérifiés : une invitation en attente pour un courriel ne suffit donc pas, sinon quiconque connaît l'adresse d'un invité prendrait son compte avant lui. La page du lien (`rejoindre.tsx`) envoie le jeton avec la demande d'inscription, dans la requête et jamais dans une adresse ; le serveur ne crée le compte que si ce jeton est celui d'une invitation en attente pour ce courriel. La règle est appliquée côté serveur, à la création du compte.
- **Google et Microsoft ne créent jamais de compte**, et un compte Google ou Microsoft ne se lie jamais de lui-même à un compte existant de même courriel. En ligne, leurs clés ne sont de toute façon pas posées : seul le mot de passe sert.
- L'écran de connexion ne propose plus de créer un compte, et un refus dit sa phrase en français (`T`).

**La racine `/` sans serveur d'agents.** En ligne, `AGENTS_URL` n'est pas posée : l'équipe d'agents n'existe pas encore. La racine mène alors à `/admin`, les routes des agents (`/api/agents`, `/api/copilotkit`) répondent qu'elles ne sont pas branchées, et l'admin ne propose pas de retour vers la console des agents. `AGENTS_URL` n'a plus de valeur par défaut dans le code : le local la pose dans `.env.local`, comme `.env.example` le dit déjà.

**Le déploiement.** Deux chemins, le même geste que pour le moteur :

- depuis le Mac de Julien : `cd console/hebergement && npx wrangler deploy --tag <commit>` ;
- un workflow « déployer la console » : à la main seulement, seulement en écrivant « Fusionne et déploie », seulement depuis `main`, avec les mêmes noms de secrets GitHub que « déployer » (`CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`). Le jeton de Cloudflare n'est donné qu'à l'étape de wrangler. D'après `docs/deploiement.md`, ce jeton n'est pas encore posé dans GitHub avec le droit sur la zone : tant qu'il manque, le chemin sûr est le Mac de Julien, et le guide le dit.

**Les deux premiers superadmins.** Une fois en ligne, Julien lance `npm run admin:inviter -- <courriel>` deux fois (lui, puis Thomas), avec l'adresse de la base de production saisie en masqué. Chacun ouvre son lien, crée son compte et entre.

**La CI.** `console.yml` construit l'image et la démarre une fois (elle répond sur `/api/sante`), comme le fait le job `image` du moteur. Les essais du Worker tournent aussi.

**Le guide.** `docs/console-en-ligne.md` : ce que Julien fait une seule fois (la base Neon, les secrets), le déploiement, les deux invitations, et comment revenir en arrière (retirer le domaine du Worker : plus rien n'arrive à la console ; la base reste).

### Partie 3 : l'entrée dans l'admin du site

Dans le dépôt du site (`guiltyspok/megga`, `~/dev/megga`), `AdminLayout` reçoit une entrée « Agents » qui ouvre `https://console.megga.ai/admin` dans un nouvel onglet. Elle n'est visible que des admins du site, comme le reste de cet écran. C'est une PR de ce dépôt, faite après la mise en ligne de la console. Claude l'ouvre à la demande de Thomas et ne la fusionne pas : selon la façon dont le site se déploie (`~/dev/megga/CLAUDE.md`), la fusionner dans `main` peut suffire à la mettre en ligne. Qui tient le dépôt du site la relit et la fusionne.

## L'ordre

1. La PR « base » (partie 1), empilée sur la PR #65. Elle ne déploie rien.
2. La PR « mise en ligne » (partie 2), empilée sur la précédente.
3. Julien relit et fusionne, dans l'ordre : #65, la base, la mise en ligne. Il crée la base Neon, pose les secrets, déploie, invite les deux superadmins.
4. La PR du site (partie 3).

## Ce qui revient à Julien

- Relire et fusionner les trois PR de ce dépôt (#65, la base, la mise en ligne).
- Où créer la base Neon. Un projet à part est recommandé, pour que la console ne garde pas éveillé le calcul des bases des clients (`docs/atelier.md`, « Installations hors Cloudflare », donne ce coût pour l'atelier).
- Les trois secrets.
- Le nom `console.megga.ai`.
- L'inscription sur invitation par défaut (la décision 6 du lot 8, restée ouverte).
- Le déploiement depuis son Mac, ou le droit Workers Routes sur le jeton de GitHub pour le workflow (`docs/deploiement.md` dit qu'il n'est pas encore posé).

## Laissé au constructeur

- Les noms de l'interface de base et de ses fonctions.
- La bibliothèque Postgres (celle que Better Auth documente).
- La façon d'isoler chaque essai sur Postgres (un schéma par fichier d'essai, par exemple).
- La forme exacte du Worker, la durée avant la veille, le texte de la page d'attente.
- Le découpage de la partie 1 en commits, tant que chaque commit laisse les essais verts.

## Les choix de Claude, à corriger

- Le nom `console.megga.ai` et le nom du Worker `megga-console`.
- Les noms `CONSOLE_BASE_URL` et `CONSOLE_INSCRIPTION`.
- SQLite gardé pour le local et les essais, plutôt que Postgres partout.
- L'inscription fermée par défaut, ouverte seulement si on l'écrit.
- Un compte créé seulement depuis la page du lien d'invitation, jeton à l'appui ; Google et Microsoft sans création ni liaison de compte dans ce mode.
- L'accès de celui qui agit lu une fois par requête, comme aujourd'hui ; seule la cible d'une écriture est relue dans la transaction.
- `/api/sante` qui ne touche pas à la base.
- La racine qui mène à `/admin` tant qu'aucun serveur d'agents n'est branché.
- Un seul conteneur, le compteur de connexions de Better Auth en mémoire.
- Les parcours sur Postgres dans la CI, sur SQLite en local.
- Deux PR dans ce dépôt (la base, puis la mise en ligne) plutôt qu'une.
