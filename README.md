# megga-agents

La plateforme d'agents IA de MEGGA : un noyau commun (WhatsApp, voix, mémoire, garde-fous), des packs métier, une configuration par client.

Le plan : [docs/plan.md](docs/plan.md).

Clone Agent, le clone IA grand public qui fait à la place de chacun ce qu'il n'aime pas faire : [docs/clone-agent/](docs/clone-agent/README.md) (cadrage, à valider par Julien).

## Ce qu'il y a ici

| Dossier | Contenu |
|---|---|
| `noyau/` | le noyau Python, sur Agno : configuration, agent, WhatsApp, base, typographie |
| `atelier/` | l'API qui construit et pilote les agents des clients ([docs/atelier.md](docs/atelier.md)) |
| `pilote/` | le pilote d'une installation hors Cloudflare : suivi et ordres signés, toujours sortant ([docs/installation-client.md](docs/installation-client.md)) |
| `socle/` | l'image Docker unique (Cloudflare, Suisse, chez le client) |
| `porte/` | le Worker d'entrée des zones Europe et États-Unis, l'objet de chaque client et celui de l'atelier |
| `installation/` | l'installation chez le client : Docker Compose et chart Helm ([docs/installation-client.md](docs/installation-client.md)) |
| `clients/` | les configurations de départ des clients (sans aucun secret) ; celle qui sert est la version en service dans l'atelier |
| `tests/` | les essais du noyau |

## Essais

```bash
uv venv --python 3.12 && uv pip install -e ".[test]" && .venv/bin/python -m pytest -q
```

```bash
cd porte && npm ci && npm test
```

Rien n'est déployé sans « Fusionne et déploie » de Julien.
