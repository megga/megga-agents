# La console en ligne : plan de construction

> **Pour les agents qui construisent :** sous-compétence requise : superpowers:subagent-driven-development (recommandée) ou superpowers:executing-plans, tâche par tâche. Les étapes se cochent (`- [ ]`).

**But :** la console, dont `/admin`, répond à `https://console.megga.ai`, dans un conteneur Cloudflare du compte MEGGA Inc., sa base dans Postgres chez Neon.

**Architecture :** tout le SQL de `console/src/lib` passe par une interface asynchrone `Base`, servie par `node:sqlite` en local et dans les essais, et par Postgres (`pg`) quand `CONSOLE_BASE_URL` est posée. Next sort en mode autonome dans une image Docker. Un Worker à part, `megga-console`, porte un seul conteneur en zone Europe, derrière le domaine `console.megga.ai`.

**Technique :** Next 16, Better Auth 1.7.25, `node:sqlite`, `pg`, Vitest 5, Playwright 1.65.1, Cloudflare Workers et Containers (wrangler 4), Docker.

**Conception :** `docs/superpowers/specs/2026-11-19-console-en-ligne-design.md`. Ce plan la suit, avec deux décisions de Thomas du 19.11.2026 : l'adresse est `console.megga.ai`, et c'est Thomas qui déploie depuis son Mac, avec l'accord de Julien, avant la fusion des PR. La partie 3 (l'entrée « Agents » dans l'admin du site) n'est pas dans ce plan.

## Contraintes globales

- Les textes visibles restent en français, dans `T` (`console/src/lib/textes.ts`) et `TA` (`console/src/lib/admin/textes.ts`), sans point médian ni tiret long. Seuls les jetons de `console/src/app/globals.css`.
- Aucun secret dans le dépôt, dans une adresse, dans un journal, ni passé par Claude. Les secrets se saisissent en masqué.
- Aucun essai contre la base ou l'atelier de production.
- Le local et les essais continuent de tourner sans Postgres installé.
- Les 339 essais Vitest et les 8 parcours Playwright passent sans qu'aucune attente de comportement ne change. Seule exception admise : un essai qui dépendait de l'ordre d'insertion de deux lignes au même horodatage reçoit deux horodatages distincts.
- Le moteur (`noyau/`, `atelier/`, `porte/`, `pilote/`, `packs/`, `tests/` à la racine) et son workflow « déployer » ne bougent pas.
- Node n'est pas dans le PATH des shells non interactifs de ce Mac. Avant `npm`, `npx` ou `node` : `export PATH="$HOME/.local/share/fnm/node-versions/v24.19.0/installation/bin:$PATH"`.
- Les commandes partent de `console/` sauf mention contraire. Chaque commit laisse `npm run typecheck`, `npm run lint` et `npm test` verts.
- Les messages de commit sont en français, au format du dépôt (`feat(console) : …`), et finissent par `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Points de relecture

Ce que la conception implique sans qu'une tâche ne l'essaie d'elle-même. Chaque ligne a son essai dans la tâche qui en est chargée.

1. **Deux requêtes à la fois sur SQLite.** Une transaction ouverte attend un `await`, une autre requête écrit sur la même connexion : son écriture ne doit ni entrer dans la transaction ni être annulée avec elle (tâche 1, `sérialise une écriture lancée pendant une transaction`).
2. **Neon endort son calcul.** Une connexion du pool coupée par Neon ne doit pas tuer le processus, et la requête suivante doit repartir sur une nouvelle connexion (tâche 1, `survit à une connexion coupée`).
3. **Un jeton d'invitation présenté pour un autre courriel** que celui de l'invitation : le compte n'est pas créé (tâche 7, `refuse un jeton valable pour un autre courriel`).
4. **Un `?` dans une chaîne SQL** (un `ESCAPE '\\'`, un littéral) : la conversion en `$n` pour Postgres ne le touche pas (tâche 1, `ne numérote pas un ? entre apostrophes`).
5. **Le conteneur dort ou ne démarre pas.** Le premier visiteur attend sans erreur brute, et si le démarrage échoue, il reçoit la page d'attente en français, statut 503 (tâche 9, `répond la page d'attente si le conteneur ne démarre pas`).

