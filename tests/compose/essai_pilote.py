"""L'essai de bout en bout du pilotage avec Docker Compose (lot 6.3).

L'installation du client telle que le guide la décrit (installation/compose : base, agent, pilote),
avec un atelier d'essai lancé à côté (la même image, base SQLite) à la place de la porte de MEGGA.
Clés, licence et mots de passe sont jetables : créés pour l'essai, effacés avec lui, jamais affichés.

  .venv/bin/python tests/compose/essai_pilote.py [dossier de travail]

Le dossier doit être vu par Docker (avec Colima : sous le dossier personnel, par exemple
~/Library/Caches/megga-essai-pilote). L'image est construite depuis le dépôt (socle/Dockerfile),
puis les clés publiques d'essai (licence, pilotage) y sont ajoutées.

Le parcours : MEGGA crée le client et enregistre la clé de l'installation ; une version part,
l'agent la prend et redémarre de lui-même ; une deuxième ; puis, avec l'accord du client, une
troisième, acceptée par python -m pilote ; le suivi arrive sans aucune conversation ; le client
revient à son fichier ; MEGGA révoque la clé.
"""

from __future__ import annotations

import base64
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

import yaml
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

RACINE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RACINE))

from noyau import licence  # noqa: E402

PROJET = "megga-essai-pilote"
IMAGE_BASE = "megga-agents:essai-pilote"
IMAGE = "megga-agents:essai-pilote-cles"
CLIENT = "essai-pilote"
DELAI = 300


def brut(cle) -> str:
    return base64.b64encode(cle.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                                              serialization.NoEncryption())).decode()


def pem(cle) -> bytes:
    return cle.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)


def port_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Essai:
    def __init__(self, dossier: Path):
        self.dossier = dossier
        self.admin = secrets.token_urlsafe(24)
        self.port = port_libre()

    def compose(self, *args: str, env: dict | None = None, verifier: bool = True) -> str:
        r = subprocess.run(["docker", "compose", "-p", PROJET, "-f", "docker-compose.yml", "-f", "essai.yml", *args],
                           cwd=self.dossier, capture_output=True, text=True, env={**os.environ, **(env or {})})
        if verifier and r.returncode != 0:
            raise RuntimeError(f"docker compose {' '.join(args)} : {r.stderr[-800:]}")
        return r.stdout

    def atelier(self, methode: str, chemin: str, corps: dict | None = None) -> tuple[int, dict]:
        requete = urllib.request.Request(f"http://127.0.0.1:{self.port}{chemin}", method=methode,
                                         data=None if corps is None else json.dumps(corps).encode(),
                                         headers={"authorization": f"Bearer {self.admin}", "content-type": "application/json"})
        try:
            with urllib.request.urlopen(requete, timeout=30) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def sante_agent(self) -> dict:
        sortie = self.compose("exec", "-T", "agent", "python", "-c",
                              "import urllib.request;print(urllib.request.urlopen('http://localhost:8080/sante').read().decode())",
                              verifier=False)
        try:
            return json.loads(sortie.strip().splitlines()[-1])
        except (ValueError, IndexError):
            return {}

    def attendre(self, quoi: str, condition, delai: float = DELAI):
        fin = time.monotonic() + delai
        while time.monotonic() < fin:
            try:
                v = condition()
                if v:
                    print(f"  ok : {quoi}")
                    return v
            except Exception:  # un conteneur qui redémarre : on réessaie
                pass
            time.sleep(3)
        print(self.compose("logs", "--tail", "40", "agent", "pilote", "atelier", verifier=False))
        raise AssertionError(f"pas atteint en {delai:.0f} s : {quoi}")

    def ordres(self) -> dict[int, str]:
        _, d = self.atelier("GET", f"/atelier/clients/{CLIENT}/installation")
        return {o["numero"]: o["etat"] for o in d.get("ordres", [])}

    def pilote(self, *args: str) -> str:
        return self.compose("exec", "-T", "pilote", "python", "-m", "pilote", *args)

    def redemarrages_agent(self) -> int:
        ident = self.compose("ps", "-q", "agent").strip()
        return int(subprocess.run(["docker", "inspect", "-f", "{{.RestartCount}}", ident], capture_output=True, text=True).stdout.strip() or 0)

    def version(self, numero_attendu: int, **changements) -> int:
        code, v = self.atelier("POST", f"/atelier/clients/{CLIENT}/versions", {"changements": changements})
        assert code == 201, v
        assert v["version"] == numero_attendu, v
        code, a = self.atelier("POST", f"/atelier/clients/{CLIENT}/versions/{v['version']}/activer", {"forcer": True})
        assert code == 200, a
        return a["pilotage"]["ordre"]


