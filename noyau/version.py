"""La version de l'image : la même partout (Cloudflare, Suisse, chez le client).

  version   celle du paquet (pyproject.toml), figée à la construction de l'image
  revision  le commit d'où l'image est construite (MEGGA_REVISION, passé à la construction)

Deux versions sont soutenues à la fois : la dernière et la précédente. La base suit la
même règle (stockage.migrer) : une image démarre sur une base migrée par la version
suivante, pour qu'un retour arrière reste possible.
"""

from __future__ import annotations

import os
from importlib import metadata


def version() -> str:
    try:
        return metadata.version("megga-agents")
    except metadata.PackageNotFoundError:  # le code lancé depuis le dépôt, sans installation
        return "dev"


def revision() -> str:
    return os.environ.get("MEGGA_REVISION", "") or "inconnue"


def carte() -> dict:
    """Ce que /sante montre de l'image, sans rien de privé."""
    from .config import VERSION as CONFIG
    from .stockage import SCHEMA_VERSION

    return {"version": version(), "revision": revision(), "config": CONFIG, "schema": SCHEMA_VERSION}
