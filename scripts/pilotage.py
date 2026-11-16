"""La clé de pilotage de MEGGA (noyau/pilotage.py) : elle signe les ordres que l'atelier envoie aux
installations hors Cloudflare (chez le client, zone suisse). Elle est distincte de la clé des licences.

  .venv/bin/python scripts/pilotage.py cle
      Une seule fois : la paire de clés Ed25519. La clé privée va dans le trousseau macOS (service
      megga-agents-pilotage), sans s'afficher ; la clé publique dans noyau/pilotage.pub, à commiter :
      elle part dans l'image, et chaque installation vérifie les ordres avec elle.

  .venv/bin/python scripts/pilotage.py poser <adresse-de-la-porte>
      Remet la clé privée à l'atelier (PUT /admin/atelier/secrets), sans l'afficher ; l'atelier
      redémarre et signe dès lors les ordres.

  .venv/bin/python scripts/pilotage.py installation <id-du-client> <adresse-de-la-porte> <clé publique>
      La mise en service d'une installation : enregistre dans l'atelier la clé publique qu'elle a
      remise (python -m pilote cle, chez le client). Rien de secret.

  .venv/bin/python scripts/pilotage.py image <id-du-client> <adresse-de-la-porte> <version> <image>
      Une version publiée (docs/deploiement.md, « Publier une version ») pour cette installation :
      <image> est ghcr.io/megga/megga-agents@sha256:<empreinte>. Son pilote la vérifie et l'installe
      si le client l'a permis (MISES_A_JOUR=oui), sinon elle lui est proposée.
"""

from __future__ import annotations

import base64
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from noyau import pilotage  # noqa: E402

SERVICE = "megga-agents-pilotage"


def _trousseau(service: str) -> str:
    return subprocess.run(["security", "find-generic-password", "-a", "megga-agents", "-s", service, "-w"],
                          capture_output=True, text=True, check=True).stdout.strip()


def _au_trousseau() -> bool:
    return subprocess.run(["security", "find-generic-password", "-a", "megga-agents", "-s", SERVICE],
                          capture_output=True).returncode == 0


def cle() -> int:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    if pilotage.CLE_PUBLIQUE.exists():
        print("noyau/pilotage.pub existe déjà : une seule paire de clés")
        return 1
    if _au_trousseau():
        print("Une clé de pilotage est déjà au trousseau (megga-agents-pilotage), sans noyau/pilotage.pub.\n"
              "Retrouver sa clé publique plutôt qu'en créer une autre : avec une nouvelle clé, les ordres déjà "
              "signés ne vaudraient plus.")
        return 1
    privee = Ed25519PrivateKey.generate()
    brut = privee.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
    # Par l'entrée standard de « security -i », jamais par la ligne de commande (lisible par ps).
    commande = (f'add-generic-password -a megga-agents -s {SERVICE} -l "Clé de pilotage MEGGA" '
                f'-w {base64.b64encode(brut).decode()}\n')
    if subprocess.run(["security", "-i"], input=commande, text=True, capture_output=True).returncode != 0 or not _au_trousseau():
        print("La clé n'a pas pu être rangée au trousseau : rien n'est créé.")
        return 1
    pilotage.CLE_PUBLIQUE.write_bytes(privee.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    print("Clé privée : trousseau (megga-agents-pilotage). Clé publique : noyau/pilotage.pub, à commiter.\n"
          "Puis, une fois la porte déployée : scripts/pilotage.py poser <adresse-de-la-porte>")
    return 0


def _appel(methode: str, url: str, corps: dict) -> int:
    """Un appel à la porte avec le jeton d'administration (trousseau) ; seule sa réponse s'affiche. En https seulement :
    le jeton, et pour « poser » la clé privée de pilotage, ne voyagent jamais en clair."""
    if not url.startswith("https://"):
        print("l'adresse de la porte : en https")
        return 2
    requete = urllib.request.Request(url, method=methode, data=json.dumps(corps).encode(),
                                     headers={"authorization": f"Bearer {_trousseau('megga-agents-admin')}",
                                              "content-type": "application/json",
                                              # Cloudflare refuse l'en-tête par défaut d'urllib (erreur 1010).
                                              "user-agent": "megga-scripts"})
    try:
        with urllib.request.urlopen(requete, timeout=60) as r:
            print(r.read().decode()[:500])
            return 0
    except urllib.error.HTTPError as e:
        print(f"refusé ({e.code}) : {e.read().decode()[:500]}")
        return 1


def poser(porte: str) -> int:
    # La clé privée va du trousseau à la porte, sans passer par l'écran ni la ligne de commande.
    return _appel("PUT", f"{porte.rstrip('/')}/admin/atelier/secrets", {"PILOTAGE_CLE": _trousseau(SERVICE)})


def installation(client: str, porte: str, cle_publique: str) -> int:
    pilotage.cle_publique(cle_publique)  # lisible avant de l'envoyer
    return _appel("PUT", f"{porte.rstrip('/')}/atelier/clients/{client}/installation", {"cle_publique": cle_publique})


def image(client: str, porte: str, version: str, image_: str) -> int:
    if not (pilotage.VERSION_IMAGE.fullmatch(version) and pilotage.IMAGE.fullmatch(image_)):
        print("version 0.2.0 et image ghcr.io/megga/megga-agents@sha256:<empreinte> attendues")
        return 2
    return _appel("POST", f"{porte.rstrip('/')}/atelier/clients/{client}/installation/image", {"version": version, "image": image_})


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["cle"]:
        sys.exit(cle())
    if a[:1] == ["poser"] and len(a) == 2:
        sys.exit(poser(a[1]))
    if a[:1] == ["installation"] and len(a) == 4:
        sys.exit(installation(a[1], a[2], a[3]))
    if a[:1] == ["image"] and len(a) == 5:
        sys.exit(image(a[1], a[2], a[3], a[4]))
    print(__doc__)
    sys.exit(2)
