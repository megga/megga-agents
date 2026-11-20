"""Lot 6.3 : le pilote et le canal de pilotage des installations hors Cloudflare.

Le canal de bout en bout, sans réseau : l'atelier (son app, sa base), le pilote de l'installation
(httpx vers l'atelier en mémoire) et l'agent (son /sante, sa base), avec de vraies signatures.
"""

import asyncio
import base64
import json
import os
import time
import uuid

import httpx
import pytest
import yaml
from fastapi.testclient import TestClient

from atelier.app import creer as creer_atelier
from noyau import config as configuration
from noyau import pilotage, stockage
from noyau.app import creer as creer_agent
from pilote.__main__ import main as commande
from pilote.service import DELAI_APPLICATION, Installation, Pilote, adresse
from test_app import FauxAgent, FauxExpediteur
from test_lot5 import ADMIN, CLE_PILOTAGE, CLE_PILOTAGE_TEXTE, MEGGA, FaussePorte, cle_jetable, jeton_client
from test_lot6_client import CLE as CLE_LICENCE
from test_lot6_client import jeton as licence

CLE_INSTALLATION, CLE_INSTALLATION_TEXTE = cle_jetable()
CLE_PUBLIQUE_INSTALLATION = pilotage.en_texte(CLE_INSTALLATION.public_key())
AUTRE_CLE, _ = cle_jetable()
PUB = CLE_PILOTAGE.public_key()
BASES = ["sqlite"] + (["postgres"] if os.environ.get("TEST_POSTGRES_URL") else [])


def conf_client(**autres) -> dict:
    d = configuration.lire("clients/exemple.yaml").model_dump(mode="json")
    return {**d, "zone": "client", **autres}


BASE = configuration.lire(conf_client())
CONF_CLIENT = json.dumps(conf_client())


def ordre_config(numero=1, version=1, cle=CLE_PILOTAGE, quand=None, client="exemple", **changements) -> str:
    return pilotage.ordre(client, numero, "config", {"version": version, "config": conf_client(**changements)}, cle,
                          time.time() if quand is None else quand)


# Le protocole : clés, ordres, requêtes signées


def test_un_ordre_de_megga_est_verifie_de_bout_en_bout():
    o = pilotage.lire_ordre(ordre_config(nom_agent="Lea"), BASE, PUB, time.time())
    assert (o["client"], o["numero"], o["genre"]) == ("exemple", 1, "config")
    assert pilotage.config_de(o, BASE)[1].nom_agent == "Lea"
    refus = [
        (ordre_config(cle=AUTRE_CLE), "non signé par MEGGA"),
        (ordre_config(client="autre"), "autre client"),
        (ordre_config(quand=time.time() - pilotage.DUREE_ORDRE - 10), "expiré"),
        (ordre_config(zone="europe"), "zone"),
        (ordre_config(metier="immobilier", outils=["immobilier"]), "incomplète"),
        (pilotage.ordre("exemple", 1, "config", {"version": 1, "config": {"id": "exemple"}}, CLE_PILOTAGE, time.time()), "invalide"),
        (pilotage.ordre("exemple", 1, "config", {"config": conf_client()}, CLE_PILOTAGE, time.time()), "version"),
        (pilotage.ordre("exemple", 1, "image", {"version": "0.2.0", "image": "docker.io/autre@sha256:" + "0" * 64}, CLE_PILOTAGE, time.time()), "image"),
        (pilotage.signer({"format": 1, "client": "exemple", "numero": 1, "genre": "commande", "cree": 1, "expire": 2 ** 40,
                          "contenu": {"lancer": "rm -rf /"}}, CLE_PILOTAGE), "genre"),
        ("abc", "mal formé"),
    ]
    for j, motif in refus:
        with pytest.raises(pilotage.PilotageRefuse, match=motif):
            pilotage.lire_ordre(j, BASE, PUB, time.time())
    # retouché après signature : refusé
    donnees, signature = ordre_config().split(".")
    faux = pilotage._b64(json.dumps({**pilotage.contenu(ordre_config()), "numero": 99}).encode())
    with pytest.raises(pilotage.PilotageRefuse, match="non signé"):
        pilotage.lire_ordre(f"{faux}.{signature}", BASE, PUB)
    image = pilotage.ordre("exemple", 2, "image", {"version": "0.2.0", "image": "ghcr.io/megga/megga-agents@sha256:" + "a" * 64},
                           CLE_PILOTAGE, time.time())
    assert pilotage.lire_ordre(image, BASE, PUB)["genre"] == "image"


def test_les_cles_en_pem_ou_sur_une_ligne(monkeypatch, tmp_path):
    from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat

    pem = CLE_INSTALLATION.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()).decode()
    der = base64.b64encode(CLE_INSTALLATION.private_bytes(Encoding.DER, PrivateFormat.PKCS8, NoEncryption())).decode()
    for texte in (pem, der, CLE_INSTALLATION_TEXTE):  # PEM, openssl genpkey -outform DER | base64, 32 octets
        assert pilotage.en_texte(pilotage.cle_privee(texte).public_key()) == CLE_PUBLIQUE_INSTALLATION
    publique = CLE_INSTALLATION.public_key()
    for texte in (publique.public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo).decode(), CLE_PUBLIQUE_INSTALLATION,
                  base64.b64encode(publique.public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()):
        assert pilotage.en_texte(pilotage.cle_publique(texte)) == CLE_PUBLIQUE_INSTALLATION
    for mauvaise in ("", "pas une clé", base64.b64encode(b"x" * 31).decode()):
        with pytest.raises(pilotage.PilotageRefuse):
            pilotage.cle_privee(mauvaise)
        with pytest.raises(pilotage.PilotageRefuse):
            pilotage.cle_publique(mauvaise)
    monkeypatch.setattr(pilotage, "CLE_PUBLIQUE", tmp_path / "absente.pub")
    with pytest.raises(pilotage.PilotageRefuse, match="absente de l'image"):
        pilotage.lire_ordre(ordre_config(), BASE)


