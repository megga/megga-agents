"""Lot 6.4 : les mises à jour signées de l'image, exécutées par le pilote.

Sans réseau ni Docker : un faux registre (httpx) qui sert de vraies signatures au format de cosign,
un faux Kubernetes, et l'agent réduit à son /sante. L'essai avec Docker Compose, de vraies images
et cosign est dans tests/compose/essai_mise_a_jour.py.
"""

import base64
import gzip
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

import httpx
import pytest
import yaml
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from noyau import pilotage, stockage
from pilote import image as images
from pilote.__main__ import main as commande
from pilote.service import Installation, MisesAJour, Pilote
from test_lot5 import MEGGA
from test_lot6_pilote import BASE, BASES, CONF_CLIENT, CLE_INSTALLATION_TEXTE, PUB, canal  # noqa: F401 (fixture)

COSIGN = ec.generate_private_key(ec.SECP256R1())
AUTRE_COSIGN = ec.generate_private_key(ec.SECP256R1())
COSIGN_PUB = COSIGN.public_key()
DEPOT = "ghcr.io/megga/megga-agents"


def empreinte(n: int) -> str:
    return "sha256:" + hashlib.sha256(str(n).encode()).hexdigest()


def image(n: int) -> str:
    return f"{DEPOT}@{empreinte(n)}"


def charge_utile(digest: str) -> bytes:
    """Ce que signe cosign (simple signing), au même format."""
    return json.dumps({"critical": {"identity": {"docker-reference": DEPOT}, "image": {"docker-manifest-digest": digest},
                                    "type": "cosign container image signature"}, "optional": None}).encode()


class FauxRegistre:
    """Un registre qui demande un jeton (comme ghcr.io) et sert les signatures déposées."""

    def __init__(self):
        self.signatures: dict[str, list[tuple[bytes, bytes]]] = {}  # empreinte -> [(charge, signature)]
        self.en_panne = False
        self.auth: list[str | None] = []

    def signer(self, digest: str, cle=COSIGN, pour: str | None = None) -> None:
        charge = charge_utile(pour or digest)
        self.signatures.setdefault(digest, []).append((charge, base64.b64encode(cle.sign(charge, ec.ECDSA(hashes.SHA256())))))

    def __call__(self, requete: httpx.Request) -> httpx.Response:
        if self.en_panne:
            return httpx.Response(503)
        if requete.url.path == "/token":
            self.auth.append(requete.headers.get("authorization"))
            return httpx.Response(200, json={"token": "jeton-de-lecture"})
        if requete.headers.get("authorization") != "Bearer jeton-de-lecture":
            return httpx.Response(401, headers={"www-authenticate": 'Bearer realm="https://ghcr.io/token",service="ghcr.io"'})
        chemin = requete.url.path.removeprefix("/v2/megga/megga-agents/")
        if chemin.startswith("manifests/sha256-") and chemin.endswith(".sig"):
            digest = chemin.removeprefix("manifests/").removesuffix(".sig").replace("-", ":", 1)
            sigs = self.signatures.get(digest)
            if not sigs:
                return httpx.Response(404)
            return httpx.Response(200, json={"schemaVersion": 2, "layers": [
                {"mediaType": images.TYPE_SIGNATURE, "digest": "sha256:" + hashlib.sha256(c).hexdigest(),
                 "annotations": {images.ANNOTATION: s.decode()}} for c, s in sigs]})
        if chemin.startswith("blobs/sha256:"):
            for sigs in self.signatures.values():
                for c, _ in sigs:
                    if "sha256:" + hashlib.sha256(c).hexdigest() == chemin.removeprefix("blobs/"):
                        return httpx.Response(200, content=c)
        return httpx.Response(404)


# La signature de l'image


def test_la_signature_de_l_image_est_verifiee_comme_cosign():
    r = FauxRegistre()
    r.signer(empreinte(1))
    t = httpx.MockTransport(r)
    assert images.verifier_signature(image(1), DEPOT, COSIGN_PUB, transport=t, jeton="lecture") == image(1)
    assert r.auth[-1].startswith("Basic ")  # le jeton de lecture du client, seulement pour le jeton du registre
    assert images.verifier_signature(image(1), "registre.client.ch/miroir/megga", COSIGN_PUB, transport=httpx.MockTransport(
        lambda q: r(httpx.Request(q.method, str(q.url).replace("registre.client.ch/v2/miroir/megga", "ghcr.io/v2/megga/megga-agents"),
                                  headers=q.headers)))) == f"registre.client.ch/miroir/megga@{empreinte(1)}"  # un miroir
    r.signer(empreinte(2), AUTRE_COSIGN)  # pas la clé de MEGGA
    r.signer(empreinte(3), pour=empreinte(4))  # la signature d'une autre image
    for n, motif in ((2, "sans signature valable"), (3, "sans signature valable"), (5, "sans signature de MEGGA")):
        with pytest.raises(images.ImageRefusee, match=motif):
            images.verifier_signature(image(n), DEPOT, COSIGN_PUB, transport=t)
    with pytest.raises(images.ImageRefusee, match="empreinte"):
        images.verifier_signature("ghcr.io/megga/megga-agents:0.2.0", DEPOT, COSIGN_PUB, transport=t)
    r.en_panne = True
    with pytest.raises(images.RegistreInjoignable):  # à réessayer, pas un refus
        images.verifier_signature(image(1), DEPOT, COSIGN_PUB, transport=t)


