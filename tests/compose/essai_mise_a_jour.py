"""L'essai de bout en bout des mises à jour signées avec Docker Compose (lot 6.4).

L'installation du client telle que le guide la décrit (installation/compose : base, agent, pilote, et
mettre_a_jour.sh lancé comme par cron), un atelier d'essai à côté, et un registre local à la place de
ghcr.io. Les images y sont poussées puis signées par le vrai cosign (son image officielle), avec une
clé jetable. Clés, licence et mots de passe sont créés pour l'essai, effacés avec lui, jamais affichés.

  .venv/bin/python tests/compose/essai_mise_a_jour.py [dossier de travail]

Le dossier doit être vu par Docker (avec Colima : sous le dossier personnel, par exemple
~/Library/Caches/megga-essai-maj).

Le parcours : une image non signée est refusée sans être tirée ; une image signée, proposée par MEGGA,
acceptée par le client, est vérifiée, la base sauvegardée, l'agent mis à jour, puis le pilote ; une
image signée mais en panne est installée, /sante échoue, et l'agent revient à l'image d'avant.
"""

from __future__ import annotations

import base64
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

import yaml
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

RACINE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RACINE))
sys.path.insert(0, str(Path(__file__).parent))

from essai_pilote import CLIENT, Essai, brut, pem, port_libre  # noqa: E402

from noyau import licence  # noqa: E402

PROJET = "megga-essai-maj"
IMAGE_BASE = "megga-agents:essai-maj"
COSIGN = "ghcr.io/sigstore/cosign/cosign:v2.4.1"
DELAI = 300


class EssaiMaj(Essai):
    def __init__(self, dossier: Path):
        super().__init__(dossier)
        self.registre = port_libre()
        self.depot = f"localhost:{self.registre}/megga/megga-agents"
        self.mdp_cosign = secrets.token_urlsafe(18)
        self.images: dict[str, str] = {}

    def compose(self, *args: str, env: dict | None = None, verifier: bool = True) -> str:
        r = subprocess.run(["docker", "compose", "-p", PROJET, "-f", "docker-compose.yml", "-f", "essai.yml", *args],
                           cwd=self.dossier, capture_output=True, text=True, env={**os.environ, **(env or {})})
        if verifier and r.returncode != 0:
            raise RuntimeError(f"docker compose {' '.join(args)} : {r.stderr[-800:]}")
        return r.stdout

    def cosign(self, *args: str) -> None:
        subprocess.run(["docker", "run", "--rm", "--network", "host", "--user", f"{os.getuid()}:{os.getgid()}",
                        "-v", f"{self.dossier / 'cosign'}:/cles", "-w", "/cles", "-e", "COSIGN_PASSWORD", COSIGN, *args],
                       check=True, capture_output=True, env={**os.environ, "COSIGN_PASSWORD": self.mdp_cosign})

    def publier(self, nom: str, dockerfile: str, signer: bool) -> str:
        """Construit une image, la pousse au registre local, la signe (ou non) ; rend son empreinte."""
        dossier = self.dossier / f"image-{nom}"
        dossier.mkdir()
        (dossier / "Dockerfile").write_text(dockerfile)
        for f in ("licence.pub", "pilotage.pub", "cosign.pub"):
            if (self.dossier / "cles" / f).exists():
                shutil.copy(self.dossier / "cles" / f, dossier / f)
        etiquette = f"{self.depot}:{nom}"
        subprocess.run(["docker", "build", "-q", "-t", etiquette, "."], cwd=dossier, check=True, stdout=subprocess.DEVNULL)
        sortie = subprocess.run(["docker", "push", etiquette], check=True, capture_output=True, text=True).stdout
        empreinte = re.search(r"digest: (sha256:[0-9a-f]{64})", sortie).group(1)
        if signer:
            self.cosign("sign", "--key", "/cles/cosign.key", "--tlog-upload=false", "--yes", "--allow-insecure-registry",
                        f"{self.depot}@{empreinte}")
        self.images[nom] = empreinte
        return empreinte

    def hote(self) -> str:
        """mettre_a_jour.sh, comme cron le lance chaque minute."""
        r = subprocess.run(["./mettre_a_jour.sh"], cwd=self.dossier, capture_output=True, text=True,
                           env={**os.environ, "COMPOSE_PROJECT_NAME": PROJET, "COMPOSE_FILE": "docker-compose.yml:essai.yml"})
        if r.returncode != 0:
            raise RuntimeError(f"mettre_a_jour.sh : {r.stdout[-400:]} {r.stderr[-400:]}")
        return r.stdout

    def env_image(self) -> str:
        return re.search(r"^MEGGA_IMAGE=(.*)$", (self.dossier / ".env").read_text(), re.M).group(1)

    def image_du_service(self, service: str) -> str:
        ident = self.compose("ps", "-q", service).strip()
        return subprocess.run(["docker", "inspect", "-f", "{{.Config.Image}}", ident], capture_output=True, text=True).stdout.strip()

    def proposer(self, nom: str, version: str) -> int:
        code, d = self.atelier("POST", f"/atelier/clients/{CLIENT}/installation/image",
                               {"version": version, "image": f"ghcr.io/megga/megga-agents@{self.images[nom]}"})
        assert code == 201, d
        return d["ordre"]

    def detail(self, numero: int) -> str:
        _, d = self.atelier("GET", f"/atelier/clients/{CLIENT}/installation")
        return next((o["detail"] for o in d.get("ordres", []) if o["numero"] == numero), "")


