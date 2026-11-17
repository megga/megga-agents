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

## Essais

```bash
cd console && npm test && npm run typecheck && npm run lint
```

```bash
.venv/bin/python -m pytest -q console/agents
```

```bash
cd console && npx playwright install chromium && npm run test:e2e
```

Rien n'est déployé sans « Fusionne et déploie » de Julien.