def test_une_requete_signee_par_l_installation():
    corps = b'{"pilotage":"suivi"}'
    h = pilotage.entetes("exemple", CLE_INSTALLATION, "POST", "/pilotage/releve", corps)
    cle_de = {"exemple": CLE_INSTALLATION.public_key()}.get
    assert pilotage.verifier_requete(h, "POST", "/pilotage/releve", corps, cle_de) == ("exemple", h["x-megga-nonce"])
    refus = [
        (h, "POST", "/pilotage/releve", b'{"pilotage":"complet"}', "signature"),  # corps changé
        (h, "POST", "/pilotage/autre", corps, "signature"),
        ({**h, "x-megga-installation": "autre"}, "POST", "/pilotage/releve", corps, "inconnue"),
        ({**h, "x-megga-heure": str(int(time.time()) - 301)}, "POST", "/pilotage/releve", corps, "fenêtre"),
        ({**h, "x-megga-nonce": "court"}, "POST", "/pilotage/releve", corps, "non signée"),
        ({k: v for k, v in h.items() if k != "x-megga-signature"}, "POST", "/pilotage/releve", corps, "non signée"),
    ]
    for entetes, methode, chemin, c, motif in refus:
        with pytest.raises(pilotage.PilotageRefuse, match=motif):
            pilotage.verifier_requete(entetes, methode, chemin, c, cle_de)
    signee_ailleurs = pilotage.entetes("exemple", AUTRE_CLE, "POST", "/pilotage/releve", corps)
    with pytest.raises(pilotage.PilotageRefuse, match="signature"):
        pilotage.verifier_requete(signee_ailleurs, "POST", "/pilotage/releve", corps, cle_de)


def test_aucun_numero_ni_secret_ne_sort_d_un_detail():
    assert pilotage.sans_donnees("envoi à +41 79 000 00 00 refusé") == "envoi à [numéro] refusé"
    assert pilotage.sans_donnees("41790000000") == "[numéro]"
    assert "postgresql" not in pilotage.sans_donnees("connexion postgresql://u:p@hote/base perdue")
    assert pilotage.sans_donnees("ModelProviderError 131047") == "ModelProviderError 131047"  # un code d'erreur reste


def test_l_adresse_de_megga_est_en_https():
    assert adresse("https://megga-agents.api-963.workers.dev/") == "https://megga-agents.api-963.workers.dev"
    assert adresse("http://atelier:8080") == "http://atelier:8080"  # un nom local, pour les essais
    for mauvaise in ("http://megga-agents.api-963.workers.dev", "", "ftp://x", "http://[2001:db8::1]", "http://134744072",
                     "http://0x08080808"):
        with pytest.raises(RuntimeError):
            adresse(mauvaise)


# Les tables, sur SQLite et Postgres


@pytest.fixture(params=BASES)
def url(request, tmp_path):
    if request.param == "sqlite":
        return f"sqlite:///{tmp_path}/pilotage.db"
    return os.environ["TEST_POSTGRES_URL"]


def test_les_ordres_cote_megga(url):
    client = f"essai-{uuid.uuid4().hex[:8]}"  # sous Postgres, la base est partagée entre les essais
    o = stockage.Ordres(url)
    signes = []

    def signer(n, q):
        signes.append(n)
        return f"jeton-{n}"

    assert o.deposer(client, "config", signer, 100, 1000.0) == {"numero": 1, "remplaces": []}
    assert o.deposer(client, "image", signer, 100, 1001.0)["numero"] == 2
    # une configuration plus récente remplace celle qui n'est pas encore partie ; l'image reste
    assert o.deposer(client, "config", signer, 100, 1002.0) == {"numero": 3, "remplaces": [1]}
    assert signes == [1, 2, 3]
    lignes, nouveaux = o.a_remettre(client, 0, 1010.0)
    assert [l["numero"] for l in lignes] == [2, 3] and nouveaux == [2, 3]
    lignes, nouveaux = o.a_remettre(client, 2, 1011.0)  # l'installation a déjà le 2
    assert [l["numero"] for l in lignes] == [3] and nouveaux == []
    assert o.noter_etats(client, [{"numero": 3, "etat": "refuse"}, {"numero": 3, "etat": "applique", "detail": "ok"},
                                  {"numero": 2, "etat": "inconnu"}, {"numero": "3", "etat": "refuse"}, "x"],
                         1012.0) == [{"numero": 3, "etat": "applique", "detail": "ok"}]  # le dernier mot par ordre
    assert o.noter_etats(client, [{"numero": 3, "etat": "applique"}], 1013.0) == []  # rien de neuf
    assert o.lire(client, 3)["etat"] == "applique"
    o.deposer(client, "config", signer, 100, 1020.0)
    # un ordre jamais remis n'a pas d'état chez l'installation ; un ordre fini n'en change plus
    assert o.noter_etats(client, [{"numero": 4, "etat": "applique"}], 1021.0) == []
    o.changer(client, 3, "remplace")
    assert o.noter_etats(client, [{"numero": 3, "etat": "applique"}], 1022.0) == []
    assert o.expirer(client, 2000.0) == [2, 4] and o.lire(client, 4)["etat"] == "expire"  # l'image remise mais jamais reçue aussi
    assert o.a_remettre(client, 0, 2000.0) == ([], [])
    assert o.dernier_numero(client) == 4 and o.dernier_numero("personne") == 0
    # jamais en dessous du dernier numéro reçu par l'installation (base de l'atelier restaurée)
    assert o.deposer(client, "config", signer, 100, 2001.0, minimum=9)["numero"] == 10


def test_les_ordres_cote_installation(url):
    client = f"essai-{uuid.uuid4().hex[:8]}"
    o = stockage.Ordres(url)
    assert o.ajouter(client, 1, "config", "j1", "applique", "", 1.0, 2.0, 3.0)
    assert not o.ajouter(client, 1, "config", "j1", "applique", "", 1.0, 2.0, 3.0)  # déjà là
    o.ajouter(client, 2, "config", "j2", "a_appliquer", "", 1.0, 2.0, 3.0)
    o.ajouter(client, 3, "image", "j3", "propose", "", 1.0, 2.0, 3.0)
    assert o.a_servir(client)["numero"] == 2
    assert o.remplacer(client, "config", ("applique",), 2) == [1]
    assert o.changer(client, 2, "echec", "délai", depuis=("a_appliquer",))
    assert not o.changer(client, 2, "applique", depuis=("a_appliquer",))
    assert o.a_servir(client) is None
    assert [l["numero"] for l in o.lister(client, etats=("propose",))] == [3]