def preparer(essai: EssaiMaj) -> None:
    dossier = essai.dossier
    licence_cle, pilotage_cle, installation_cle = (Ed25519PrivateKey.generate() for _ in range(3))
    (dossier / "cles").mkdir()
    (dossier / "cosign").mkdir()
    (dossier / "cles" / "licence.pub").write_bytes(pem(licence_cle))
    (dossier / "cles" / "pilotage.pub").write_bytes(pem(pilotage_cle))
    for f in ("docker-compose.yml", "Caddyfile", "mettre_a_jour.sh"):
        shutil.copy(RACINE / "installation" / "compose" / f, dossier / f)
    conf = yaml.safe_load((RACINE / "clients" / "exemple.yaml").read_text())
    conf.update(id=CLIENT, zone="client")
    (dossier / "client.yaml").write_text(yaml.safe_dump(conf, allow_unicode=True))
    jeton = licence.emettre({"client": CLIENT, "jusqu_au": "2099-12-31"}, licence_cle)
    (dossier / "secrets.env").write_text(
        f"MEGGA_LICENCE={jeton}\nMETA_TOKEN=essai\nMETA_APP_SECRET=essai\nMETA_VERIFY_TOKEN=essai\n"
        "ANTHROPIC_API_KEY=\nDEEPSEEK_API_KEY=\n")
    der = installation_cle.private_bytes(serialization.Encoding.DER, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    (dossier / "pilote.env").write_text(f"PILOTE_CLE={base64.b64encode(der).decode()}\n")
    for f in ("secrets.env", "pilote.env"):
        (dossier / f).chmod(0o600)
    # Le registre local (à la place de ghcr.io), l'atelier d'essai (à la place de la porte), et le pilote
    # qui joint le registre par le réseau de l'installation.
    (dossier / "essai.yml").write_text(yaml.safe_dump({"services": {
        "registre": {"image": "registry:2", "ports": [f"127.0.0.1:{essai.registre}:5000"]},
        "atelier": {"image": "${ESSAI_ATELIER:?}",
                    "environment": {"MEGGA_SERVICE": "atelier", "DATABASE_URL": "sqlite:////tmp/atelier.db",
                                    "ADMIN_TOKEN": "${ESSAI_ADMIN:?}", "PILOTAGE_CLE": "${ESSAI_PILOTAGE_CLE:?}"},
                    "ports": [f"127.0.0.1:{essai.port}:8080"]},
        "pilote": {"environment": {"MEGGA_REGISTRE_URL": "http://registre:5000"}},
    }}))
    os.environ["ESSAI_ADMIN"] = essai.admin
    os.environ["ESSAI_PILOTAGE_CLE"] = brut(pilotage_cle)
    # Provisoires, le temps de lancer le registre (Compose lit tout le fichier) : remplacés par images().
    os.environ["ESSAI_ATELIER"] = "registry:2"
    (dossier / ".env").write_text("MEGGA_IMAGE=registry:2\nDOMAINE=essai.invalid\nPOSTGRES_PASSWORD=provisoire\n")


def images(essai: EssaiMaj) -> None:
    print("Registre local, clé cosign jetable, images poussées et signées")
    essai.compose("up", "-d", "registre")
    essai.attendre("le registre répond", lambda: urllib.request.urlopen(f"http://127.0.0.1:{essai.registre}/v2/", timeout=5).status == 200, 120)
    essai.cosign("generate-key-pair")
    shutil.copy(essai.dossier / "cosign" / "cosign.pub", essai.dossier / "cles" / "cosign.pub")
    cles = (f"FROM {IMAGE_BASE}\n"
            "COPY licence.pub pilotage.pub cosign.pub /app/noyau/\n"
            "COPY licence.pub pilotage.pub cosign.pub /usr/local/lib/python3.12/site-packages/noyau/\n")
    # Une autre version, sans reconstruire : celle que lit importlib.metadata (le dossier de l'image, puis le paquet).
    version = ("USER root\nRUN sed -i 's/^Version: .*/Version: {v}/' /app/megga_agents.egg-info/PKG-INFO "
               "/usr/local/lib/python3.12/site-packages/megga_agents-*.dist-info/METADATA\n"
               "USER agent\n")
    essai.publier("depart", cles, signer=True)
    essai.publier("saine", cles + version.format(v="0.9.0"), signer=True)
    # Signée, mais l'agent ne démarre pas : le contrôle de santé échoue.
    essai.publier("en-panne", cles + version.format(v="0.9.1") + 'CMD ["python", "-c", "raise SystemExit(\'panne voulue\')"]\n', signer=True)
    essai.publier("non-signee", cles + version.format(v="0.9.2"), signer=False)
    (essai.dossier / ".env").write_text(
        f"MEGGA_IMAGE={essai.depot}@{essai.images['depart']}\nDOMAINE=essai.invalid\nPOSTGRES_PASSWORD={secrets.token_urlsafe(18)}\n"
        "PILOTAGE=complet\nPILOTAGE_ACCORD=oui\nPILOTAGE_URL=http://atelier:8080\nPILOTAGE_INTERVALLE=3\n"
        f"PILOTAGE_DELAI=60\nMISES_A_JOUR=oui\nMEGGA_DEPOT={essai.depot}\n")
    os.environ["ESSAI_ATELIER"] = f"{essai.depot}@{essai.images['depart']}"


def parcours(essai: EssaiMaj) -> None:
    depart, saine = f"{essai.depot}@{essai.images['depart']}", f"{essai.depot}@{essai.images['saine']}"
    print("Démarrage : base, agent, pilote, atelier d'essai")
    essai.compose("up", "-d", "base", "agent", "pilote", "atelier")
    essai.attendre("l'atelier répond", lambda: essai.atelier("GET", "/sante")[1].get("pilotage") is True, 180)
    essai.attendre("l'agent répond", lambda: essai.sante_agent().get("ok") is True, 240)
    version_depart = essai.sante_agent()["version"]

    print("Mise en service")
    conf = yaml.safe_load((essai.dossier / "client.yaml").read_text())
    assert essai.atelier("POST", "/atelier/clients", {"config": conf})[0] == 201
    code, d = essai.atelier("PUT", f"/atelier/clients/{CLIENT}/installation", {"cle_publique": essai.pilote("cle").strip()})
    assert code == 200, d
    essai.attendre("MEGGA voit que le pilote installe les images", lambda: essai.atelier(
        "GET", f"/atelier/clients/{CLIENT}/installation")[1]["installation"]["mises_a_jour"] is True, 60)

    print("Une image non signée : refusée, jamais tirée")
    n = essai.proposer("non-signee", "0.9.2")
    essai.attendre(f"ordre {n} en attente d'accord", lambda: essai.ordres().get(n) == "attente_accord")
    assert "accepté" in essai.pilote("accepter", str(n))
    essai.attendre(f"ordre {n} en échec", lambda: essai.ordres().get(n) == "echec")
    assert "image refusée" in essai.detail(n), essai.detail(n)
    assert "MEGGA_IMAGE" not in essai.hote() and essai.env_image() == depart

    print("Une image signée, acceptée : vérifiée, base sauvegardée, agent mis à jour, puis le pilote")
    n = essai.proposer("saine", "0.9.0")
    essai.attendre(f"ordre {n} en attente d'accord", lambda: essai.ordres().get(n) == "attente_accord")
    assert essai.images["saine"] in essai.pilote("ordres")
    essai.hote()
    assert essai.env_image() == depart  # rien sans l'accord du client
    assert "accepté" in essai.pilote("accepter", str(n))
    essai.attendre("signature vérifiée", lambda: "signature de l'image vérifiée" in essai.detail(n), 60)
    assert "installer" in essai.hote()
    assert essai.env_image() == saine and essai.image_du_service("agent") == saine
    assert essai.image_du_service("pilote") == depart  # le pilote attend que l'agent ait fait ses preuves
    if essai.attendre(f"ordre {n} appliqué ou en échec", lambda: essai.ordres().get(n) in ("applique", "echec")) and essai.ordres()[n] != "applique":
        raise AssertionError(f"ordre {n} en échec : {essai.detail(n)}")
    assert essai.sante_agent()["version"] == "0.9.0" != version_depart
    assert "megga-essai-pilote-" in essai.pilote("sauvegardes")
    essai.hote()  # hors mise à jour : le pilote prend l'image de l'agent
    essai.attendre("le pilote sur la nouvelle image", lambda: essai.image_du_service("pilote") == saine, 120)
    essai.attendre("le nouveau pilote relève", lambda: "demarrage" in essai.pilote("journal", "3"), 120)

    print("Une image signée mais en panne : /sante échoue, retour à l'image d'avant")
    n = essai.proposer("en-panne", "0.9.1")
    essai.attendre(f"ordre {n} en attente d'accord", lambda: essai.ordres().get(n) == "attente_accord")
    assert "accepté" in essai.pilote("accepter", str(n))
    essai.attendre("signature vérifiée", lambda: "signature de l'image vérifiée" in essai.detail(n), 60)
    assert "installer" in essai.hote()
    assert essai.image_du_service("agent").endswith(essai.images["en-panne"])
    essai.attendre(f"ordre {n} en échec (délai de 60 s)", lambda: essai.ordres().get(n) == "echec", 240)
    assert "retour à l'image d'avant" in essai.detail(n), essai.detail(n)
    assert "revenir" in essai.hote()
    assert essai.env_image() == saine and essai.image_du_service("agent") == saine
    essai.attendre("l'agent répond de nouveau, sur l'image d'avant", lambda: essai.sante_agent().get("version") == "0.9.0", 180)
    essai.hote()
    assert "retour" in essai.pilote("journal", "5")
    _, vue = essai.atelier("GET", f"/atelier/clients/{CLIENT}/installation")
    assert any(e["evenement"] == "echec" and e["numero"] == n for e in vue["journal"]), json.dumps(vue["journal"])[:400]
    print("Essai réussi.")


def main() -> int:
    dossier = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="megga-essai-maj-")) / "essai"
    if dossier.exists():
        print(f"{dossier} existe déjà : donner un dossier qui n'existe pas encore")
        return 2
    dossier.mkdir(parents=True)
    essai = EssaiMaj(dossier)
    try:
        print("Construction de l'image (socle/Dockerfile)")
        subprocess.run(["docker", "build", "-q", "-f", "socle/Dockerfile", "-t", IMAGE_BASE, "."], cwd=RACINE, check=True,
                       stdout=subprocess.DEVNULL)
        preparer(essai)
        images(essai)
        parcours(essai)
        return 0
    finally:
        essai.compose("down", "-v", "--remove-orphans", verifier=False)
        subprocess.run(["docker", "rmi", "-f", IMAGE_BASE, *(f"{essai.depot}:{n}" for n in essai.images)], capture_output=True)
        subprocess.run(["docker", "image", "prune", "-f", "--filter", f"reference={essai.depot}"], capture_output=True)
        shutil.rmtree(dossier, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
