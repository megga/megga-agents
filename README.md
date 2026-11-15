# megga-agents

La plateforme d'agents IA de MEGGA : un noyau commun (WhatsApp, voix, mémoire, garde-fous), des packs métier, une configuration par client.

Le plan : [docs/plan.md](docs/plan.md).

## Ce qu'il y a ici

| Dossier | Contenu |
|---|---|
| `noyau/` | le noyau Python, sur Agno : configuration, agent, WhatsApp, base, typographie |
| `atelier/` | l'API qui construit et pilote les agents des clients ([docs/atelier.md](docs/atelier.md)) |
| `socle/` | l'image Docker unique (Cloudflare, Suisse, chez le client) |
| `porte/` | le Worker d'entrée des zones Europe et États-Unis, l'objet de chaque client et celui de l'atelier |
| `installation/` | l'installation chez le client : Docker Compose et chart Helm ([docs/installation-client.md](docs/installation-client.md)) |
| `clients/` | des configurations ; seulement un exemple, aucun client réel |
| `tests/` | les essais du noyau |

## Essais

```bash
uv venv --python 3.12 && uv pip install -e ".[test]" && .venv/bin/python -m pytest -q
```

```bash
cd porte && npm ci && npm test
```

Rien n'est déployé sans « Fusionne et déploie » de Julien.