@pytest.fixture
def tables_atelier(url):
    """Sous Postgres (base partagée), les tables de l'atelier sont retirées après l'essai : la base d'un client
    ne les a jamais, et l'essai d'export la prend pour celle d'un client."""
    yield url
    e = stockage.moteur(url)
    if e.dialect.name == "postgresql":
        with e.begin() as c:
            for nom in ("megga_installations", "megga_nonces"):
                c.execute(stockage.text(f'DROP TABLE IF EXISTS "{stockage.SCHEMA}".{nom}'))


def test_installations_journal_et_nonces(tables_atelier):
    url = tables_atelier
    client = f"essai-{uuid.uuid4().hex[:8]}"
    i = stockage.Installations(url)
    i.enregistrer(client, "cle-1", 10.0)
    assert i.cle(client) == "cle-1"
    i.noter_releve(client, {"pilotage": "suivi"}, {"fenetres": {}}, 11.0)
    i.noter_releve(client, {"pilotage": "complet"}, None, 12.0)  # sans suivi : le dernier reste
    lu = i.lire(client)
    assert (lu["releve"], lu["etat"], lu["suivi"]) == (12.0, {"pilotage": "complet"}, {"fenetres": {}})
    assert i.revoquer(client, 13.0) and not i.revoquer(client, 14.0)
    assert i.cle(client) is None
    i.enregistrer(client, "cle-2", 15.0)  # une nouvelle clé lève la révocation
    assert i.cle(client) == "cle-2" and i.lire(client)["revoquee"] is None
    assert client in {x["client"] for x in i.toutes()}
    j = stockage.JournalPilotage(url)
    j.noter(client, "depose", 1, "configuration, version 1", 1.0)
    j.noter(client, "applique", 1, "", 2.0)
    assert [e["evenement"] for e in j.lire(client)] == ["applique", "depose"]
    n = stockage.Nonces(url)
    nonce = uuid.uuid4().hex
    assert n.nouveau(client, nonce, time.time()) and not n.nouveau(client, nonce, time.time())


def test_le_pilote_attend_que_l_agent_ait_migre_la_base(tmp_path):
    url = f"sqlite:///{tmp_path}/neuve.db"
    assert not stockage.migree(url)
    stockage.migrer(url)
    assert stockage.migree(url)


def test_l_export_d_un_client_garde_son_pilotage(tmp_path):
    source, cible = f"sqlite:///{tmp_path}/a.db", f"sqlite:///{tmp_path}/b.db"
    stockage.migrer(source)
    stockage.Ordres(source).ajouter("exemple", 1, "config", "j", "applique", "", 1.0, 2.0)
    stockage.JournalPilotage(source).noter("exemple", "applique", 1)
    stockage.exporter(source, tmp_path / "export.jsonl")
    stockage.importer(tmp_path / "export.jsonl", cible)
    assert stockage.Ordres(cible).a_servir("exemple")["jeton"] == "j"


# L'agent chez le client : la configuration poussée


def agent_client(url, pilotage_mode="complet", quitter=lambda: None, **k):
    """L'agent chez le client ; `quitter` ne tue jamais le processus des essais."""
    return creer_agent({"CLIENT_CONFIG": CONF_CLIENT, "META_APP_SECRET": "s", "MEGGA_INSTALLATION": "client",
                        "MEGGA_LICENCE": licence(), "DATABASE_URL": url, "PILOTAGE": pilotage_mode},
                       agent=FauxAgent(), expediteur=FauxExpediteur(), cle_licence=CLE_LICENCE.public_key(), cle_pilotage=PUB,
                       quitter=quitter, **k)


def base_client(tmp_path) -> str:
    url = f"sqlite:///{tmp_path}/client.db"
    stockage.migrer(url)
    return url


def test_l_agent_sert_la_derniere_configuration_poussee(tmp_path):
    url = base_client(tmp_path)
    app = agent_client(url)
    assert app.state.config.nom_agent == "Alix"
    assert TestClient(app).get("/sante").json()["configuration"] == {"source": "fichier"}
    o = stockage.Ordres(url)
    o.ajouter("exemple", 1, "config", ordre_config(1, 3, nom_agent="Lea"), "applique", "", 1, 2)
    o.ajouter("exemple", 2, "config", ordre_config(2, 4, nom_agent="Zoe"), "a_appliquer", "", 1, 2)
    o.ajouter("exemple", 3, "config", ordre_config(3, 5, nom_agent="Eva"), "attente_accord", "", 1, 2)  # pas encore accepté
    app = agent_client(url)
    assert app.state.config.nom_agent == "Zoe"
    assert TestClient(app).get("/sante").json()["configuration"] == {"source": "pilotage", "version": 4, "ordre": 2}
    # une configuration retouchée dans la base, sans la signature de MEGGA, ne sert jamais
    o.ajouter("exemple", 4, "config", ordre_config(4, 6, cle=AUTRE_CLE, nom_agent="Pirate"), "a_appliquer", "", 1, 2)
    app = agent_client(url)
    assert app.state.config.nom_agent == "Alix"
    assert TestClient(app).get("/sante").json()["configuration"] == {"source": "fichier"}


def test_l_agent_redemarre_quand_une_autre_configuration_est_a_servir(tmp_path):
    url = base_client(tmp_path)
    arrets = []
    app = agent_client(url, quitter=lambda: arrets.append(1))
    with TestClient(app) as t:
        t.portal.call(asyncio.sleep, 0.1)
    assert arrets == []  # rien de neuf : la veille ne relance pas l'agent
    stockage.Ordres(url).ajouter("exemple", 1, "config", ordre_config(nom_agent="Lea"), "a_appliquer", "", 1, 2)
    with TestClient(app) as t:  # la veille voit la nouvelle configuration dès son premier tour
        for _ in range(40):
            if arrets:
                break
            t.portal.call(asyncio.sleep, 0.05)
    assert arrets == [1]
    # chez MEGGA, derrière la porte : aucun pilotage, la configuration vient de l'annuaire
    hebergee = creer_agent({"CLIENT_CONFIG": CONF_CLIENT, "META_APP_SECRET": "s", "DATABASE_URL": url},
                           agent=FauxAgent(), expediteur=FauxExpediteur(), cle_pilotage=PUB)
    assert hebergee.state.config.nom_agent == "Alix" and "configuration" not in TestClient(hebergee).get("/sante").json()