def preparer(dossier: Path, essai: Essai) -> None:
    licence_cle, pilotage_cle, installation_cle = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    construction = dossier / "image"
    construction.mkdir()
    (construction / "licence.pub").write_bytes(pem(licence_cle))
    (construction / "pilotage.pub").write_bytes(pem(pilotage_cle))
    (construction / "Dockerfile").write_text(
        f"FROM {IMAGE_BASE}\n"
        "COPY licence.pub pilotage.pub /app/noyau/\n"
        "COPY licence.pub pilotage.pub /usr/local/lib/python3.12/site-packages/noyau/\n")
    for f in ("docker-compose.yml", "Caddyfile"):
        shutil.copy(RACINE / "installation" / "compose" / f, dossier / f)
    conf = yaml.safe_load((RACINE / "clients" / "exemple.yaml").read_text())
    conf.update(id=CLIENT, zone="client")
    (dossier / "client.yaml").write_text(yaml.safe_dump(conf, allow_unicode=True))
    jeton = licence.emettre({"client": CLIENT, "jusqu_au": "2099-12-31"}, licence_cle)
    (dossier / ".env").write_text(
        f"MEGGA_IMAGE={IMAGE}\nDOMAINE=essai.invalid\nPOSTGRES_PASSWORD={secrets.token_urlsafe(18)}\n"
        "PILOTAGE=complet\nPILOTAGE_ACCORD=non\nPILOTAGE_URL=http://atelier:8080\nPILOTAGE_INTERVALLE=3\n")
    (dossier / "secrets.env").write_text(
        f"MEGGA_LICENCE={jeton}\nMETA_TOKEN=essai\nMETA_APP_SECRET=essai\nMETA_VERIFY_TOKEN=essai\n"
        "ANTHROPIC_API_KEY=\nDEEPSEEK_API_KEY=\n")
    # Comme le guide : la clé PKCS8 d'openssl, en base64 sur une ligne.
    der = installation_cle.private_bytes(serialization.Encoding.DER, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    (dossier / "pilote.env").write_text(f"PILOTE_CLE={base64.b64encode(der).decode()}\n")
    for f in ("secrets.env", "pilote.env"):
        (dossier / f).chmod(0o600)
    # L'atelier d'essai, à la place de la porte : la même image, en service « atelier ».
    (dossier / "essai.yml").write_text(yaml.safe_dump({"services": {"atelier": {
        "image": IMAGE,
        "environment": {"MEGGA_SERVICE": "atelier", "DATABASE_URL": "sqlite:////tmp/atelier.db",
                        "ADMIN_TOKEN": "${ESSAI_ADMIN:?}", "PILOTAGE_CLE": "${ESSAI_PILOTAGE_CLE:?}"},
        "ports": [f"127.0.0.1:{essai.port}:8080"],
    }}}))
    os.environ["ESSAI_ADMIN"] = essai.admin
    os.environ["ESSAI_PILOTAGE_CLE"] = brut(pilotage_cle)


def parcours(essai: Essai) -> None:
    print("Démarrage : base, agent, pilote, atelier d'essai")
    essai.compose("up", "-d", "base", "agent", "pilote", "atelier")
    essai.attendre("l'atelier répond", lambda: essai.atelier("GET", "/sante")[1].get("pilotage") is True, 180)
    essai.attendre("l'agent répond, sur son fichier",
                   lambda: essai.sante_agent().get("configuration") == {"source": "fichier"}, 240)

    print("Mise en service : MEGGA crée le client et enregistre la clé de l'installation")
    conf = yaml.safe_load((essai.dossier / "client.yaml").read_text())
    code, d = essai.atelier("POST", "/atelier/clients", {"config": conf})
    assert code == 201, d
    publique = essai.pilote("cle").strip()
    assert publique and "PRIVATE" not in publique
    code, d = essai.atelier("PUT", f"/atelier/clients/{CLIENT}/installation", {"cle_publique": publique})
    assert code == 200, d

    print("Version 1 : l'ordre part, l'agent la prend et redémarre de lui-même")
    code, a = essai.atelier("POST", f"/atelier/clients/{CLIENT}/versions/1/activer", {"forcer": True})
    assert code == 200 and a["pilotage"]["ordre"] == 1, a
    essai.attendre("ordre 1 appliqué", lambda: essai.ordres().get(1) == "applique")
    assert essai.sante_agent()["configuration"] == {"source": "pilotage", "version": 1, "ordre": 1}
    assert essai.redemarrages_agent() >= 1, "l'agent aurait dû redémarrer de lui-même"

    print("Version 2 : le ton change")
    assert essai.version(2, ton="direct") == 2
    essai.attendre("ordre 2 appliqué", lambda: essai.ordres().get(2) == "applique")
    assert essai.sante_agent()["configuration"]["version"] == 2

    print("Version 3, avec l'accord du client")
    essai.compose("up", "-d", "pilote", env={"PILOTAGE_ACCORD": "oui"})
    assert essai.version(3, nom_agent="Lea") == 3
    essai.attendre("ordre 3 en attente d'accord", lambda: essai.ordres().get(3) == "attente_accord")
    liste = essai.pilote("ordres")
    assert "attend votre accord" in liste and "nom_agent" in liste and "Lea" in liste, liste
    assert "accepté" in essai.pilote("accepter", "3")
    essai.attendre("ordre 3 appliqué", lambda: essai.ordres().get(3) == "applique")
    assert essai.sante_agent()["configuration"]["version"] == 3

    print("Suivi : il arrive, sans aucune conversation")
    code, s = essai.attendre("le suivi est là", lambda: (lambda r: r if r[0] == 200 else None)(
        essai.atelier("GET", f"/atelier/clients/{CLIENT}/suivi?jours=7")))
    assert "activite" in s and s["installation"]["pilotage"] == "complet", s
    assert essai.atelier("GET", f"/atelier/clients/{CLIENT}/conversations")[0] == 409

    print("Le client revient à son fichier")
    assert "client.yaml" in essai.pilote("revenir")
    essai.attendre("l'agent sert de nouveau client.yaml", lambda: essai.sante_agent().get("configuration") == {"source": "fichier"})
    essai.attendre("MEGGA le sait", lambda: essai.ordres().get(3) == "retire")
    assert "retire" in essai.pilote("journal")

    print("MEGGA révoque la clé : les relevés sont refusés")
    code, d = essai.atelier("DELETE", f"/atelier/clients/{CLIENT}/installation")
    assert code == 200 and d["revoquee"] is True
    essai.attendre("le pilote est refusé", lambda: "révoquée" in essai.compose("logs", "--tail", "20", "pilote"), 60)
    print("Essai réussi.")


def main() -> int:
    dossier = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="megga-essai-pilote-"))
    dossier.mkdir(parents=True, exist_ok=True)
    essai = Essai(dossier)
    try:
        print("Construction de l'image (socle/Dockerfile) et ajout des clés publiques d'essai")
        subprocess.run(["docker", "build", "-q", "-f", "socle/Dockerfile", "-t", IMAGE_BASE, "."], cwd=RACINE, check=True,
                       stdout=subprocess.DEVNULL)
        preparer(dossier, essai)
        subprocess.run(["docker", "build", "-q", "-t", IMAGE, "."], cwd=dossier / "image", check=True, stdout=subprocess.DEVNULL)
        parcours(essai)
        return 0
    finally:
        essai.compose("down", "-v", "--remove-orphans", verifier=False)
        subprocess.run(["docker", "rmi", "-f", IMAGE, IMAGE_BASE], capture_output=True)
        shutil.rmtree(dossier, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
