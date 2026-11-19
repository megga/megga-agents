# La console MEGGA (lot 8.1)

L'espace client : connexion, création d'un agent (prénom et métier), conversation avec lui. D'après la maquette validée par Julien et la designer (Plaquette MEGGA 2). La conception : [docs/superpowers/specs/2026-11-17-console-socle-design.md](../docs/superpowers/specs/2026-11-17-console-socle-design.md).

| Brique | Rôle |
|---|---|
| Next.js 16, Tailwind 4, [shadcn/ui](https://ui.shadcn.com) | l'application et ses pièces (`src/components/ui`), aux jetons de la maquette (`src/app/globals.css`) |
| [Better Auth](https://better-auth.com) | la connexion : courriel et mot de passe ; Google et Microsoft dès que leurs clés sont posées |
| [CopilotKit](https://copilotkit.ai) et AG-UI | la conversation : `/api/copilotkit` branche chaque agent du compte au serveur d'agents |
| `agents/serveur.py` | le serveur d'agents de l'essai local : un agent Agno par agent de la console, consignes tirées des gabarits et du noyau |

Tous les textes visibles sont dans `src/lib/textes.ts`.

## Lancer en local

```bash
uv venv --python 3.12 && uv pip install -e ".[test]" "ag-ui-protocol==1.0.0"
```

```bash
cd console && npm ci && cp .env.example .env.local
```

Remplir `BETTER_AUTH_SECRET` et `AGENTS_JETON` dans `.env.local`, puis, depuis la racine du dépôt (sans `ANTHROPIC_API_KEY`, l'agent répond avec un modèle d'essai, sans réseau) :

```bash
AGENTS_JETON=<le même> .venv/bin/python -m uvicorn serveur:app --app-dir console/agents --host 127.0.0.1 --port 8100
```

```bash
cd console && npm run dev
```

### L'admin et l'atelier d'essai

L'admin (`/admin`) lit l'atelier. En local, jamais la production : l'atelier d'essai (`agents/atelier_essai.py`), le vrai atelier sur une porte simulée, avec six clients fictifs (une boulangerie qui va bien, un garage en panne, une agence en écart, un chalet installé hors Cloudflare, un fleuriste dont le conteneur ne répond plus, une librairie jamais mise en service). Sa base est dans `.donnees/atelier-essai` ; l'effacer le repeuple. Depuis `console/` :

```bash
ATELIER_JETON=<un jeton> ../.venv/bin/python -m uvicorn atelier_essai:app --app-dir agents --host 127.0.0.1 --port 8198
```

Puis la console contre lui (ou `ATELIER_URL` et `ATELIER_JETON` dans `.env.local`) ; sans `ATELIER_URL`, les écrans du moteur disent qu'il n'est pas branché :

```bash
ATELIER_URL=http://127.0.0.1:8198 ATELIER_JETON=<le même> npm run dev
```

Pour entrer dans `/admin`, il faut un superadmin : cette commande imprime le lien d'invitation du premier, à ouvrir une fois connecté avec ce courriel. Elle ne lit pas `.env.local` : passez-lui `BETTER_AUTH_URL` (par défaut `http://localhost:3000`) et `CONSOLE_BASE` (par défaut `.donnees/console.sqlite`) quand ils diffèrent de ceux de la console.

```bash
npm run admin:inviter -- <courriel>
```

Contre la base de production (Postgres chez Neon), depuis `console/` : l'adresse de la base se tape en masqué, sans passer par l'historique du terminal ni par un fichier, et dans un sous-shell (les parenthèses) : elle meurt avec lui, rien ne reste exporté dans le terminal.

```bash
( read -rs CONSOLE_BASE_URL && export CONSOLE_BASE_URL && BETTER_AUTH_URL=https://console.megga.ai npm run admin:inviter -- <courriel> )
```

### La base

SQLite en local et dans les essais (`.donnees/console.sqlite`, ou `CONSOLE_BASE`) ; Postgres dès que `CONSOLE_BASE_URL` est posée, comme en production. Tout le SQL passe par l'interface de `src/lib/donnees` et s'écrit une fois pour les deux moteurs. Les tables se créent à la première requête (`pret()`, `src/lib/base.ts`).

## Essais

```bash
cd console && npm test && npm run typecheck && npm run lint
```

Sur Postgres aussi, comme la CI : un serveur d'essai jetable (jamais la production), sur lequel chaque essai crée sa propre base, puis la supprime.

```bash
docker run -d --name console-pg-essai -e POSTGRES_PASSWORD=essai -p 55432:5432 postgres:18
CONSOLE_ESSAI_MOTEUR=postgres CONSOLE_BASE_ESSAI_URL=postgres://postgres:essai@localhost:55432/postgres npm test
```

```bash
.venv/bin/python -m pytest -q console/agents
```

```bash
cd console && npx playwright install chromium && npm run test:e2e
```

Rien n'est déployé sans « Fusionne et déploie » de Julien.