# Le canal de bout en bout : atelier, pilote, agent


class Horloge:
    def __init__(self):
        self.t = time.time()

    def __call__(self):
        return self.t


@pytest.fixture
def canal(tmp_path):
    """L'atelier (sa base), une installation enregistrée (sa base, son agent), et de quoi faire tourner son pilote."""
    atelier = creer_atelier({"ADMIN_TOKEN": ADMIN, "DATABASE_URL": f"sqlite:///{tmp_path}/atelier.db", "PILOTAGE_CLE": CLE_PILOTAGE_TEXTE,
                             "ESSAIS_DIR": str(tmp_path / "essais")}, porte=FaussePorte())
    t = TestClient(atelier)
    assert t.post("/atelier/clients", headers=MEGGA, json={"config": conf_client()}).status_code == 201
    r = t.put("/atelier/clients/exemple/installation", headers=MEGGA, json={"cle_publique": CLE_PUBLIQUE_INSTALLATION})
    assert r.status_code == 200 and r.json()["cle"] == pilotage.empreinte(CLE_PUBLIQUE_INSTALLATION)
    url = base_client(tmp_path)

    class Canal:
        pass

    c = Canal()
    c.t, c.atelier, c.url, c.horloge = t, atelier, url, Horloge()
    c.agent = agent_client(url)

    def pilote(**env):
        return Pilote({"PILOTAGE": "complet", "PILOTAGE_ACCORD": "non", "CLIENT_CONFIG": CONF_CLIENT, "DATABASE_URL": url,
                       "PILOTE_CLE": CLE_INSTALLATION_TEXTE, **env},
                      transport=httpx.ASGITransport(app=atelier), transport_agent=httpx.ASGITransport(app=c.agent),
                      cle_megga=PUB, horloge=c.horloge)

    def tour(p):
        return asyncio.run(p.tour())

    def relancer_agent():  # Compose ou Kubernetes relancent l'agent, qui relit sa configuration
        c.agent = agent_client(url)
        return c.agent

    def ordres():
        return {o["numero"]: o["etat"] for o in t.get("/atelier/clients/exemple/installation", headers=MEGGA).json()["ordres"]}

    c.pilote, c.tour, c.relancer_agent, c.ordres = pilote, tour, relancer_agent, ordres
    return c


def nouvelle_version(t, **changements) -> int:
    r = t.post("/atelier/clients/exemple/versions", headers=MEGGA, json={"changements": changements})
    assert r.status_code == 201, r.text
    return r.json()["version"]


def activer(t, v):
    return t.post(f"/atelier/clients/exemple/versions/{v}/activer", headers=MEGGA, json={"forcer": True})


def test_une_version_part_de_l_atelier_et_l_agent_la_sert(canal):
    c = canal
    r = activer(c.t, 1)
    assert r.status_code == 200 and r.json()["pilotage"] == {"ordre": 1, "installation": True}
    p = c.pilote()
    p.transport_agent = httpx.ASGITransport(app=c.agent)
    c.tour(p)  # remis, vérifié, à appliquer
    assert c.ordres() == {1: "remis"}
    assert Installation(c.url, BASE).ordres.lire("exemple", 1)["etat"] == "a_appliquer"
    p.transport_agent = httpx.ASGITransport(app=c.relancer_agent())  # l'agent a vu l'ordre et s'est relancé
    assert c.agent.state.config.nom_agent == "Alix"  # la version 1 est la configuration de départ
    c.tour(p)  # l'agent sert l'ordre 1 : appliqué
    c.tour(p)  # et l'atelier l'apprend
    assert c.ordres() == {1: "applique"}
    lu = c.t.get("/atelier/clients/exemple", headers=MEGGA).json()
    assert lu["installation"]["configuration"] == {"source": "pilotage", "version": 1, "ordre": 1} and lu["ecart"] is False
    # une nouvelle version : l'écart se voit jusqu'à ce que l'installation la serve
    v = nouvelle_version(c.t, ton="direct")
    assert activer(c.t, v).json()["pilotage"]["ordre"] == 2
    assert c.t.get("/atelier/clients", headers=MEGGA).json()["clients"][0]["ecart"] is True
    c.tour(p)
    p.transport_agent = httpx.ASGITransport(app=c.relancer_agent())
    assert c.agent.state.config.ton == "direct"
    c.tour(p)
    c.tour(p)
    assert c.ordres() == {1: "remplace", 2: "applique"}
    assert c.t.get("/atelier/clients/exemple", headers=MEGGA).json()["ecart"] is False
    journal = [e["evenement"] for e in c.t.get("/atelier/clients/exemple/installation", headers=MEGGA).json()["journal"]]
    assert {"cle_enregistree", "depose", "remis", "applique", "remplace"} <= set(journal)
    local = [e["evenement"] for e in Installation(c.url, BASE).journal.lire("exemple")]
    assert {"demarrage", "a_appliquer", "applique", "remplace"} <= set(local)
    # renvoyer la version en service : refusé, l'installation la sert déjà
    assert activer(c.t, v).status_code == 409


def test_avec_l_accord_du_client(canal):
    c = canal
    p = c.pilote(PILOTAGE_ACCORD="oui")
    v = nouvelle_version(c.t, nom_agent="Lea")
    activer(c.t, v)
    c.tour(p)
    inst = Installation(c.url, BASE, PUB)
    assert inst.ordres.lire("exemple", 1)["etat"] == "attente_accord"
    env = {"CLIENT_CONFIG": CONF_CLIENT, "DATABASE_URL": c.url, "PILOTAGE": "complet"}
    sortie = []
    assert commande(["ordres"], env, sortie.append, cle_megga=PUB) == 0
    texte = "\n".join(sortie)
    assert "attend votre accord" in texte and "nom_agent : « Alix » devient « Lea »" in texte and "accepter 1" in texte
    c.tour(p)
    assert c.ordres() == {1: "attente_accord"}
    assert commande(["accepter", "1"], env, sortie.append, cle_megga=PUB) == 0
    assert inst.ordres.lire("exemple", 1)["etat"] == "a_appliquer"
    assert commande(["accepter", "1"], env, sortie.append, cle_megga=PUB) == 1  # n'attend plus rien
    # un refus
    v2 = nouvelle_version(c.t, nom_agent="Zoe")
    activer(c.t, v2)
    c.tour(p)
    assert commande(["refuser", "2"], env, sortie.append, cle_megga=PUB) == 0
    c.tour(p)
    assert c.ordres()[2] == "refuse"
    genres = [a["genre"] for a in c.t.get("/atelier/clients/exemple/alertes", headers=MEGGA).json()["alertes"]]
    assert "ordre_refuse" in genres
    # renvoyer la version refusée : un nouvel ordre part
    assert activer(c.t, v2).json()["pilotage"]["ordre"] == 3


