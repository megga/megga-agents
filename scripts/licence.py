"""Les licences des installations chez le client (noyau/licence.py), côté MEGGA.

  .venv/bin/python scripts/licence.py cle
      Une seule fois : crée la paire de clés Ed25519. La clé privée va dans le trousseau macOS
      (service megga-agents-licence), sans s'afficher ; la clé publique dans noyau/licence.pub,
      à commiter (elle part dans l'image).

  .venv/bin/python scripts/licence.py emettre <id-du-client> <jusqu-au AAAA-MM-JJ>
      Une licence signée pour ce client, à lui remettre (elle n'a rien de secret : elle ne
      vaut que pour lui, et seule MEGGA peut en signer une).

  .venv/bin/python scripts/licence.py verifier <id-du-client> <licence>
"""

from __future__ import annotations

import base64
import datetime as dt
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from noyau import licence  # noqa: E402

SERVICE = "megga-agents-licence"


def _cle_privee():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    brut = subprocess.run(["security", "find-generic-password", "-a", "megga-agents", "-s", SERVICE, "-w"],
                          capture_output=True, text=True, check=True).stdout.strip()
    return Ed25519PrivateKey.from_private_bytes(base64.b64decode(brut))


def _au_trousseau() -> bool:
    return subprocess.run(["security", "find-generic-password", "-a", "megga-agents", "-s", SERVICE],
                          capture_output=True).returncode == 0


def cle() -> int:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    if licence.CLE_PUBLIQUE.exists():
        print("noyau/licence.pub existe déjà : une seule paire de clés")
        return 1
    if _au_trousseau():
        print("Une clé des licences est déjà au trousseau (megga-agents-licence), sans noyau/licence.pub.\n"
              "Retrouver sa clé publique plutôt qu'en créer une autre : avec une nouvelle clé, les licences "
              "déjà remises ne vaudraient plus.")
        return 1
    privee = Ed25519PrivateKey.generate()
    brut = privee.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
    # Par l'entrée standard de « security -i », jamais par la ligne de commande (lisible par ps).
    commande = (f'add-generic-password -a megga-agents -s {SERVICE} -l "Clé des licences MEGGA" '
                f'-w {base64.b64encode(brut).decode()}\n')
    if subprocess.run(["security", "-i"], input=commande, text=True, capture_output=True).returncode != 0 or not _au_trousseau():
        print("La clé n'a pas pu être rangée au trousseau : rien n'est créé.")
        return 1
    licence.CLE_PUBLIQUE.write_bytes(privee.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    print("Clé privée : trousseau (megga-agents-licence). Clé publique : noyau/licence.pub, à commiter.")
    return 0


def emettre(client: str, jusqu_au: str) -> int:
    fin = dt.date.fromisoformat(jusqu_au)
    jeton = licence.emettre({"client": client, "jusqu_au": fin.isoformat(), "emise": dt.date.today().isoformat()}, _cle_privee())
    licence.verifier(jeton, client)  # signée par la clé dont la publique est dans l'image
    print(jeton)
    return 0


def verifier(client: str, jeton: str) -> int:
    try:
        print(licence.verifier(jeton, client))
        return 0
    except licence.LicenceRefusee as e:
        print(f"refusée : {e}")
        return 1


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["cle"]:
        sys.exit(cle())
    if a[:1] == ["emettre"] and len(a) == 3:
        sys.exit(emettre(a[1], a[2]))
    if a[:1] == ["verifier"] and len(a) == 3:
        sys.exit(verifier(a[1], a[2]))
    print(__doc__)
    sys.exit(2)
