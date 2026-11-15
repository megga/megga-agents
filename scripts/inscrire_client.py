"""Inscrit (ou met à jour) un client dans l'annuaire de la porte (D1), d'après sa configuration.

  .venv/bin/python scripts/inscrire_client.py clients/essai.yaml            # inscrit
  .venv/bin/python scripts/inscrire_client.py clients/essai.yaml --a-blanc  # montre seulement

Seules les zones Europe et États-Unis passent par la porte. Aucun secret ici :
l'adresse de la base se pose ensuite avec scripts/secrets_client.sh.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from noyau import config as configuration  # noqa: E402

BASE = "megga-agents-annuaire"


def sql(c: configuration.Config) -> str:
    def q(v: str) -> str:
        return "'" + str(v).replace("'", "''") + "'"

    donnees = json.dumps(c.model_dump(), ensure_ascii=False)
    return (
        "INSERT INTO clients (id, numero_id, zone, config, actif) VALUES "
        f"({q(c.id)}, {q(c.whatsapp.numero_id)}, {q(c.zone)}, {q(donnees)}, 1) "
        "ON CONFLICT(id) DO UPDATE SET numero_id = excluded.numero_id, zone = excluded.zone, "
        "config = excluded.config, actif = 1;\n"
    )


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    c = configuration.lire(sys.argv[1])
    if c.zone not in ("europe", "etats-unis"):
        print(f"zone {c.zone} : ce client ne passe pas par la porte Cloudflare")
        return 1
    commande = sql(c)
    if "--a-blanc" in sys.argv:
        print(commande)
        return 0
    with tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False, encoding="utf-8") as f:
        f.write(commande)
    return subprocess.call(["npx", "wrangler", "d1", "execute", BASE, "--remote", "--file", f.name], cwd=RACINE / "porte")


if __name__ == "__main__":
    sys.exit(main())