def test_sous_suivi_aucun_ordre_ne_passe(canal):
    c = canal
    activer(c.t, 1)
    p = c.pilote(PILOTAGE="suivi")
    r = c.tour(p)
    assert r["ordres"] == [] and c.ordres() == {1: "en_attente"}
    assert Installation(c.url, BASE).ordres.lister("exemple") == []
    # même si MEGGA en remettait un, le pilote ne le prendrait pas : c'est le réglage du client qui décide
    class Bavarde(httpx.AsyncBaseTransport):
        async def handle_async_request(self, requete):
            return httpx.Response(200, json={"ordres": [ordre_config()]})

    p.transport = Bavarde()
    c.tour(p)
    assert Installation(c.url, BASE).ordres.lister("exemple") == []


def test_le_suivi_ne_porte_jamais_une_conversation(canal):
    c = canal
    stockage.Fil(c.url).noter("+41790000000", "recu", "texte", "Mon code secret est 4321, rappelez-moi")
    stockage.Journal(c.url).noter("envoi_echec", detail="refus pour +41 79 123 45 67")
    stockage.Journal(c.url).noter("voix_caracteres", 120)
    p = c.pilote(PILOTAGE="suivi")
    vus = []

    class Espionne(httpx.AsyncBaseTransport):
        async def handle_async_request(self, requete):
            vus.append(requete.content.decode())
            return await httpx.ASGITransport(app=c.atelier).handle_async_request(requete)

    p.transport = Espionne()
    c.tour(p)
    envoye = vus[0]
    for prive in ("4321", "rappelez-moi", "41790000000", "79 123 45 67", "secret"):
        assert prive not in envoye
    s = c.t.get("/atelier/clients/exemple/suivi?jours=7", headers=MEGGA).json()
    assert s["activite"]["journal"]["voix_caracteres"]["quantite"] == 120 and s["periode_jours"] == 7
    assert "couts" in s and s["installation"]["pilotage"] == "suivi"
    assert c.t.get("/atelier/clients/exemple/suivi?jours=2", headers=MEGGA).status_code == 400
    alertes = c.t.get("/atelier/clients/exemple/alertes", headers=MEGGA).json()["alertes"]
    assert {"genre": "envoi_echec", "detail": "refus pour [numéro]"} in [{k: a[k] for k in ("genre", "detail")} for a in alertes]
    # MEGGA ne lit jamais une conversation (20.11.2026) ; celles d'une installation ne la quittent pas, même pour son client
    assert c.t.get("/atelier/clients/exemple/conversations", headers=MEGGA).status_code == 403
    assert c.t.get("/atelier/clients/exemple/conversations/41790000000", headers=MEGGA).status_code == 403
    client = jeton_client(c.t)
    assert c.t.get("/atelier/clients/exemple/conversations", headers=client).status_code == 409
    assert c.t.get("/atelier/clients/exemple/conversations/41790000000", headers=client).status_code == 409
    # le suivi suivant attend 5 minutes ; l'état part à chaque relevé
    vus.clear()
    c.tour(p)
    assert "fenetres" not in vus[0] and '"agent"' in vus[0]


def test_une_configuration_que_l_agent_ne_prend_pas_revient_en_arriere(canal):
    c = canal
    p = c.pilote()
    activer(c.t, 1)
    c.tour(p)
    p.transport_agent = httpx.ASGITransport(app=c.relancer_agent())
    c.tour(p)
    v = nouvelle_version(c.t, ton="direct")
    activer(c.t, v)
    c.tour(p)  # ordre 2 à appliquer ; l'agent, lui, reste sur l'ordre 1
    inst = Installation(c.url, BASE, PUB)
    assert inst.config_servie()[1]["ordre"] == 2
    c.horloge.t += DELAI_APPLICATION + 1
    c.tour(p)
    assert inst.ordres.lire("exemple", 2)["etat"] == "echec"
    assert inst.config_servie()[1]["ordre"] == 1  # l'agent revient à la précédente
    c.tour(p)
    assert c.ordres()[2] == "echec"
    assert "retour à l'ordre 1" in inst.journal.lire("exemple")[0]["detail"]


def test_le_client_revient_a_son_fichier(canal):
    c = canal
    p = c.pilote()
    activer(c.t, nouvelle_version(c.t, nom_agent="Lea"))
    c.tour(p)
    env = {"CLIENT_CONFIG": CONF_CLIENT, "DATABASE_URL": c.url, "PILOTAGE": "complet"}
    sortie = []
    assert commande(["revenir"], env, sortie.append) == 0
    assert "client.yaml" in sortie[-1]
    assert c.relancer_agent().state.config.nom_agent == "Alix"
    c.tour(p)
    assert c.ordres()[1] == "retire"
    n = len(sortie)
    assert commande(["journal", "5"], env, sortie.append) == 0
    assert "retire, ordre 1 : retiré par le client" in sortie[n]  # le plus récent d'abord


def test_une_image_proposee_est_notee_seulement(canal):
    c = canal
    image = "ghcr.io/megga/megga-agents@sha256:" + "b" * 64
    for mauvais in ({"version": "0.2", "image": image}, {"version": "0.2.0", "image": "ghcr.io/autre/image@sha256:" + "b" * 64}):
        assert c.t.post("/atelier/clients/exemple/installation/image", headers=MEGGA, json=mauvais).status_code == 400
    r = c.t.post("/atelier/clients/exemple/installation/image", headers=MEGGA, json={"version": "0.2.0", "image": image})
    assert r.status_code == 201 and r.json()["ordre"] == 1
    p = c.pilote()
    c.tour(p)
    inst = Installation(c.url, BASE, PUB)
    assert inst.ordres.lire("exemple", 1)["etat"] == "propose"
    env = {"CLIENT_CONFIG": CONF_CLIENT, "DATABASE_URL": c.url, "PILOTAGE": "complet"}
    sortie = []
    assert commande(["accepter", "1"], env, sortie.append, cle_megga=PUB) == 1 and "MISES_A_JOUR" in sortie[-1]
    assert commande(["refuser", "1"], env, sortie.append, cle_megga=PUB) == 0
    c.tour(p)
    assert c.ordres() == {1: "refuse"}