---

## Partie 1 : la base passe à Postgres (PR « base », empilée sur la PR #65)

### Tâche 1 : l'interface `Base` et ses deux moteurs

**Fichiers :**
- Créer : `console/src/lib/donnees/base.ts` (le type `Base` et `ouvrirBase`), `console/src/lib/donnees/sqlite.ts`, `console/src/lib/donnees/postgres.ts`
- Créer : `console/tests/donnees.test.ts`, `console/tests/moteurs.ts` (l'aide qui donne les moteurs d'essai)
- Modifier : `console/package.json` (ajouter `pg` et `@types/pg`, versions exactes, sorties depuis au moins deux semaines)

**Interfaces :**
- Produit :
  ```ts
  export type Valeur = string | number | boolean | null;
  export type Ligne = Record<string, unknown>;
  export interface Base {
    readonly dialecte: "sqlite" | "postgres";
    un<T extends Ligne>(sql: string, ...params: Valeur[]): Promise<T | undefined>;
    tous<T extends Ligne>(sql: string, ...params: Valeur[]): Promise<T[]>;
    ecrire(sql: string, ...params: Valeur[]): Promise<{ changements: number }>;
    executer(sql: string): Promise<void>; // DDL, une seule instruction, sans paramètre
    transaction<T>(f: (tx: Base) => Promise<T>): Promise<T>;
    pourAuth(): unknown; // ce que Better Auth reçoit dans `database` : la DatabaseSync ou le Pool
    fermer(): Promise<void>;
  }
  export function baseSqlite(chemin: string): Base;          // sqlite.ts
  export function basePostgres(url: string): Base;           // postgres.ts
  export function ouvrirBase(env?: Record<string, string | undefined>): Base; // base.ts : Postgres si CONSOLE_BASE_URL, sinon SQLite sur cheminBase()
  ```
- Produit pour les essais (`tests/moteurs.ts`) : `export function moteursEssai(): ("sqlite" | "postgres")[]` (Postgres seulement si `CONSOLE_BASE_ESSAI_URL` est posée) et `export async function baseVide(moteur): Promise<Base>` (SQLite en mémoire ; Postgres : une base neuve créée sur le serveur de `CONSOLE_BASE_ESSAI_URL`, un nom tiré au hasard, supprimée par `fermer()`).

Les règles des deux moteurs :
- Le SQL s'écrit avec `?`. Postgres les numérote `$1`, `$2`… en sautant ce qui est entre apostrophes ou entre guillemets.
- **SQLite** : une seule connexion, `PRAGMA journal_mode = WAL; PRAGMA foreign_keys = ON;` à l'ouverture (hors `:memory:` pour le WAL). Toute opération passe par un verrou (une file de promesses). `transaction` prend le verrou pour toute sa durée, `BEGIN IMMEDIATE` … `COMMIT` ou `ROLLBACK` ; le `tx` qu'elle passe exécute sans reprendre le verrou. Les booléens passés en paramètre deviennent `1` ou `0`.
- **Postgres** : un `Pool` de `pg` (`max` 5), un écouteur `pool.on("error")` qui écrit la panne sans la relancer. `transaction` prend un client, `BEGIN`, puis `SELECT pg_advisory_xact_lock(4247)` : toutes les transactions de la console passent l'une après l'autre, comme sous SQLite, et les cinq règles de la conception tiennent dès qu'une lecture suivie d'une écriture est dans une transaction. Les types `timestamp` et `timestamptz` se lisent en texte ISO UTC (`toISOString()`), `int8` et `numeric` en nombre.
- `ecrire` rend le nombre de lignes touchées (`changes` sous SQLite, `rowCount` sous Postgres).

