# La console MEGGA, premier lot (8.1) : conception

Le 17.11.2026. D'après la maquette validée par Julien et la designer (artefact « Plaquette MEGGA 2 »). Rien n'est fusionné ni déployé sans « Fusionne et déploie » de Julien.

## L'intention

Il n'existe encore aucun écran pour les clients : l'atelier (lot 5) est une API. Ce lot pose la vraie console, l'espace client, avec les trois briques retenues le 16.11.2026 : CopilotKit (branché aux agents par AG-UI), shadcn/ui et Better Auth. Une PME se connecte, crée un agent en deux gestes (prénom et métier), et lui parle tout de suite.

## Les objectifs

1. Une application `console/` (Next.js, TypeScript), avec shadcn/ui et les jetons de couleur de la maquette, en clair et en sombre (« Nuit douce »).
2. La connexion par Better Auth : courriel et mot de passe. Google et Microsoft sont préparés et ne s'allument que si leurs clés sont posées.
3. L'écran principal fidèle à la maquette : le rail (épinglés, conversations avec chaque agent, compte en bas), la conversation et la barre de saisie, branchées à un agent Agno par CopilotKit et AG-UI.
4. La création d'un agent (le Studio de la maquette) : prénom, couleur, yeux, métier. Les huit métiers sont exactement ceux du lot 10 (`atelier/gabarits/`). L'agent est en service dès sa création, sans étape imposée.
5. Des tests, une CI à part, une PR en français simple avec des captures.

## Les non-objectifs

- Les raccourcis du rail (Aujourd'hui, À valider, Planifié, Bibliothèque), les groupes, les conversations à plusieurs, la voix, les pièces jointes, la page « Tous mes agents » : lots suivants. On ne montre pas de bouton qui ne fait rien.
- La mascotte animée du Studio (regard, humeurs) : la tête est dessinée fixe, avec un léger flottement. Son animation complète viendra seule, d'après `mascotte-vivante.html`.
- Le moteur (`noyau`, `atelier`, `packs`, `porte`, `pilote`) et le travail de Thomas (Composio, Docling, Claude Code Action, modèles par métier) : rien n'y est modifié.
- Le déploiement de la console : à décider avec Julien (Cloudflare ou autre).

## Les anti-objectifs (un échec, même si tout marche)

- Un texte visible non relu par Julien, un point médian, un tiret long ou demi-cadratin.
- Deux fois la même information à l'écran (par exemple le prénom de l'agent dans la barre du haut et dans le fil).
- Un contour épais, un contour dans la conversation, un anneau de focus après un clic.
- Une autre icône qu'un engrenage pour les réglages ; une forme du logo GG modifiée.
- Un bouton Google ou Microsoft qui s'affiche sans clés et échoue au clic.
- Un écran qui impose des étapes avant que l'agent ne réponde.

## Les choix

### L'application