def test_un_ordre_falsifie_est_refuse_sans_rien_decaler(canal):
    c = canal
    p = c.pilote()

    class Pirate(httpx.AsyncBaseTransport):
        async def handle_async_request(self, requete):
            await httpx.ASGITransport(app=c.atelier).handle_async_request(requete)
            return httpx.Response(200, json={"ordres": [ordre_config(numero=999, cle=AUTRE_CLE, nom_agent="Pirate")]})

    p.transport = Pirate()
    c.tour(p)
    inst = p.installation
    assert inst.ordres.lister("exemple") == [] and inst.ordres.dernier_numero("exemple") == 0
    assert inst.statuts() == [{"numero": 999, "etat": "refuse", "detail": "ordre non signé par MEGGA"}]  # dit à MEGGA
    assert "non signé" in inst.journal.lire("exemple")[0]["detail"]


def test_l_atelier_ne_croit_que_les_releves_signes(canal):
    c = canal
    corps = json.dumps({"pilotage": "complet", "dernier_ordre": 0}).encode()

    def envoyer(entetes, contenu=corps):
        return c.t.post("/pilotage/releve", content=contenu, headers={**entetes, "content-type": "application/json"})

    h = pilotage.entetes("exemple", CLE_INSTALLATION, "POST", "/pilotage/releve", corps)
    assert envoyer(h).status_code == 200
    assert envoyer(h).json() == {"erreur": "requête rejouée"}  # la même requête, rejouée
    autres = [
        pilotage.entetes("exemple", AUTRE_CLE, "POST", "/pilotage/releve", corps),
        pilotage.entetes("inconnu", CLE_INSTALLATION, "POST", "/pilotage/releve", corps),
        pilotage.entetes("exemple", CLE_INSTALLATION, "POST", "/pilotage/releve", corps, time.time() - 600),
        {},
    ]
    for entetes in autres:
        assert envoyer(entetes).status_code == 401
    mal = json.dumps({"pilotage": "tout"}).encode()
    assert envoyer(pilotage.entetes("exemple", CLE_INSTALLATION, "POST", "/pilotage/releve", mal), mal).status_code == 401
    # révoquée par MEGGA : plus rien n'est accepté de cette clé
    assert c.t.delete("/atelier/clients/exemple/installation", headers=MEGGA).json() == {"client": "exemple", "revoquee": True}
    r = envoyer(pilotage.entetes("exemple", CLE_INSTALLATION, "POST", "/pilotage/releve", corps))
    # au pilote, une réponse unique : on ne sonde pas quelles installations existent
    assert r.status_code == 401 and r.json() == {"erreur": "installation non reconnue"}
    inconnue = envoyer(pilotage.entetes("inconnu", CLE_INSTALLATION, "POST", "/pilotage/releve", corps))
    assert inconnue.json() == {"erreur": "installation non reconnue"}
    assert "installation_revoquee" in [a["genre"] for a in c.t.get("/atelier/clients/exemple/alertes", headers=MEGGA).json()["alertes"]]


def test_les_roles_autour_des_installations(canal):
    c = canal
    jeton = c.t.post("/atelier/clients/exemple/jetons", headers=MEGGA).json()["jeton"]
    client = {"authorization": f"Bearer {jeton}"}
    assert c.t.get("/atelier/clients/exemple/installation", headers=client).status_code == 200  # il voit la sienne
    for methode, chemin, corps in (("put", "installation", {"cle_publique": CLE_PUBLIQUE_INSTALLATION}), ("delete", "installation", None),
                                   ("post", "installation/image", {"version": "0.2.0", "image": "x"})):
        r = c.t.request(methode.upper(), f"/atelier/clients/exemple/{chemin}", headers=client, json=corps)
        assert r.status_code == 403, chemin
    assert c.t.get("/atelier/installations", headers=client).status_code == 403
    toutes = c.t.get("/atelier/installations", headers=MEGGA).json()
    assert [i["client"] for i in toutes["installations"]] == ["exemple"] and toutes["cle_pilotage"] is True
    assert c.t.put("/atelier/clients/exemple/installation", headers=MEGGA, json={"cle_publique": "abc"}).status_code == 400
    # un client servi par la porte n'a pas d'installation à piloter
    c.t.post("/atelier/clients", headers=MEGGA, json={"config": {**conf_client(id="europe-1", zone="europe"),
                                                                "whatsapp": {"numero_id": "100000000000002"}}})
    assert c.t.put("/atelier/clients/europe-1/installation", headers=MEGGA, json={"cle_publique": CLE_PUBLIQUE_INSTALLATION}).status_code == 409


def test_une_installation_silencieuse_est_signalee(canal):
    c = canal
    activer(c.t, 1)
    genres = [a["genre"] for a in c.t.get("/atelier/clients/exemple/alertes", headers=MEGGA).json()["alertes"]]
    assert "installation_silencieuse" in genres  # jamais de relevé
    assert c.t.get("/atelier/clients/exemple/suivi", headers=MEGGA).status_code == 409  # pas encore de suivi
    p = c.pilote()
    c.tour(p)
    genres = [a["genre"] for a in c.t.get("/atelier/clients/exemple/alertes", headers=MEGGA).json()["alertes"]]
    assert "installation_silencieuse" not in genres
    # un agent qui ne répond plus se voit au relevé suivant
    p.transport_agent = httpx.MockTransport(lambda r: httpx.Response(503, json={"ok": False}))
    c.tour(p)
    genres = [a["genre"] for a in c.t.get("/atelier/clients/exemple/alertes", headers=MEGGA).json()["alertes"]]
    assert "agent_en_panne" in genres


