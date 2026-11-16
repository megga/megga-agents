"""L'environnement d'un conteneur : les secrets en variables, ou en fichiers.

Chez Cloudflare, la porte remet les secrets en variables. Chez le client, ils peuvent aussi
venir de fichiers montés (secrets Docker, Kubernetes, ou l'agent d'un coffre comme Vault ou
Key Vault) : `ANTHROPIC_API_KEY_FILE=/run/secrets/anthropic` vaut `ANTHROPIC_API_KEY`.
"""

from __future__ import annotations

from pathlib import Path

SECRETS = (
    "DATABASE_URL", "META_TOKEN", "META_APP_SECRET", "META_VERIFY_TOKEN", "ANTHROPIC_API_KEY",
    "DEEPSEEK_API_KEY", "ELEVENLABS_API_KEY", "INTERNE_TOKEN", "ADMIN_TOKEN", "MEGGA_LICENCE",
    "PILOTE_CLE", "PILOTAGE_CLE", "REGISTRE_JETON", "GESTIONNAIRES", "GESTION_CLE",
)


def charger(env: dict[str, str]) -> dict[str, str]:
    """L'environnement, avec chaque secret lu dans son fichier s'il n'est pas déjà en variable."""
    sortie = dict(env)
    for k in SECRETS:
        chemin = sortie.get(f"{k}_FILE")
        if not sortie.get(k) and chemin:
            try:
                sortie[k] = Path(chemin).read_text(encoding="utf-8").strip()
            except OSError as e:
                raise RuntimeError(f"{k}_FILE illisible : {chemin}") from e
    return sortie