def test_une_signature_alteree_est_refusee():
    r = FauxRegistre()
    r.signer(empreinte(1))

    def altere(q: httpx.Request) -> httpx.Response:
        rep = r(q)
        return httpx.Response(200, content=rep.content + b" ") if "/blobs/" in q.url.path and rep.status_code == 200 else rep

    with pytest.raises(images.ImageRefusee, match="altéré"):
        images.verifier_signature(image(1), DEPOT, COSIGN_PUB, transport=httpx.MockTransport(altere))


def test_le_registre_et_la_cle_se_reglent():
    assert images.adresse_registre(DEPOT) == ("https://ghcr.io", "megga/megga-agents")
    assert images.adresse_registre("localhost:5000/megga/megga-agents", "http://registre:5000") == ("http://registre:5000", "megga/megga-agents")
    with pytest.raises(RuntimeError):
        images.adresse_registre(DEPOT, "http://registre.exemple.com")  # en clair, seulement un nom local
    for mauvais in ("ghcr.io", "GHCR.io/x y", "ghcr.io/megga;rm"):
        with pytest.raises(RuntimeError):
            images.depot(mauvais)
    assert images.depot(None) == DEPOT
    with pytest.raises(images.ImageRefusee, match="ECDSA"):
        images.cle_image(PUB.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    if not images.CLE_IMAGE.exists():  # le dépôt n'a pas encore la clé : aucune mise à jour possible
        with pytest.raises(images.ImageRefusee, match="absente"):
            images.cle_image()


# La sauvegarde


@pytest.fixture(params=BASES)
def url(request, tmp_path):
    if request.param == "sqlite":
        u = f"sqlite:///{tmp_path}/client.db"
    else:
        u = os.environ["TEST_POSTGRES_URL"]
    stockage.migrer(u)
    return u


def test_la_base_est_sauvegardee_et_se_recharge(url, tmp_path):
    stockage.JournalPilotage(url).noter("exemple", "essai", 1, "avant la mise à jour")
    dossier = tmp_path / "sauvegardes"
    dossier.mkdir()
    fichiers = [images.sauvegarder(url, dossier, "exemple", "0.2.0", 1000.0 + i) for i in range(5)]
    assert [f.name for f in images.sauvegardes(dossier, "exemple")] == [f.name for f in reversed(fichiers[-3:])]  # les 3 dernières
    assert list(dossier.glob(".*")) == []  # aucune sauvegarde à moitié écrite
    assert fichiers[-1].name == "megga-exemple-19700101-001644-avant-0.2.0.jsonl.gz"
    with gzip.open(fichiers[-1], "rt") as f:
        assert json.loads(f.readline()) == {"format": stockage.FORMAT}
    cible = f"sqlite:///{tmp_path}/restauree.db"
    assert stockage.importer(fichiers[-1], cible) > 0
    assert any(e["evenement"] == "essai" for e in stockage.JournalPilotage(cible).lire("exemple"))
    assert all(f.stat().st_mode & 0o777 == 0o600 for f in images.sauvegardes(dossier, "exemple"))  # le pilote seul
    with pytest.raises(RuntimeError, match="absent"):
        images.sauvegarder(url, tmp_path / "nulle-part", "exemple", "0.2.0")


def test_la_mise_a_jour_en_cours_ne_change_que_si_personne_ne_l_a_changee(url):
    r = stockage.Reglages(url)
    assert r.changer("maj", None, {"phase": "verifier"})
    assert not r.changer("maj", None, {"phase": "autre"})  # déjà posée
    assert r.changer("maj", {"phase": "verifier"}, {"phase": "prete"})
    assert not r.changer("maj", {"phase": "verifier"}, {"phase": "lancee"})  # l'autre processus l'a avancée
    assert r.changer("maj", {"phase": "prete"}, None) and r.lire("maj") is None
    assert r.changer("maj", None, {"phase": "verifier"})  # après un None écrit


# Le parcours, par le script de l'hôte (Compose)


class Sante:
    """Le /sante de l'agent : la version qu'il sert, et s'il va bien."""

    def __init__(self, version="0.1.0", ok=True):
        self.version, self.ok = version, ok

    def __call__(self, q: httpx.Request) -> httpx.Response:
        if self.ok is None:
            raise httpx.ConnectError("injoignable")
        return httpx.Response(200 if self.ok else 503, json={"ok": self.ok, "version": self.version})


def preparer(c, tmp_path, accord="oui", **env):
    """Un pilote qui installe les images (MISES_A_JOUR=oui), son registre, le /sante de l'agent."""
    (tmp_path / "sauvegardes").mkdir(parents=True, exist_ok=True)
    c.registre, c.sante = FauxRegistre(), Sante()
    c.env = {"PILOTAGE": "complet", "PILOTAGE_ACCORD": accord, "MISES_A_JOUR": "oui", "CLIENT_CONFIG": CONF_CLIENT,
             "DATABASE_URL": c.url, "PILOTE_CLE": CLE_INSTALLATION_TEXTE, "PILOTE_SAUVEGARDES": str(tmp_path / "sauvegardes"), **env}
    p = Pilote(c.env, transport=httpx.ASGITransport(app=c.atelier), transport_agent=httpx.MockTransport(c.sante),
               cle_megga=PUB, horloge=c.horloge, **({"transport_kube": env.pop("_kube")} if "_kube" in env else {}))
    p.maj.cle, p.maj.transport = COSIGN_PUB, httpx.MockTransport(c.registre)
    return p


def proposer(c, n: int, version: str) -> int:
    r = c.t.post("/atelier/clients/exemple/installation/image", headers=MEGGA, json={"version": version, "image": image(n)})
    assert r.status_code == 201, r.text
    return r.json()["ordre"]


def etat(p, numero: int) -> str:
    """L'état d'un ordre chez l'installation (MEGGA le reçoit au relevé suivant)."""
    return p.installation.ordres.lire("exemple", numero)["etat"]


def hote(c, p, actuelle: str) -> str:
    """Ce que le script de l'hôte reçoit du pilote (python -m pilote image --actuelle …)."""
    return p.installation.image_cible(actuelle, c.horloge())


def test_une_image_acceptee_est_verifiee_sauvegardee_puis_installee(canal, tmp_path):
    c = canal
    p = preparer(c, tmp_path)
    c.registre.signer(empreinte(2))
    numero = proposer(c, 2, "0.2.0")
    c.tour(p)
    assert etat(p, numero) == "attente_accord"
    sortie = []
    env = {**c.env, "PILOTE_SAUVEGARDES": c.env["PILOTE_SAUVEGARDES"]}
    assert commande(["ordres"], env, sortie.append, cle_megga=PUB) == 0
    assert any(image(2) in l for l in sortie) and any("retour à l'image d'avant" in l for l in sortie)
    assert hote(c, p, image(1)) == "rien"  # rien avant l'accord du client
    assert commande(["accepter", str(numero)], env, sortie.append, cle_megga=PUB) == 0 and "signature" in sortie[-1]
    c.tour(p)  # la signature est vérifiée
    assert p.installation._maj()["phase"] == "prete"
    assert list((tmp_path / "sauvegardes").iterdir()) == []  # la sauvegarde attend le dernier moment
    assert hote(c, p, image(1)) == f"installer {image(2)}"
    assert len(list((tmp_path / "sauvegardes").iterdir())) == 1
    assert hote(c, p, image(1)) == f"installer {image(2)}"  # le script n'a pas pu : il réessaie
    assert hote(c, p, image(2)) == "attendre"  # en place : le pilote surveille /sante
    c.tour(p)
    assert etat(p, numero) == "a_appliquer"  # l'agent répond encore sur l'ancienne version
    c.sante.version = "0.2.0"
    c.tour(p)
    assert etat(p, numero) == "a_appliquer"  # un relevé sain ne suffit pas
    c.sante.ok = False
    c.tour(p)  # elle répond puis tombe : la série repart de zéro
    c.sante.ok = True
    c.tour(p)
    assert etat(p, numero) == "a_appliquer"
    c.tour(p)
    assert etat(p, numero) == "applique"
    c.tour(p)
    assert c.ordres()[numero] == "applique"  # chez MEGGA aussi
    assert hote(c, p, image(2)) == "rien"  # le pilote suit l'image de l'agent
    journal = [e["evenement"] for e in p.installation.journal.lire("exemple")]
    assert {"accepte", "verifie", "lance", "applique"} <= set(journal)
    vue = c.t.get("/atelier/clients/exemple/installation", headers=MEGGA).json()
    assert vue["installation"]["mises_a_jour"] is True
    chez_megga = [e["detail"] for e in vue["journal"] if e["numero"] == numero]
    assert any("signature de l'image vérifiée" in d for d in chez_megga) and any("0.2.0" in d for d in chez_megga)


def test_retour_a_l_image_d_avant_si_sante_echoue(canal, tmp_path):
    c = canal
    p = preparer(c, tmp_path, accord="non", PILOTAGE_DELAI="60")
    c.registre.signer(empreinte(3))
    numero = proposer(c, 3, "0.3.0")
    c.tour(p)
    c.tour(p)
    assert hote(c, p, image(1)) == f"installer {image(3)}"
    assert hote(c, p, image(3)) == "attendre"
    c.sante.ok = None  # l'agent ne démarre pas sur la nouvelle image
    c.tour(p)
    assert etat(p, numero) == "a_appliquer"
    c.horloge.t += 61
    c.tour(p)
    assert etat(p, numero) == "echec"
    l = p.installation.ordres.lire("exemple", numero)
    assert "après 1 minutes" in l["detail"] and "retour à l'image d'avant" in l["detail"]
    assert hote(c, p, image(3)) == f"revenir {image(1)}"
    assert hote(c, p, image(1)) == "rien"
    assert p.installation.journal.lire("exemple")[0]["evenement"] == "retour"
    c.tour(p)
    assert etat(p, numero) == "echec"


def test_une_image_non_signee_n_est_jamais_tiree(canal, tmp_path):
    c = canal
    p = preparer(c, tmp_path, accord="non")
    c.registre.signer(empreinte(4), AUTRE_COSIGN)
    numero = proposer(c, 4, "0.4.0")
    c.tour(p)
    c.tour(p)
    assert etat(p, numero) == "echec"
    assert "image refusée" in p.installation.ordres.lire("exemple", numero)["detail"]
    assert hote(c, p, image(1)) == "rien" and list((tmp_path / "sauvegardes").iterdir()) == []
    # le registre en panne : on réessaie, sans échec, jusqu'à l'échéance de l'ordre
    c.registre.en_panne = True
    c.registre.signer(empreinte(5))
    numero = proposer(c, 5, "0.5.0")
    c.tour(p)
    c.tour(p)
    assert etat(p, numero) == "a_appliquer" and p.installation._maj()["phase"] == "verifier"
    c.registre.en_panne = False
    c.tour(p)
    assert p.installation._maj()["phase"] == "prete"


def test_sans_empreinte_pas_de_retour_possible_donc_pas_de_mise_a_jour(canal, tmp_path):
    c = canal
    p = preparer(c, tmp_path, accord="non")
    c.registre.signer(empreinte(6))
    numero = proposer(c, 6, "0.6.0")
    c.tour(p)
    c.tour(p)
    assert hote(c, p, "ghcr.io/megga/megga-agents:0.1.0") == "rien"  # l'image d'avant par étiquette : rien ne part
    assert etat(p, numero) == "echec" and "empreinte" in p.installation.ordres.lire("exemple", numero)["detail"]
    assert list((tmp_path / "sauvegardes").iterdir()) == []


def test_sans_sauvegarde_pas_de_mise_a_jour(canal, tmp_path):
    c = canal
    p = preparer(c, tmp_path, accord="non")
    p.installation.maj.sauvegardes = str(tmp_path / "absent")
    c.registre.signer(empreinte(6))
    numero = proposer(c, 6, "0.6.0")
    c.tour(p)
    c.tour(p)
    assert hote(c, p, image(1)) == "rien"
    assert "sauvegarde de la base impossible" in p.installation.ordres.lire("exemple", numero)["detail"]


def test_une_image_plus_recente_remplace_celle_qui_attend(canal, tmp_path):
    c = canal
    p = preparer(c, tmp_path)
    c.registre.signer(empreinte(7))
    c.registre.signer(empreinte(8))
    premier = proposer(c, 7, "0.7.0")
    c.tour(p)
    second = proposer(c, 8, "0.8.0")
    c.tour(p)
    assert etat(p, premier) == "remplace" and etat(p, second) == "attente_accord"


def test_sans_mises_a_jour_l_image_est_proposee_et_reconnue_une_fois_installee(canal, tmp_path):
    c = canal
    p = preparer(c, tmp_path, MISES_A_JOUR="non")
    numero = proposer(c, 9, "0.9.0")
    c.tour(p)
    assert etat(p, numero) == "propose"
    assert hote(c, p, image(1)) == "rien"
    c.sante.version = "0.9.0"  # le client l'a installée à la main
    c.tour(p)
    assert etat(p, numero) == "applique"
    assert "installée par le client" in p.installation.ordres.lire("exemple", numero)["detail"]


# Sous Kubernetes : le pilote change l'image de deux Deployments nommés, rien d'autre


class FauxKubernetes:
    def __init__(self, image_depart: str):
        self.images = {"agent": image_depart, "agent-pilote": image_depart}
        self.changements: list[tuple[str, str]] = []

    def __call__(self, q: httpx.Request) -> httpx.Response:
        assert q.headers["authorization"].startswith("Bearer ")
        nom = q.url.path.rsplit("/", 1)[-1]
        assert q.url.path.startswith("/apis/apps/v1/namespaces/clients/deployments/") and nom in self.images
        conteneur = "pilote" if nom.endswith("pilote") else "agent"
        if q.method == "PATCH":
            assert q.headers["content-type"] == "application/strategic-merge-patch+json"
            corps = json.loads(q.content)
            (c,) = corps["spec"]["template"]["spec"]["containers"]
            assert set(corps) == {"spec"} and set(c) == {"name", "image"} and c["name"] == conteneur  # l'image, et rien d'autre
            self.images[nom] = c["image"]
            self.changements.append((nom, c["image"]))
        return httpx.Response(200, json={"spec": {"template": {"spec": {"containers": [{"name": conteneur, "image": self.images[nom]}]}}}})


def test_sous_kubernetes_le_pilote_change_l_image_puis_revient(canal, tmp_path):
    c = canal
    kube = FauxKubernetes(image(1))
    p = preparer(c, tmp_path, accord="non", PILOTAGE_DELAI="60", AGENT_DEPLOIEMENT="agent", PILOTE_DEPLOIEMENT="agent-pilote",
                 KUBERNETES_SERVICE_HOST="10.0.0.1", POD_NAMESPACE="clients", _kube=httpx.MockTransport(kube))
    c.registre.signer(empreinte(2))
    c.registre.signer(empreinte(3))
    numero = proposer(c, 2, "0.2.0")
    c.tour(p)  # reçue
    c.tour(p)  # vérifiée
    c.tour(p)  # sauvegardée, image changée
    assert kube.changements == [("agent", image(2))]
    assert hote(c, p, image(1)) == "rien"  # sous Kubernetes, aucun script
    c.sante.version = "0.2.0"
    c.tour(p)
    c.tour(p)
    assert etat(p, numero) == "applique"
    c.tour(p)  # puis le pilote prend l'image de l'agent
    assert kube.changements[-1] == ("agent-pilote", image(2))
    # une image qui ne démarre pas : retour à la précédente
    numero = proposer(c, 3, "0.3.0")
    for _ in range(3):
        c.tour(p)
    assert kube.images["agent"] == image(3)
    c.sante.ok = False
    c.horloge.t += 61
    c.tour(p)
    assert etat(p, numero) == "echec"
    c.tour(p)
    assert kube.images == {"agent": image(2), "agent-pilote": image(2)}
    assert len(list((tmp_path / "sauvegardes").iterdir())) == 2


def test_les_mises_a_jour_se_reglent():
    base = {"PILOTAGE": "complet", "CLIENT_CONFIG": CONF_CLIENT, "DATABASE_URL": "sqlite://", "PILOTE_CLE": CLE_INSTALLATION_TEXTE,
            "PILOTAGE_URL": "https://megga.exemple"}
    assert Pilote(base).maj.actif is False
    # sans mises à jour, un dépôt inutile n'empêche pas le pilote de démarrer (un pilote 6.3 sous Helm, par exemple)
    assert Pilote({**base, "MEGGA_DEPOT": "megga-agents"}).maj.actif is False
    for mauvais in ({"MISES_A_JOUR": "peut-etre"}, {"PILOTAGE_DELAI": "5"}, {"MISES_A_JOUR": "oui", "MEGGA_DEPOT": "rien"},
                    {"MISES_A_JOUR": "oui", "MEGGA_REGISTRE_URL": "http://registre.exemple.com"},
                    {"MISES_A_JOUR": "oui", "AGENT_DEPLOIEMENT": "agent", "PILOTE_DEPLOIEMENT": "../x"}):
        with pytest.raises(RuntimeError):
            Pilote({**base, **mauvais})
    assert MisesAJour.depuis({"MISES_A_JOUR": "oui"}).kube is None  # Compose : le script de l'hôte


# Compose et Helm


def test_compose_les_mises_a_jour_sans_acces_a_docker():
    c = yaml.safe_load(open("installation/compose/docker-compose.yml"))
    p = c["services"]["pilote"]
    assert not any("docker.sock" in str(v) for v in p["volumes"])  # aucun accès à Docker
    assert "sauvegardes:/sauvegardes" in p["volumes"] and "sauvegardes" in c["volumes"]
    assert p["environment"]["MISES_A_JOUR"] == "${MISES_A_JOUR:-non}"
    assert os.access("installation/compose/mettre_a_jour.sh", os.X_OK)


def faux_docker(tmp_path, reponses: list[str], conteneur: str = "", locales: tuple[str, ...] = ()) -> dict:
    """Un faux docker : rend les réponses du pilote dans l'ordre et note chaque commande. `conteneur` : l'image du
    conteneur de l'agent (aucun sinon), remplacée par celle de .env à « compose up agent » ; `locales` : les images
    déjà sur le serveur."""
    (tmp_path / "bin").mkdir()
    (tmp_path / "reponses").write_text("\n".join(reponses) + "\n")
    (tmp_path / "conteneur").write_text(conteneur)
    (tmp_path / "locales").write_text("\n".join(locales) + "\n")
    script = tmp_path / "bin" / "docker"
    script.write_text(f"""#!/usr/bin/env bash
echo "$*" >> {tmp_path}/commandes
case "$1 $2" in
  "compose exec") head -n 1 {tmp_path}/reponses; sed -i.bak 1d {tmp_path}/reponses ;;
  "compose ps") [ -s {tmp_path}/conteneur ] && echo c0ffee ;;
  "compose up") case "$*" in *agent*) sed -n 's/^MEGGA_IMAGE=//p' .env > {tmp_path}/conteneur ;; esac ;;
  "image inspect") grep -qxF "$3" {tmp_path}/locales || exit 1 ;;
  inspect*) cat {tmp_path}/conteneur ;;
esac
exit 0
""")
    script.chmod(0o755)
    return {**os.environ, "PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}"}


def lancer_script(tmp_path, reponses: list[str], conteneur: str = "", env_image: str | None = None,
                  avant=None, locales: tuple[str, ...] = (), depot: str | None = None) -> tuple[subprocess.CompletedProcess, str, str]:
    dossier = tmp_path / "installation"
    dossier.mkdir()
    if avant:
        avant(dossier)
    (dossier / "mettre_a_jour.sh").write_bytes(Path("installation/compose/mettre_a_jour.sh").read_bytes())
    (dossier / "mettre_a_jour.sh").chmod(0o755)
    (dossier / ".env").write_text(f"DOMAINE=agent.exemple.ch\nMEGGA_IMAGE={env_image or image(1)}\nPILOTAGE=complet\n"
                                  + (f"MEGGA_DEPOT={depot}\n" if depot else ""))
    r = subprocess.run([str(dossier / "mettre_a_jour.sh")], env=faux_docker(tmp_path, reponses, conteneur, locales),
                       capture_output=True, text=True, cwd=dossier)
    commandes = (tmp_path / "commandes").read_text() if (tmp_path / "commandes").exists() else ""
    return r, (dossier / ".env").read_text(), commandes


def test_le_script_de_l_hote_installe_l_image_que_le_pilote_rend(tmp_path):
    r, env, commandes = lancer_script(tmp_path, [f"installer {image(2)}", "attendre"])
    assert r.returncode == 0, r.stderr
    assert f"MEGGA_IMAGE={image(2)}" in env and "DOMAINE=agent.exemple.ch" in env and image(1) not in env
    assert f"compose exec -T pilote python -m pilote image --actuelle {image(1)}" in commandes
    assert f"pull -q {image(2)}" in commandes and "compose up -d --no-deps agent" in commandes
    assert f"--actuelle {image(2)}" in commandes  # le pilote sait aussitôt que l'image est en place


@pytest.mark.parametrize("reponse", ["installer ghcr.io/megga/megga-agents:latest", "installer x; rm -rf /",
                                     f"installer {image(2)} --privileged", "lancer tout",
                                     "revenir evil.example/x/y@" + empreinte(9)])  # un autre dépôt
def test_le_script_de_l_hote_refuse_tout_le_reste(tmp_path, reponse):
    r, env, commandes = lancer_script(tmp_path, [reponse])
    assert r.returncode == 1
    assert f"MEGGA_IMAGE={image(1)}" in env and "pull" not in commandes and "up -d" not in commandes


def test_le_script_reprend_l_image_d_avant_sans_le_registre_et_suit_un_miroir(tmp_path):
    r, env, commandes = lancer_script(tmp_path, [f"revenir {image(1)}", "rien"], conteneur=image(2), env_image=image(2),
                                      locales=(image(1),))
    assert r.returncode == 0, r.stderr
    assert "pull" not in commandes and f"MEGGA_IMAGE={image(1)}" in env  # déjà sur le serveur : registre inutile
    miroir = f"registre.client.ch/megga@{empreinte(2)}"
    autre = tmp_path / "miroir"
    autre.mkdir()
    r, env, _ = lancer_script(autre, [f"installer {miroir}", "attendre"], depot="registre.client.ch/megga")
    assert r.returncode == 0 and f"MEGGA_IMAGE={miroir}" in env


def test_le_script_donne_l_image_qui_tourne_vraiment(tmp_path):
    # .env réécrit, mais « docker compose up » n'est pas passé : l'agent tourne encore sur l'image d'avant.
    r, _, commandes = lancer_script(tmp_path, ["attendre"], conteneur=image(1), env_image=image(2))
    assert r.returncode == 0 and f"--actuelle {image(1)}" in commandes


def test_un_verrou_orphelin_ne_bloque_pas_les_mises_a_jour(tmp_path):
    def verrou(dossier, age):
        (dossier / ".mise-a-jour.verrou").mkdir()
        os.utime(dossier / ".mise-a-jour.verrou", (time.time() - age, time.time() - age))

    r, _, commandes = lancer_script(tmp_path, ["rien"], avant=lambda d: verrou(d, 3600))
    assert r.returncode == 0 and "--actuelle" in commandes  # interrompu il y a une heure : repris
    autre = tmp_path / "autre"
    autre.mkdir()
    r, _, commandes = lancer_script(autre, ["rien"], avant=lambda d: verrou(d, 10))
    assert r.returncode == 0 and commandes == ""  # une exécution en cours : on la laisse


def test_le_script_de_l_hote_hors_mise_a_jour(tmp_path):
    r, env, commandes = lancer_script(tmp_path, ["rien"])
    assert r.returncode == 0 and "compose up -d --no-deps pilote" in commandes and f"MEGGA_IMAGE={image(1)}" in env


def test_helm_le_pilote_ne_peut_changer_que_deux_deployments():
    gabarit = open("installation/helm/megga-agent/templates/mises-a-jour.yaml").read()
    assert 'verbs: ["get", "patch"]' in gabarit and "resourceNames" in gabarit
    assert "secrets" not in gabarit.split("rules:")[1].split("---")[0] and "ClusterRole" not in gabarit
    # un « helm upgrade » garde l'image posée par le pilote tant que les valeurs n'ont pas changé
    aides = open("installation/helm/megga-agent/templates/_helpers.tpl").read()
    assert 'lookup "apps/v1" "Deployment"' in aides and "megga.ai/image-valeurs" in aides
    for f in ("deployment.yaml", "pilote.yaml"):
        assert "megga-agent.image-en-place" in open(f"installation/helm/megga-agent/templates/{f}").read()


def test_un_releve_dit_si_le_pilote_installe_les_images(canal, tmp_path):
    c = canal
    p = preparer(c, tmp_path)
    c.tour(p)
    assert c.t.get("/atelier/installations", headers=MEGGA).json()["installations"][0]["mises_a_jour"] is True


# Seconde relecture


def lancee(c, tmp_path, n=2, version="0.2.0", **env):
    """Une mise à jour lancée sous Compose : vérifiée, base sauvegardée, image donnée au script."""
    p = preparer(c, tmp_path, accord="non", PILOTAGE_DELAI="60", **env)
    c.registre.signer(empreinte(n))
    numero = proposer(c, n, version)
    c.tour(p)
    c.tour(p)
    assert hote(c, p, image(1)) == f"installer {image(n)}"
    return p, numero


def test_une_mise_a_jour_retouchee_dans_la_base_ne_fait_rien_tirer(canal, tmp_path):
    c = canal
    p, numero = lancee(c, tmp_path)
    inst = p.installation
    r = inst._maj()
    pirate = "evil.example/x/y@" + empreinte(99)
    assert inst.reglages.changer("mise_a_jour", r, {**r, "reference": pirate})
    assert hote(c, p, image(1)) == "rien"  # jamais « installer evil… »
    assert etat(p, numero) == "echec" and inst._maj() is None
    assert any(a["genre"] == "mise_a_jour_bloquee" for a in stockage.Journal(c.url).alertes(0))
    # l'image d'avant retouchée, en phase de retour : pareil
    p, numero = lancee(c, tmp_path / "b", n=3, version="0.3.0")
    inst = p.installation
    r = inst._maj()
    assert inst.reglages.changer("mise_a_jour", r, {**r, "phase": "retour", "avant": pirate})
    assert hote(c, p, image(3)) == "rien" and etat(p, numero) == "echec"


def test_un_retour_impossible_ne_bloque_pas_pour_toujours(canal, tmp_path):
    c = canal
    p, numero = lancee(c, tmp_path)
    assert hote(c, p, image(2)) == "attendre"
    c.sante.ok = None
    c.horloge.t += 61
    c.tour(p)
    assert hote(c, p, image(2)) == f"revenir {image(1)}"  # le script n'y arrive pas (registre en panne…)
    c.horloge.t += 61
    c.tour(p)
    assert p.installation._maj() is None and hote(c, p, image(2)) == "rien"
    assert any(a["genre"] == "mise_a_jour_bloquee" for a in stockage.Journal(c.url).alertes(0))
    assert image(1) in p.installation.journal.lire("exemple")[0]["detail"]  # l'image à remettre à la main
    # la mise à jour suivante peut partir
    c.registre.signer(empreinte(4))
    suivant = proposer(c, 4, "0.4.0")
    c.tour(p)
    c.tour(p)
    assert hote(c, p, image(2)) == f"installer {image(4)}" and etat(p, suivant) == "a_appliquer"


def test_recharger_la_sauvegarde_ne_relance_pas_la_mise_a_jour(canal, tmp_path):
    c = canal
    p, numero = lancee(c, tmp_path)
    (fichier,) = images.sauvegardes(tmp_path / "sauvegardes", "exemple")
    cible = f"sqlite:///{tmp_path}/rechargee.db"
    stockage.importer(fichier, cible)
    assert stockage.Reglages(cible).lire("mise_a_jour") is None
    assert stockage.Ordres(cible).lire("exemple", numero)["etat"] == "echec"
    assert p.installation._maj()["phase"] == "lancee"  # la base en service, elle, n'est pas touchée


def test_le_delai_part_quand_l_image_est_en_place(canal, tmp_path):
    c = canal
    p, numero = lancee(c, tmp_path)
    c.horloge.t += 50  # un long pull
    assert hote(c, p, image(2)) == "attendre"
    c.horloge.t += 50
    c.tour(p)
    assert etat(p, numero) == "a_appliquer"  # 100 s depuis le lancement, 50 depuis la mise en place
    c.horloge.t += 11
    c.tour(p)
    assert etat(p, numero) == "echec"


def test_mises_a_jour_desactivees_en_route(canal, tmp_path):
    c = canal
    p = preparer(c, tmp_path, accord="non")
    c.registre.signer(empreinte(2))
    numero = proposer(c, 2, "0.2.0")
    c.tour(p)
    c.tour(p)
    assert p.installation._maj()["phase"] == "prete"
    p.installation.maj.actif = False  # le client passe MISES_A_JOUR à non
    assert hote(c, p, image(1)) == "rien"
    c.tour(p)
    assert etat(p, numero) == "echec" and p.installation._maj() is None
    # une mise à jour déjà lancée, elle, va au bout
    q, suivant = lancee(c, tmp_path / "b", n=3, version="0.3.0")
    assert hote(c, q, image(3)) == "attendre"
    q.installation.maj.actif = False
    c.sante.version = "0.3.0"
    c.tour(q)
    c.tour(q)
    assert etat(q, suivant) == "applique"


def test_sous_kubernetes_un_helm_upgrade_en_route_n_est_pas_ecrase(canal, tmp_path):
    c = canal
    kube = FauxKubernetes(image(1))
    p = preparer(c, tmp_path, accord="non", PILOTAGE_DELAI="60", AGENT_DEPLOIEMENT="agent", PILOTE_DEPLOIEMENT="agent-pilote",
                 KUBERNETES_SERVICE_HOST="10.0.0.1", POD_NAMESPACE="clients", _kube=httpx.MockTransport(kube))
    c.registre.signer(empreinte(2))
    numero = proposer(c, 2, "0.2.0")
    for _ in range(3):
        c.tour(p)
    assert kube.images["agent"] == image(2)
    kube.images["agent"] = image(5)  # le client fait un « helm upgrade » vers une autre empreinte
    c.sante.ok = False
    c.horloge.t += 61
    c.tour(p)
    c.tour(p)
    assert kube.images["agent"] == image(5) and etat(p, numero) == "echec"
    assert "hors du pilote" in p.installation.journal.lire("exemple")[0]["detail"]


def test_une_reponse_illisible_du_registre_se_reessaie_avec_sa_cause():
    def proxy(q: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>portail du proxy</html>")

    with pytest.raises(images.RegistreInjoignable, match="illisible"):
        images.verifier_signature(image(1), DEPOT, COSIGN_PUB, transport=httpx.MockTransport(proxy))


# La relecture du 16.11.2026 (I17 à I20) : chaque faille prouvée alors, fermée maintenant.

def test_une_ligne_ecrite_par_l_agent_ne_fait_rien_installer(canal, tmp_path):
    """I17 : la mise à jour en cours est scellée par la clé du pilote ; l'agent, qui partage la base, ne peut pas en
    écrire une : ni une image d'avant libre, ni une image non signée par MEGGA, ni une image que le client n'a pas acceptée."""
    c = canal
    p, numero = lancee(c, tmp_path)
    inst = p.installation
    r = inst._maj()
    assert inst.reglages.changer("mise_a_jour", r, {**r, "phase": "retour", "avant": image(77)})  # sans le sceau
    assert hote(c, p, image(2)) == "rien" and inst._maj() is None and etat(p, numero) == "echec"
    assert stockage.Journal(c.url).alertes(0)[0]["genre"] == "mise_a_jour_bloquee"

    c.registre.signer(empreinte(4), AUTRE_COSIGN)  # pas signée par MEGGA
    n4 = proposer(c, 4, "0.4.0")
    c.tour(p)
    assert inst.reglages.changer("mise_a_jour", inst._maj(), {"numero": n4, "version": "0.4.0", "image": image(4), "phase": "prete",
                                                           "reference": image(4), "depuis": c.horloge()})
    assert hote(c, p, image(1)) == "rien"


def test_une_image_que_le_client_n_a_pas_acceptee_ne_part_pas(canal, tmp_path):
    c = canal
    p = preparer(c, tmp_path, accord="oui")
    numero = proposer(c, 4, "0.4.0")
    c.tour(p)
    assert etat(p, numero) == "attente_accord"
    assert p.installation.reglages.changer("mise_a_jour", None, {"numero": numero, "version": "0.4.0", "image": image(4), "phase": "lancee",
                                                               "reference": image(4), "avant": image(1), "depuis": c.horloge(),
                                                               "en_place": False, "saines": 0})
    assert hote(c, p, image(1)) == "rien" and etat(p, numero) == "attente_accord"


def test_une_ligne_changee_pendant_la_sauvegarde_n_est_pas_rendue(canal, tmp_path, monkeypatch):
    c = canal
    p = preparer(c, tmp_path, accord="non")
    c.registre.signer(empreinte(2))
    proposer(c, 2, "0.2.0")
    c.tour(p), c.tour(p)
    inst = p.installation
    vraie = images.sauvegarder

    def retouchee(*a, **k):
        f = vraie(*a, **k)
        r = inst._maj()
        inst.reglages.changer("mise_a_jour", r, {**r, "phase": "lancee", "reference": "evil.example/x/y@" + empreinte(99), "avant": image(1)})
        return f

    monkeypatch.setattr(images, "sauvegarder", retouchee)
    assert hote(c, p, image(1)) == "rien"


class KubeRefuse(FauxKubernetes):
    refuse = True

    def __call__(self, q):
        if q.method == "PATCH" and self.refuse:
            return httpx.Response(403)
        return super().__call__(q)


def _sous_kube(c, tmp_path, kube):
    return preparer(c, tmp_path, accord="non", PILOTAGE_DELAI="60", AGENT_DEPLOIEMENT="agent", PILOTE_DEPLOIEMENT="agent-pilote",
                    KUBERNETES_SERVICE_HOST="10.0.0.1", POD_NAMESPACE="clients", _kube=httpx.MockTransport(kube))


def test_sous_kubernetes_un_changement_refuse_finit_en_echec(canal, tmp_path):
    """I18 : l'API refuse le changement d'image (droits, règle d'admission) : après le délai, l'ordre est en échec et
    la mise à jour suivante peut partir, au lieu de rester bloquée sans alerte."""
    c = canal
    kube = KubeRefuse(image(1))
    p = _sous_kube(c, tmp_path, kube)
    c.registre.signer(empreinte(2))
    numero = proposer(c, 2, "0.2.0")
    for _ in range(3):
        c.tour(p)
    c.horloge.t += 120
    c.tour(p), c.tour(p)
    assert etat(p, numero) == "echec" and p.installation._maj() is None and kube.images["agent"] == image(1)


def test_sous_kubernetes_un_retour_refuse_est_abandonne_et_dit(canal, tmp_path):
    c = canal
    kube = KubeRefuse(image(1))
    kube.refuse = False
    p = _sous_kube(c, tmp_path, kube)
    c.registre.signer(empreinte(2))
    numero = proposer(c, 2, "0.2.0")
    for _ in range(3):
        c.tour(p)
    assert kube.images["agent"] == image(2)
    c.sante.ok = False
    c.horloge.t += 61
    kube.refuse = True
    c.tour(p)
    assert etat(p, numero) == "echec" and p.installation._maj()["phase"] == "retour"
    c.horloge.t += 120
    c.tour(p)
    assert p.installation._maj() is None
    assert any(a["genre"] == "mise_a_jour_bloquee" for a in stockage.Journal(c.url).alertes(0))


def test_une_panne_entre_deux_ecritures_ne_relance_pas_l_image(canal, tmp_path):
    """I19 : l'état de l'ordre s'écrit avant la phase ; une panne entre les deux se rattrape au relevé suivant."""
    c = canal
    p, numero = lancee(c, tmp_path)
    inst = p.installation
    assert hote(c, p, image(2)) == "attendre"
    c.sante.ok = None
    c.horloge.t += 61
    vraie = inst.ordres.changer

    def panne(*a, **k):
        inst.ordres.changer = vraie
        raise RuntimeError("base coupée un instant")

    inst.ordres.changer = panne
    with pytest.raises(RuntimeError):
        inst.suivre_image({"ok": False}, c.horloge())
    assert inst._maj()["phase"] == "lancee"  # rien d'écrit : tout se refait
    c.tour(p)
    assert etat(p, numero) == "echec" and inst._maj()["phase"] == "retour"
    assert hote(c, p, image(2)) == f"revenir {image(1)}" and hote(c, p, image(1)) == "rien"
    c.tour(p), c.tour(p)
    assert hote(c, p, image(1)) == "rien"


def test_une_sauvegarde_interrompue_ne_reste_pas(canal, tmp_path):
    """I20 : le fichier d'une sauvegarde tuée en route est effacé à la suivante."""
    d = tmp_path / "s"
    d.mkdir()
    orphelin = d / ".megga-exemple-20250101-000000-avant-0.1.0.jsonl.gz.partiel"
    orphelin.write_bytes(b"x" * 1000)
    images.sauvegarder(canal.url, d, "exemple", "0.2.0")
    assert not orphelin.exists() and len(images.sauvegardes(d, "exemple")) == 1


def test_helm_couper_les_mises_a_jour_garde_l_image_en_place():
    """I23 : l'image en place se relit dans le cluster quel que soit misesAJour ; seule une nouvelle empreinte dans les
    valeurs l'emporte."""
    aides = open("installation/helm/megga-agent/templates/_helpers.tpl").read()
    bloc = aides[aides.index('define "megga-agent.image-en-place"'):]
    bloc = bloc[:bloc.index("{{- end -}}\n\n")]
    assert "lookup" in bloc and "misesAJour" not in bloc and "pilotage.mode" not in bloc


def test_les_cles_publiques_sont_dans_l_image():
    """I21 : sans noyau/licence.pub, aucune licence n'est acceptée et l'agent ne démarre pas chez un client."""
    from noyau import licence

    for f in ("noyau/licence.pub", "noyau/pilotage.pub", "socle/cosign.pub"):
        assert os.path.getsize(f) > 0, f
    licence.cle_publique()  # lisible
    publier = open(".github/workflows/publier.yml").read()
    assert "test -s noyau/licence.pub" in publier and "test -s noyau/pilotage.pub" in publier