def test_sans_cle_de_pilotage_l_atelier_ne_signe_rien(tmp_path):
    t = TestClient(creer_atelier({"ADMIN_TOKEN": ADMIN, "DATABASE_URL": f"sqlite:///{tmp_path}/a.db"}, porte=FaussePorte()))
    t.post("/atelier/clients", headers=MEGGA, json={"config": conf_client()})
    r = activer(t, 1)
    assert r.status_code == 503 and "scripts/pilotage.py" in r.json()["erreur"]
    assert t.get("/sante").json()["pilotage"] is False
    illisible = TestClient(creer_atelier({"ADMIN_TOKEN": ADMIN, "DATABASE_URL": f"sqlite:///{tmp_path}/b.db", "PILOTAGE_CLE": "abc"},
                                         porte=FaussePorte()))
    assert illisible.get("/sante").json()["pilotage"] is False  # l'atelier sert le reste


# Le pilote lui-même


def test_le_pilote_se_regle_chez_le_client(tmp_path):
    base = {"CLIENT_CONFIG": CONF_CLIENT}
    p = Pilote({**base})
    assert p.mode == "non" and asyncio.run(p.tour()) is None  # par défaut, rien ne sort
    for mauvais, motif in (({"PILOTAGE": "tout"}, "PILOTAGE"), ({"PILOTAGE": "suivi"}, "DATABASE_URL"),
                           ({"PILOTAGE": "suivi", "DATABASE_URL": "sqlite:///x"}, "PILOTE_CLE"),
                           ({"PILOTAGE": "suivi", "PILOTAGE_ACCORD": "peut-être"}, "PILOTAGE_ACCORD"),
                           ({"PILOTAGE": "suivi", "DATABASE_URL": "sqlite:///x", "PILOTE_CLE": CLE_INSTALLATION_TEXTE,
                             "PILOTAGE_URL": "http://megga.example"}, "https")):
        with pytest.raises(RuntimeError, match=motif):
            Pilote({**base, **mauvais})
    (tmp_path / "cle").write_text(CLE_INSTALLATION_TEXTE + "\n")
    p = Pilote({**base, "PILOTAGE": "suivi", "DATABASE_URL": "sqlite:///x", "PILOTE_CLE_FILE": str(tmp_path / "cle"),
                "PILOTAGE_URL": "https://megga-agents.api-963.workers.dev"})
    assert p.accord is True and p.url == "https://megga-agents.api-963.workers.dev"
    sortie = []
    assert commande(["cle"], {"PILOTE_CLE_FILE": str(tmp_path / "cle")}, sortie.append) == 0
    assert sortie == [CLE_PUBLIQUE_INSTALLATION]  # la clé publique, à remettre à MEGGA ; jamais la privée
    assert commande(["inconnue"], {}, sortie.append) == 2


def test_un_releve_en_echec_n_arrete_pas_le_pilote(canal, monkeypatch, tmp_path):
    from pilote import sonde

    monkeypatch.setattr(sonde, "VIVANT", tmp_path / "vivant")  # pas le /tmp de la machine
    assert commande(["vivant"], {}, print) == 1
    c = canal
    p = c.pilote(PILOTAGE_INTERVALLE="1")
    p.transport = httpx.MockTransport(lambda r: httpx.Response(502, text="porte en panne"))

    async def deux_tours():
        arret = asyncio.Event()
        tache = asyncio.create_task(p.tourner(arret))
        await asyncio.sleep(1.5)
        arret.set()
        await tache

    asyncio.run(deux_tours())
    assert commande(["vivant"], {}, print) == 0


# Les fichiers d'installation


def test_compose_le_pilote_sans_les_secrets_de_l_agent():
    c = yaml.safe_load(open("installation/compose/docker-compose.yml"))
    p = c["services"]["pilote"]
    assert p["image"] == c["services"]["agent"]["image"] and p["environment"]["MEGGA_SERVICE"] == "pilote"
    assert "ports" not in p and "expose" not in p  # toujours sortant
    assert p["env_file"] == [{"path": "pilote.env", "required": False}]  # pas secrets.env : ni modèles ni Meta
    assert p["environment"]["PILOTAGE"] == "${PILOTAGE:-non}"
    assert p["volumes"][0]["read_only"] is True
    assert "suivi" in open("installation/compose/exemple.env").read()


def test_helm_le_pilote_a_ses_propres_etiquettes():
    gabarit = open("installation/helm/megga-agent/templates/pilote.yaml").read()
    assert "megga-agent.etiquettes-pilote" in gabarit and "kind: Service" not in gabarit
    assert "key: PILOTE_CLE" in gabarit and "envFrom" not in gabarit  # seulement sa clé et la base
    aides = open("installation/helm/megga-agent/templates/_helpers.tpl").read()
    assert "app.kubernetes.io/name: megga-pilote" in aides


# Corrections de la relecture


def releve_signe(c, corps: dict | bytes, cle=CLE_INSTALLATION, client="exemple", en_tete=None):
    brut = corps if isinstance(corps, bytes) else json.dumps(corps).encode()
    h = pilotage.entetes(client, cle, "POST", "/pilotage/releve", brut)
    if en_tete:
        h["x-megga-installation"] = en_tete
    return c.t.post("/pilotage/releve", content=brut, headers={**h, "content-type": "application/json"})


def test_un_releve_mal_forme_est_refuse_sans_rien_casser(canal):
    c = canal
    activer(c.t, 1)
    for mauvais in (b'{"pilotage":"suivi","etat":{"agent":{"ok":NaN}}}', b'{"pilotage":"suivi","etat":{"x":Infinity}}',
                    json.dumps({"pilotage": "suivi", "etat": {"x": 10 ** 400}}).encode(),
                    json.dumps({"pilotage": "suivi", "suivi": {"fenetres": {}, "alertes": 5}}).encode(),
                    json.dumps({"pilotage": "suivi", "etat": {"agent": "panne"}}).encode()):
        r = releve_signe(c, mauvais)
        assert r.status_code == 401 and r.json()["erreur"].startswith("relevé"), r.text
    # rien n'a été gardé : les listes de MEGGA répondent
    for chemin in ("/atelier/clients", "/atelier/installations", "/atelier/clients/exemple", "/atelier/clients/exemple/alertes"):
        assert c.t.get(chemin, headers=MEGGA).status_code == 200