- Next.js 16 (App Router), React 19, TypeScript, Tailwind 4, shadcn/ui (pièces copiées dans `console/src/components/ui`).
- Police Figtree (chargée par `next/font`, servie par l'application).
- Jetons : les variables de la maquette (`--bg`, `--side`, `--hover`, `--line`, `--ink`, `--muted`, `--faint`, `--accent`, `--on-accent`, `--ok`, `--warn`, `--soft`, `--shadow`, `--trait`, `--trait-fort`, `--fin`) sont posées telles quelles sur `:root` (clair) et sur `[data-theme="douce"]` (Nuit douce). Les variables de shadcn (`--background`, `--foreground`, `--primary`, `--border`…) en sont dérivées : une seule source de couleurs.
- Le thème suit l'appareil ; le menu du compte permet de le forcer (clair ou sombre), retenu dans le navigateur.
- Les contours : `var(--fin)` (un seul point d'écran : 1px, 0,5px en Retina), jamais dans le fil de la conversation. L'anneau de focus n'apparaît qu'au clavier (`:focus-visible`, retiré après un clic de souris, comme dans la maquette).

### La connexion (Better Auth)

- `better-auth`, courriel et mot de passe, sessions par cookie. La route `/api/auth/[...all]` sert Better Auth ; toutes les pages, sauf `/connexion`, demandent une session (vérifiée côté serveur).
- Base : SQLite intégré à Node (`node:sqlite`) en local, fichier `console/.donnees/console.sqlite` (hors dépôt). Le passage à Postgres (Neon) se fera au déploiement, par l'adaptateur de Better Auth, sans changer le reste.
- Google et Microsoft : déclarés dans `socialProviders` seulement si `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` ou `MICROSOFT_CLIENT_ID`/`MICROSOFT_CLIENT_SECRET` sont posés ; l'écran de connexion n'affiche que les fournisseurs actifs.
- À l'inscription : le nom de l'entreprise (affiché en bas du rail), le courriel, le mot de passe (8 caractères au moins).

### Les agents de la console

- Une table `agent` dans la même base : `id`, `utilisateur`, `prenom`, `metier`, `couleur`, `yeux`, `epingle`, `cree_le`. Un compte voit seulement ses agents.
- Les métiers : la liste fixe des huit identifiants du lot 10 (`generaliste`, `immobilier`, `sante`, `hotellerie`, `juridique`, `commerce`, `fiduciaire`, `garage`), avec les noms de la maquette. Un test vérifie qu'elle reste égale aux gabarits du lot 10 tant qu'ils ne sont pas fusionnés (copie des titres), puis la console les lira à `GET /atelier/gabarits`.
- La création : prénom (20 caractères au plus, comme la maquette) et métier obligatoires ; couleur et yeux facultatifs (rouge et marron par défaut). L'agent est inscrit auprès du serveur d'agents, puis s'ouvre dans le fil avec le message d'accueil de la maquette.
- Épingler : trois agents au plus, comme la maquette. Un agent épinglé quitte la liste des conversations (jamais deux fois à l'écran).
- Le fil de chaque agent est gardé tant que la page reste ouverte ; un message écrit avant que CopilotKit soit prêt part dès qu'il l'est.

### La conversation (CopilotKit et AG-UI)

- Côté serveur de la console, `/api/copilotkit` porte le `CopilotRuntime` de CopilotKit. Pour chaque requête, il vérifie la session, vérifie que l'agent demandé appartient au compte, et le branche par un `HttpAgent` d'AG-UI à l'adresse `AGENTS_URL/agents/<id>/agui`. Le navigateur ne parle jamais directement au serveur d'agents.
- Côté écran, les crochets de CopilotKit (sans ses composants de discussion) : le fil et la barre de saisie sont ceux de la maquette.
- La réponse arrive au fil de l'eau (événements AG-UI).

### Le serveur d'agents pour l'essai local (`console/agents/`)

L'atelier ne sait pas encore servir plusieurs agents par compte ni parler AG-UI (voir « Ce qui manque à l'API »). Pour un essai de bout en bout sans toucher au moteur, un petit serveur Python à côté de la console :

- FastAPI et l'interface AG-UI d'Agno 3.2 (`agno.os.interfaces.agui`, sa fonction `run_entity`), `ag-ui-protocol` en plus.
- `PUT /agents/{id}` `{prenom, metier, entreprise}` : inscrit un agent ; `POST /agents/{id}/agui` : le fait répondre en AG-UI.
- Les consignes viennent du moteur, sans le modifier : `atelier.gabarits.reglages_pour` et `noyau.agent.consignes`. Tant que le lot 10 n'est pas fusionné, un métier inconnu de l'image prend les consignes du généraliste (et le serveur le dit dans son journal).
- Le modèle : Claude (`ANTHROPIC_API_KEY`) ; sans clé, un modèle d'essai local qui répond sans réseau (les tests l'utilisent).
- Protégé par un jeton partagé avec la console (`AGENTS_JETON`) ; il n'écoute que sur `127.0.0.1`.

## Ce qui manque à l'API (noté dans la PR, pas codé dans le moteur)

1. Plusieurs agents par compte : l'atelier compte un agent par client.
2. La création par le client lui-même : `POST /atelier/clients` est réservé à MEGGA.
3. La mise en service immédiate : `activer` refuse un brouillon jamais essayé (sauf MEGGA, qui force).
4. Une entrée AG-UI au fil de l'eau pour un agent en service (l'essai rend une réponse entière ; la PR #35 ouvre la réponse au fil de l'eau).
5. Le lien entre un compte Better Auth et un client de l'atelier (aujourd'hui, un jeton délivré par MEGGA).
6. L'historique d'une conversation de la console (relire un fil après rechargement).

## Les tests

- Vitest : les jetons (clair et sombre complets, sans contour au-delà de `--fin`), la liste des métiers, la validation de la création, l'appartenance d'un agent au compte, les fournisseurs de connexion selon les clés, les textes (ni point médian, ni tiret long ou demi-cadratin).
- Pytest (dans `console/agents/`) : inscription d'un agent, réponse AG-UI au fil de l'eau avec le modèle d'essai, jeton exigé.
- Playwright : inscription, connexion, création d'un agent, message envoyé et réponse reçue, de bout en bout avec le serveur d'agents et son modèle d'essai.
- Une CI à part (`.github/workflows/console.yml`), pour ne pas toucher `tests.yml`, que le lot 10 modifie.

## Les textes

Tous dans `console/src/lib/textes.ts`, repris de la maquette autant que possible. Les nouveaux (connexion, inscription, thème, erreurs) y sont marqués « nouveau » et listés dans la PR pour que Julien les relise avant qu'ils ne soient figés. Espaces insécables de la typographie française devant « : ? ! ; » et dans les guillemets.