- [ ] **Étape 1 : écrire les essais**, chacun joué pour chaque moteur de `moteursEssai()` (`describe.each`) :
  - `écrit puis relit une ligne` : `executer("CREATE TABLE t (id TEXT PRIMARY KEY, n INTEGER)")`, `ecrire("INSERT INTO t VALUES (?, ?)", "a", 1)` rend `{ changements: 1 }`, `un("SELECT n FROM t WHERE id = ?", "a")` rend `{ n: 1 }`, `tous(...)` rend une ligne.
  - `annule une transaction qui échoue` : une écriture puis une erreur dans `transaction` ; la ligne n'existe pas après.
  - `sérialise une écriture lancée pendant une transaction` : une transaction écrit `a`, attend 20 ms, puis lève une erreur ; pendant l'attente, hors transaction, `ecrire` insère `b`. Après : `a` absent, `b` présent.
  - `ne numérote pas un ? entre apostrophes` : `un("SELECT '?' AS q, ? AS v", "x")` rend `{ q: "?", v: "x" }`.
  - `lit un horodatage en texte ISO` (Postgres seulement) : une colonne `timestamptz` relue vaut `"2026-11-18T10:00:00.000Z"`.
  - `survit à une connexion coupée` (Postgres seulement) : `SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = current_database() AND pid <> pg_backend_pid()` depuis une autre connexion, puis `un("SELECT 1 AS n")` rend `{ n: 1 }` (au plus un nouvel essai de la requête sur l'erreur de connexion coupée, `57P01`).

- [ ] **Étape 2 : lancer** `npx vitest run tests/donnees.test.ts` : échec, les modules n'existent pas.
- [ ] **Étape 3 : écrire** `sqlite.ts`, `postgres.ts`, `base.ts` selon les règles ci-dessus.
- [ ] **Étape 4 : lancer** `npx vitest run tests/donnees.test.ts` (SQLite), puis, si un Postgres est à portée, avec `CONSOLE_BASE_ESSAI_URL` : tout passe.
- [ ] **Étape 5 : commit** `feat(console) : une interface de base, servie par SQLite ou Postgres`.

### Tâche 2 : les tables et Better Auth sur l'interface

**Fichiers :**
- Modifier : `console/src/lib/base.ts`, `console/src/lib/admin/tables.ts`, `console/src/lib/auth.ts`, `console/tests/admin/aides.ts`

**Interfaces :**
- Consomme : `Base`, `ouvrirBase`, `baseVide` (tâche 1).
- Produit :
  ```ts
  // base.ts
  export function donnees(): Base;                    // la base de la console, ouverte une fois (globalThis), tables prêtes au premier appel de pret()
  export async function pret(): Promise<Base>;        // donnees(), Better Auth migré, puis preparer() ; à attendre avant toute requête
  export async function preparer(b: Base): Promise<void>;
  // tables.ts
  export async function creerTablesAdmin(b: Base, maintenant?: Date): Promise<void>;
  // auth.ts
  export function optionsAuth(b?: Base): BetterAuthOptions; // database: b.pourAuth()
  // tests/admin/aides.ts
  export async function baseEssai(moteur?: "sqlite" | "postgres"): Promise<Base>; // moteur par défaut : process.env.CONSOLE_ESSAI_MOTEUR ?? "sqlite"
  ```

Le DDL portable :
- `admin_journal.id` : `INTEGER PRIMARY KEY AUTOINCREMENT` sous SQLite, `BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY` sous Postgres. C'est le seul endroit qui lit `b.dialecte`.
- Le nom d'un rôle, unique sans tenir compte de la casse : la colonne perd `COLLATE NOCASE` et `UNIQUE`, et `CREATE UNIQUE INDEX IF NOT EXISTS admin_role_nom ON admin_role (lower(nom))` la remplace.
- `INSERT OR IGNORE` devient `INSERT … ON CONFLICT DO NOTHING`.
- Les colonnes de Better Auth en casse mixte se citent entre guillemets partout : `u."createdAt"`, `"emailVerified"`, `"userId"`, `"expiresAt"`, `"userAgent"`, `"banReason"`.

Une base SQLite déjà créée en local par la PR #65 garde son ancien index `UNIQUE COLLATE NOCASE` : rien à migrer, l'index neuf s'ajoute à côté.

Pendant la conversion, `base()` (la `DatabaseSync`) reste, ouverte sur la même connexion que `donnees()` sous SQLite, pour les modules pas encore convertis. Elle disparaît à la tâche 5.

- [ ] **Étape 1 : écrire l'essai** `tests/admin/tables.test.ts` (nouveau), pour chaque moteur : après `baseEssai()`, `admin_role` contient le superadmin et les rôles de départ ; insérer `"Lecture"` puis `"lecture"` lève une erreur de contrainte ; relancer `creerTablesAdmin` ne double rien et ne remet pas un rôle de départ retiré.
- [ ] **Étape 2 : lancer** `npx vitest run tests/admin/tables.test.ts` : échec.
- [ ] **Étape 3 : écrire** le DDL portable, `preparer`, `donnees`, `pret`, `optionsAuth(b)` et `baseEssai(moteur)` (sous Postgres, `baseVide("postgres")`, puis les migrations de Better Auth, puis `preparer`).
- [ ] **Étape 4 : lancer** `npm test` : tout passe.
- [ ] **Étape 5 : commit** `feat(console) : les tables et Better Auth sur l'interface de base`.

### Tâche 3 : les agents et l'usage

**Fichiers :**
- Modifier : `console/src/lib/agents.ts`, `console/src/lib/admin/usage.ts`, `console/src/app/api/agents/route.ts`, `console/src/app/api/agents/[id]/route.ts`, `console/src/app/api/copilotkit/[[...chemin]]/route.ts`, `console/src/app/page.tsx`, `console/src/lib/auth.ts` (`noterSansBloquer`)
- Essais : `console/tests/agents.test.ts`, `console/tests/admin/usage.test.ts`, `console/tests/admin/couts.test.ts`

**Interfaces :**
- Produit : chaque fonction exportée de `agents.ts` et `usage.ts` qui prenait `db: DatabaseSync` prend `b: Base` et rend une `Promise` du même type qu'avant.

La conversion, ici et aux tâches 4 et 5 :
- `db.prepare(sql).get(...)` devient `await b.un(sql, ...)`, `.all` devient `tous`, `.run` devient `ecrire`.
- `json_each(?)` avec une liste en JSON devient une liste de `?` tirée de la longueur du tableau (`IN (?, ?, ?)`). Un tableau vide ne lance pas de requête.
- `MAX(derniere, excluded.derniere)` devient `CASE WHEN excluded.derniere > compte_connexion.derniere THEN excluded.derniere ELSE compte_connexion.derniere END`.
- `rowid` dans un tri devient la clé primaire de la table (`id`, `utilisateur`).

- [ ] **Étape 1 : passer les essais** de ces trois fichiers à `await` et au moteur de `baseEssai()`, sans changer une seule attente.
- [ ] **Étape 2 : lancer** `npx vitest run tests/agents.test.ts tests/admin/usage.test.ts tests/admin/couts.test.ts` : échec à la compilation.
- [ ] **Étape 3 : convertir** les modules et leurs appelants.
- [ ] **Étape 4 : lancer** `npm run typecheck && npm test` : tout passe.
- [ ] **Étape 5 : commit** `refactor(console) : les agents et l'usage passent par l'interface de base`.

### Tâche 4 : rôles, membres, invitations, garde, et les cinq règles

**Fichiers :**
- Modifier : `console/src/lib/admin/roles.ts`, `membres.ts`, `invitations.ts`, `acces.ts`, `garde.ts`, `personnes.ts`, `console/src/lib/admin/comptes.ts` (la suspension seulement), et toutes les routes et pages qui les appellent
- Essais : `tests/admin/{roles,equipe,equipe-routes,invitations,garde,acces,acces-routes,acces-page,externes,droits}.test.ts` ; créer `tests/admin/concurrence.test.ts`

**Interfaces :**
- Produit : les mêmes fonctions, avec `b: Base` et une `Promise`. `Contexte<P>.db` devient `db: Base`. `garde`, `gardeSession` et `gardePage` attendent la base (`await pret()`), puis lisent l'accès une fois par requête, comme aujourd'hui.

Ce qui se dit autrement :
- `WHERE nom = ? COLLATE NOCASE` devient `WHERE lower(nom) = lower(?)`.
- `COALESCE(u.banned, 0) = 0` devient `u.banned IS NOT TRUE`, et `u?.banned` se lit avec `!!` (booléen sous Postgres, entier sous SQLite).
- Chaque fonction qui lit puis écrit d'après ce qu'elle a lu fait les deux dans une seule `b.transaction(async (tx) => …)`, et n'utilise que `tx` à l'intérieur : `accepterInvitation`, `modifierMembre`, `retirerMembre`, la suspension d'un compte, `creerRole`, `modifierRole`, `retirerRole`, `ajouterMembre`, `creerInvitation`.

- [ ] **Étape 1 : écrire** `tests/admin/concurrence.test.ts`. Pour chaque moteur, chaque essai lance deux opérations par `Promise.allSettled` et vérifie :
  - `une invitation ne sert qu'une fois` : deux `accepterInvitation` du même jeton, une réussite et un refus 404 ; un seul membre ajouté.
  - `il reste un superadmin` : deux superadmins, chacun retire l'autre au même instant ; une seule réussite, un superadmin en cours après.
  - `un seul rôle de ce nom` : `creerRole` de « Lecture » et de « lecture » ; une réussite, un refus 409.
  - `aucun membre sur un rôle retiré` : `retirerRole(r)` et `ajouterMembre(… role: r …)` ; après, soit le rôle existe avec son membre, soit aucun des deux.
  - `aucun droit donné d'après un rôle qui vient de changer` : `modifierRole` qui retire un droit, et `creerInvitation` par un membre qui le donne d'après l'ancien état ; jamais d'invitation qui porte un droit que son auteur n'a plus.
- [ ] **Étape 2 : passer** les autres essais listés à `await`, sans changer une attente. Lancer `npx vitest run tests/admin` : échec.
- [ ] **Étape 3 : convertir** les modules, leurs routes et leurs pages, puis les transactions.
- [ ] **Étape 4 : lancer** `npm run typecheck && npm test` : tout passe.
- [ ] **Étape 5 : commit** `refactor(admin) : l'équipe passe par l'interface de base, ses règles tiennent à deux requêtes à la fois`.

### Tâche 5 : le reste de l'admin, le script, et la fin de `DatabaseSync`

**Fichiers :**
- Modifier : `console/src/lib/admin/{comptes,journal,externes,suivi,versions}.ts`, les routes et pages qui restent, `console/scripts/admin-inviter.ts`, `console/src/lib/base.ts` (retirer `base()`), `console/.env.example`, `console/README.md`
- Essais : tous ceux qui restent sous `tests/admin`, plus `tests/admin/commande.test.ts`

**Interfaces :**
- Produit : plus aucun `DatabaseSync` hors de `src/lib/donnees/sqlite.ts` et de `tests/moteurs.ts`.

Ce qui se dit autrement :
- La recherche de comptes : `lower(u.name) LIKE lower(?) ESCAPE '\'` (et de même pour `u.email`), insensible à la casse sous les deux moteurs.
- `ORDER BY u."createdAt" DESC, u.id DESC`.
- Le journal filtré par périmètre : `cible IN (?, ?, …)` sur les `'client:' + id`, tirés en JS.
- `admin:inviter` ouvre la base par `pret()`, donc Postgres si `CONSOLE_BASE_URL` est posée. Le README dit comment le lancer contre la production : `read -rs CONSOLE_BASE_URL && export CONSOLE_BASE_URL && BETTER_AUTH_URL=https://console.megga.ai npm run admin:inviter -- <courriel>`.
- `.env.example` documente `CONSOLE_BASE_URL` (vide en local) à côté de `CONSOLE_BASE`.

- [ ] **Étape 1 : passer les essais restants** à `await`. Ajouter à `comptes.test.ts` : `la recherche ignore la casse` (« ALICE » trouve `alice@megga.test`).
- [ ] **Étape 2 : convertir**, puis retirer `base()`.
- [ ] **Étape 3 : vérifier** que `grep -rn "DatabaseSync\|node:sqlite" src scripts tests | grep -v "src/lib/donnees/sqlite.ts\|tests/moteurs.ts"` ne rend rien.
- [ ] **Étape 4 : lancer** `npm run typecheck && npm run lint && npm test` : tout passe ; puis `npx playwright test --config playwright.local.config.ts` (fichier local hors dépôt) : 8 sur 8.
- [ ] **Étape 5 : commit** `refactor(admin) : toute la console passe par l'interface de base`.

### Tâche 6 : le lint typé et la CI sur les deux moteurs

**Fichiers :**
- Modifier : `console/eslint.config.mjs`, `.github/workflows/console.yml`, `console/playwright.config.ts`

- [ ] **Étape 1 : passer en erreur**, sur `src`, `scripts` et `tests`, avec les types du projet : `@typescript-eslint/no-floating-promises`, `@typescript-eslint/no-misused-promises`, `@typescript-eslint/await-thenable`. Lancer `npm run lint` et corriger ce qu'il trouve.
- [ ] **Étape 2 : la CI.** Dans `console.yml`, un service `postgres:18` (empreinte, comme `tests.yml` le fait pour le moteur), puis `npm test` deux fois : sans variable (SQLite), puis avec `CONSOLE_ESSAI_MOTEUR=postgres` et `CONSOLE_BASE_ESSAI_URL=postgres://postgres:postgres@localhost:5432/postgres`. Les parcours Playwright tournent avec `CONSOLE_BASE_URL` sur ce service : `playwright.config.ts` passe la variable au serveur de Next quand elle est posée.
- [ ] **Étape 3 : pousser** la branche et ouvrir la PR « base », en brouillon, empilée sur `claude/megga-agents-admin-section-adf144`. Lire la CI : verte sur les deux moteurs.
- [ ] **Étape 4 : commit** `ci(console) : les essais jouent sur SQLite et sur Postgres, le lint attend les promesses`.

---

## Partie 2 : la mise en ligne (PR « mise en ligne », empilée sur la PR « base »)

### Tâche 7 : l'inscription sur invitation, `/api/sante`, la racine sans serveur d'agents

**Fichiers :**
- Modifier : `console/src/lib/auth.ts`, `console/src/app/admin/invitation/[jeton]/rejoindre.tsx`, `console/src/app/connexion/connexion.tsx`, `console/src/lib/serveur-agents.ts`, `console/src/app/page.tsx`, les routes `api/agents` et `api/copilotkit`, `console/src/lib/textes.ts`, `console/.env.example`, `console/playwright.config.ts`
- Créer : `console/src/app/api/sante/route.ts`
- Essais : `console/tests/inscription.test.ts` (nouveau), `console/tests/sante.test.ts` (nouveau), `console/tests/connexion.test.ts`

**Interfaces :**
- Produit : `export function inscriptionOuverte(env = process.env): boolean` (vrai seulement si `CONSOLE_INSCRIPTION === "ouverte"`), dans `auth.ts`. L'en-tête `x-megga-invitation-token` porte le jeton du lien. `serveurAgents(): string | null` (null sans `AGENTS_URL`).

Ce qui change :
- En mode invitation, `databaseHooks.user.create.before` lit `x-megga-invitation-token` dans la requête, et refuse (`APIError("FORBIDDEN", { message: T.inscriptionSurInvitation })`) sauf si ce jeton est celui d'une invitation en attente pour ce courriel. Sans en-tête, Google et Microsoft sont refusés de la même façon. `account.accountLinking.enabled` vaut `false` dans ce mode.
- `rejoindre.tsx` envoie le jeton à l'inscription, par `fetchOptions: { headers: { "x-megga-invitation": jeton } }`, jamais dans une adresse. Le commentaire « jamais envoyé au serveur » est corrigé.
- L'écran de connexion ne propose plus de créer un compte quand l'inscription est fermée. `T.inscriptionSurInvitation` : « Un compte se crée depuis un lien d'invitation. »
- `GET /api/sante`, sans session : `{ "ok": true, "revision": process.env.CONSOLE_REVISION ?? null }`. Elle ne touche pas à la base.
- Sans `AGENTS_URL`, `/` redirige vers `/admin`, `/api/agents` et `/api/copilotkit` répondent 503 avec `T.agentsNonBranches` (« L'équipe d'agents n'est pas encore branchée. »), et l'admin ne montre pas de retour vers la console des agents.
- `.env.example` : `CONSOLE_INSCRIPTION=ouverte` pour le local. `playwright.config.ts` pose `CONSOLE_INSCRIPTION=ouverte` et `AGENTS_URL`.

- [ ] **Étape 1 : écrire les essais.** `inscription.test.ts`, par appel direct de `auth().api.signUpEmail` sur une base d'essai :
  - `refuse une inscription sans invitation` (mode invitation) ;
  - `refuse un jeton valable pour un autre courriel` ;
  - `accepte le jeton de l'invitation de ce courriel`, puis l'invitation reste à accepter par sa route ;
  - `laisse tout passer quand l'inscription est ouverte`.

  `sante.test.ts` : `GET` rend 200 et `{ ok: true, revision: "abc" }` avec `CONSOLE_REVISION=abc`, sans base ouverte.
- [ ] **Étape 2 : lancer** `npx vitest run tests/inscription.test.ts tests/sante.test.ts` : échec.
- [ ] **Étape 3 : écrire** le mode invitation, la page du lien, `/api/sante`, la racine.
- [ ] **Étape 4 : lancer** `npm run typecheck && npm run lint && npm test`, puis les parcours en local : tout passe.
- [ ] **Étape 5 : commit** `feat(console) : en ligne, un compte ne se crée que par invitation`.

### Tâche 8 : l'image

**Fichiers :**
- Créer : `console/Dockerfile`, `console/.dockerignore`
- Modifier : `console/next.config.ts` (`output: "standalone"`), `.github/workflows/console.yml` (un job `image`)

Ce qu'elle contient : Node 24 par empreinte (`node:24-…@sha256:…`, comme `socle/Dockerfile`), une étape de construction (`npm ci`, `npm run build`), puis une image d'exécution avec `.next/standalone`, `.next/static` et `public`, un utilisateur sans droits, `PORT=3000`, `HOSTNAME=0.0.0.0`, `CMD ["node", "server.js"]`. Ni `agents/` ni l'atelier d'essai n'y entrent. `CONSOLE_REVISION` est un argument de construction.

- [ ] **Étape 1 : construire** depuis la racine du dépôt : `docker build -f console/Dockerfile -t megga-console console`.
- [ ] **Étape 2 : démarrer** `docker run --rm -d -p 3300:3000 -e BETTER_AUTH_SECRET=essai -e BETTER_AUTH_URL=http://localhost:3300 megga-console`, puis `curl -s localhost:3300/api/sante` rend `{"ok":true,…}` et `curl -sI localhost:3300/connexion` rend 200. Arrêter le conteneur.
- [ ] **Étape 3 : le job `image`** de `console.yml` fait la même chose dans la CI.
- [ ] **Étape 4 : commit** `feat(console) : l'image de la console`.

### Tâche 9 : le Worker `megga-console`, ses secrets, le guide

**Fichiers :**
- Créer : `console/hebergement/wrangler.jsonc`, `console/hebergement/package.json` (wrangler à la version de `porte/`), `console/hebergement/src/index.js`, `console/hebergement/test/index.test.js` (avec `node --test` et un faux `ctx.container`, sur le modèle de `porte/test`), `console/hebergement/secrets.sh`, `docs/console-en-ligne.md`
- Modifier : `.github/workflows/console.yml` (les essais du Worker)

**Interfaces :**
- `wrangler.jsonc` : `name: "megga-console"`, `main: "src/index.js"`, `compatibility_date: "2026-11-01"`, `workers_dev: false`, `preview_urls: false`, `routes: [{ "pattern": "console.megga.ai", "custom_domain": true }]`, un conteneur `ConsoleConteneur` (`image: "../Dockerfile"`, `image_build_context: ".."`, `instance_type: "basic"`, `max_instances: 1`, `constraints: { jurisdiction: "eu" }`), son objet durable (`storage: "sqlite"`), `version_metadata` (binding `VERSION`), `observability` activée, et `vars` : `BETTER_AUTH_URL = "https://console.megga.ai"`, `ATELIER_URL = "https://megga-agents.api-963.workers.dev"` (le code ajoute `/atelier`).
- `src/index.js` : `export default { fetch }` qui transmet tout à `env.CONSOLE.jurisdiction("eu").getByName("console")`, et `export class ConsoleConteneur extends DurableObject`.

Ce que fait `ConsoleConteneur`, sur le modèle de `Conteneur` (`porte/src/agent.js`) :
- au besoin, `ctx.container.start({ enableInternet: true, env })`, avec `env` = `BETTER_AUTH_URL`, `ATELIER_URL`, `CONSOLE_INSCRIPTION=invitation`, `CONSOLE_REVISION` (de `VERSION.tag`) et les secrets `BETTER_AUTH_SECRET`, `CONSOLE_BASE_URL`, `ATELIER_JETON` (ce dernier seulement s'il est posé) ; puis attendre `/api/sante` sur le port 3000, au plus 60 s ;
- `setInactivityTimeout(15 min)` ;
- transmettre la requête au port 3000, `x-forwarded-for` remplacé par `cf-connecting-ip` ;
- un démarrage qui échoue : statut 503, une page courte en français, `retry-after: 10`, rien de technique.

`secrets.sh` (sur le modèle de `scripts/secrets_worker.sh`) : `BETTER_AUTH_SECRET` est tiré par `openssl rand -base64 32` et envoyé à `wrangler secret put` par un tube, sans s'afficher ; `CONSOLE_BASE_URL` et `ATELIER_JETON` se lisent par `read -rs`, et un champ vide passe son tour. Rien ne s'écrit sur le disque.

`docs/console-en-ligne.md` : la base Neon (un projet à part, AWS Francfort, l'adresse sans regroupeur), les secrets, le déploiement (`cd console/hebergement && npx wrangler deploy --tag "$(git rev-parse --short HEAD)"`), les deux invitations, et comment revenir en arrière (retirer le domaine du Worker ; la base reste).

- [ ] **Étape 1 : écrire les essais** du Worker :
  - `transmet à la console et écrase x-forwarded-for` : une requête qui porte `x-forwarded-for: 6.6.6.6` et `cf-connecting-ip: 1.2.3.4` arrive au faux conteneur avec `x-forwarded-for: 1.2.3.4` ;
  - `démarre le conteneur avec ses variables` : `start` reçoit `CONSOLE_INSCRIPTION: "invitation"` et les secrets posés, pas `ATELIER_JETON` s'il manque ;
  - `répond la page d'attente si le conteneur ne démarre pas` : 503, `content-type` HTML, le texte français, aucun message d'erreur technique.
- [ ] **Étape 2 : lancer** `cd console/hebergement && npm test` : échec.
- [ ] **Étape 3 : écrire** le Worker, `secrets.sh` et le guide.
- [ ] **Étape 4 : lancer** `npm test` (essais du Worker), puis `npx wrangler deploy --dry-run` : la configuration se lit et l'image se construit.
- [ ] **Étape 5 :** commit `feat(console) : le Worker megga-console et son guide`, puis pousser et ouvrir la PR « mise en ligne », en brouillon, empilée sur la PR « base ».

---

## La mise en service (Thomas et la session, pas les agents)

1. **Thomas** : créer le projet Neon `megga-console` (AWS Francfort, Postgres 18) et garder sous la main son adresse sans regroupeur.
2. **Thomas** : `cd console/hebergement && ./secrets.sh` (saisie masquée).
3. **La session** : `npx wrangler deploy --tag <commit>` depuis ce Mac (compte MEGGA Inc.), puis vérifier `curl -s https://console.megga.ai/api/sante` et la page `/connexion`.
4. **Thomas** : lancer `admin:inviter` deux fois contre la base de production (README, tâche 5), pour lui puis pour Julien ; ouvrir son lien, créer son compte, entrer dans `/admin`.
5. **La session** : vérifier qu'une inscription sans invitation est refusée sur `https://console.megga.ai`.