def test_la_signature_couvre_l_installation_et_une_cle_ne_sert_qu_une_fois(canal):
    c = canal
    c.t.post("/atelier/clients", headers=MEGGA, json={"config": {**conf_client(id="autre"), "whatsapp": {"numero_id": "100000000000002"}}})
    r = c.t.put("/atelier/clients/autre/installation", headers=MEGGA, json={"cle_publique": CLE_PUBLIQUE_INSTALLATION})
    assert r.status_code == 400 and "autre installation" in r.json()["erreur"]
    # signée pour « exemple », présentée comme « autre » : refusée
    _, texte = cle_jetable()
    c.t.put("/atelier/clients/autre/installation", headers=MEGGA,
            json={"cle_publique": pilotage.en_texte(pilotage.cle_privee(texte).public_key())})
    assert releve_signe(c, {"pilotage": "suivi"}, en_tete="autre").status_code == 401


def test_l_ecart_est_inconnu_quand_l_agent_ne_repond_pas(canal):
    c = canal
    activer(c.t, 1)
    p = c.pilote()
    c.tour(p)
    p.transport_agent = httpx.ASGITransport(app=c.relancer_agent())
    c.tour(p)
    c.tour(p)
    assert c.ordres() == {1: "applique"}
    p.transport_agent = httpx.MockTransport(lambda r: httpx.Response(503, text="redémarre"))
    c.tour(p)
    assert c.t.get("/atelier/clients/exemple", headers=MEGGA).json()["ecart"] is None
    r = activer(c.t, 1)  # pas de doublon pendant qu'il redémarre
    assert r.status_code == 409 and "prochain relevé" in r.json()["erreur"]


def test_les_ordres_expirent_meme_sous_suivi(tmp_path):
    from atelier.pilotage import Pilotage

    h = Horloge()
    canal_ = Pilotage(f"sqlite:///{tmp_path}/a.db", CLE_PILOTAGE, horloge=h)
    canal_.deposer("exemple", "config", {"version": 1, "config": pilotage.config_a_envoyer(BASE)}, "megga")
    assert canal_.en_cours("exemple", 1) == 1
    h.t += pilotage.DUREE_ORDRE + 1
    assert canal_.en_cours("exemple", 1) is None  # expiré sans relevé « complet » : la version peut repartir
    assert canal_.ordres.lire("exemple", 1)["etat"] == "expire"
    assert "ordre_expire" in [a["genre"] for a in canal_.alertes("exemple", 0, 1)]


def test_une_configuration_part_sans_ses_valeurs_par_defaut():
    envoyee = pilotage.config_a_envoyer(BASE)
    assert envoyee["version"] == 1 and "reactions" not in envoyee and "voix" not in envoyee
    # une installation dont la configuration ne connaît pas encore un réglage facultatif l'accepte quand même
    o = pilotage.ordre("exemple", 1, "config", {"version": 2, "config": envoyee}, CLE_PILOTAGE, time.time())
    assert pilotage.config_de(pilotage.lire_ordre(o, BASE, PUB), BASE)[1] == BASE


def test_sous_pilotage_non_l_agent_sert_son_fichier(tmp_path):
    url = base_client(tmp_path)
    stockage.Ordres(url).ajouter("exemple", 1, "config", ordre_config(nom_agent="Lea"), "applique", "", 1, 2)
    assert agent_client(url).state.config.nom_agent == "Lea"
    app = agent_client(url, pilotage_mode="non")
    assert app.state.config.nom_agent == "Alix" and TestClient(app).get("/sante").json()["configuration"] == {"source": "fichier"}
    sortie = []
    env = {"CLIENT_CONFIG": CONF_CLIENT, "DATABASE_URL": url, "PILOTAGE": "non"}
    assert commande(["accepter", "1"], env, sortie.append) == 1 and "PILOTAGE" in sortie[-1]


def test_la_licence_est_verifiee_avant_la_base(tmp_path):
    from noyau import licence as licences

    url = f"sqlite:///{tmp_path}/jamais.db"
    with pytest.raises(licences.LicenceRefusee):
        creer_agent({"CLIENT_CONFIG": CONF_CLIENT, "MEGGA_INSTALLATION": "client", "MEGGA_LICENCE": "", "DATABASE_URL": url},
                    cle_licence=CLE_LICENCE.public_key())
    assert not (tmp_path / "jamais.db").exists()


def test_base_en_panne_ou_ordre_illisible_n_arretent_pas_le_releve(canal):
    c = canal
    p = c.pilote()
    vus = []

    class Note(httpx.AsyncBaseTransport):
        async def handle_async_request(self, requete):
            vus.append(json.loads(requete.content))
            return await httpx.ASGITransport(app=c.atelier).handle_async_request(requete)

    p.transport = Note()
    p.installation.prete = lambda: (_ for _ in ()).throw(RuntimeError("base injoignable"))
    c.tour(p)
    assert vus[-1]["etat"]["base"] is False and vus[-1]["etat"]["base_erreur"] == "RuntimeError"
    assert vus[-1]["etat"]["agent"]["ok"] is True  # MEGGA voit au moins l'agent
    # un ordre d'un genre inconnu de cette image est refusé, et le suivant passe quand même
    del p.installation.prete
    inconnu = pilotage.signer({"format": 1, "client": "exemple", "numero": 1, "genre": "mise_a_jour_lointaine", "cree": 1,
                               "expire": 2 ** 40, "contenu": {}}, CLE_PILOTAGE)

    class Deux(httpx.AsyncBaseTransport):
        async def handle_async_request(self, requete):
            await httpx.ASGITransport(app=c.atelier).handle_async_request(requete)
            return httpx.Response(200, json={"ordres": [inconnu, ordre_config(numero=2, nom_agent="Lea")]})

    p.transport = Deux()
    c.tour(p)
    o = p.installation.ordres
    assert (o.lire("exemple", 1)["etat"], o.lire("exemple", 1)["genre"]) == ("refuse", "inconnu")
    assert o.lire("exemple", 2)["etat"] == "a_appliquer"


def test_un_ordre_applique_que_l_agent_refuse_passe_en_echec(canal):
    c = canal
    url = c.url
    stockage.Ordres(url).ajouter("exemple", 1, "config", ordre_config(nom_agent="Lea"), "applique", "", 1, 2)
    autre_image = Installation(url, BASE, AUTRE_CLE.public_key())  # une image qui ne connaît pas cette clé
    autre_image.suivre_application({"ok": True, "configuration": {"source": "fichier"}})
    assert autre_image.ordres.lire("exemple", 1)["etat"] == "echec"
    assert "refusé par l'agent" in autre_image.journal.lire("exemple")[0]["detail"]
