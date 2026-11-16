"""Lot 9.3 : le transfert vers un humain (noyau/reprises.py)."""

import asyncio
import json
import time

import pytest
from fastapi.testclient import TestClient

from noyau import config as configuration, reprises, stockage
from noyau.agent import construire
from noyau.app import creer

CONF = configuration.lire("clients/exemple.yaml").model_dump(mode="json")


@pytest.fixture
def url(tmp_path):
    return f"sqlite:///{tmp_path}/client.db"


class Contexte:
    def __init__(self, user_id):
        self.user_id = user_id


class FaussesConversations:
    def __init__(self):
        self.envois, self.apres, self.fil = [], [], []

    def apres_le_tour(self, personne, f):
        self.apres.append(f)

    async def envoyer_de_soi_meme(self, personne, messages, usage, variables=None, langue="", garder=True):
        self.envois.append((personne, messages, usage))
        return "libre"

    def _noter_fil(self, personne, sens, genre, texte):
        self.fil.append((personne, sens, genre, texte))


def transfert(url, gestionnaires=("+41790000099",)):
    t = reprises.Transfert(stockage.Reprises(url), stockage.Fil(url), gestionnaires, "Alix")
    t.conversations = FaussesConversations()
    return t


class Message:
    def __init__(self, texte, vocal=None, media=None, choix=None):
        self.texte, self.vocal, self.media, self.choix = texte, vocal, media, choix


def outil(t, nom, role=None):
    return next(o for o in t.outils_pour(role) if o.__name__ == nom)


# Le stockage


def test_une_seule_reprise_en_cours_par_personne(url):
    r = stockage.Reprises(url)
    assert r.ouvrir("+41790000001", "visiteur", "réclamation", "résumé") == (1, True)
    assert r.ouvrir("+41790000001", "visiteur", "encore", "x") == (1, False)
    assert r.prendre(1, "+41790000099")["etat"] == "prise"
    assert r.prendre(1, "+41790000098") is None  # une seule fois
    assert r.ecrite(1, "console")["par"] == "+41790000099"  # celui qui l'a prise la garde
    assert r.rendre(1)["etat"] == "rendue" and r.rendre(1) is None
    assert r.en_cours("+41790000001") is None
    assert [x["id"] for x in r.a_relire("+41790000001")] == [1] and r.a_relire("+41790000001") == []


def test_les_reprises_oubliees_reviennent_a_l_agent(url, monkeypatch):
    r = stockage.Reprises(url)
    r.ouvrir("+41790000001", "public", "m", "r")
    r.ouvrir("+41790000002", "public", "m", "r")
    r.prendre(2, "console")
    plus_tard = time.time() + 25 * 3600
    monkeypatch.setattr(stockage.time, "time", lambda: plus_tard)
    assert r.en_cours("+41790000001") is None  # ouverte, personne ne l'a prise en 24 heures
    assert r.en_cours("+41790000002") is not None  # prise : 72 heures
    assert [x["etat"] for x in r.lister()] == ["prise", "expiree"]


# L'outil de l'agent


def test_passer_la_main_previent_l_equipe(url):
    t = transfert(url)
    passer = outil(t, "passer_la_main", "visiteur")
    r = asyncio.run(passer("demande un humain", "Cherche un 4 pièces à Nyon, clé sk-abcdefghijklmnopqrstuvwxyz", Contexte("+41790000001")))
    assert "transmise à l'équipe (n° 1)" in r
    [d] = stockage.Reprises(url).lister()
    assert (d["personne"], d["role"], d["etat"], d["prevenue"]) == ("+41790000001", "visiteur", "ouverte", 1)
    assert "[masqué]" in d["resume"] and "sk-" not in d["resume"]
    # l'équipe est prévenue après le tour, avec « Je la prends »
    assert len(t.conversations.apres) == 1
    asyncio.run(t.conversations.apres[0]())
    [(qui, [message], usage)] = t.conversations.envois
    assert qui == "+41790000099" and usage == "transfert"
    assert [l["id"] for l in message["liste"]["lignes"]] == ["tr:1:prendre", "tr:1:rendre"]
    # une seconde fois : la même, sans prévenir de nouveau
    asyncio.run(passer("encore", "x", Contexte("+41790000001")))
    assert len(t.conversations.apres) == 1


def test_pas_de_transfert_par_api(url):
    t = transfert(url)
    r = asyncio.run(outil(t, "passer_la_main")("humain", "x", Contexte("api:dossier:p1")))
    assert "pas possible" in r and stockage.Reprises(url).lister() == []


def test_les_outils_par_role(url):
    t = transfert(url)
    assert [o.__name__ for o in t.outils_pour("visiteur")] == ["passer_la_main"]
    assert [o.__name__ for o in t.outils_pour("gestionnaire")] == ["conversations_transmises", "repondre_en_reprise", "rendre_la_main"]


# Le tour de la personne, l'équipe


def test_quand_l_equipe_a_la_main_l_agent_se_tait(url):
    t = transfert(url)
    assert asyncio.run(t.garde("+41790000001", [Message("Bonjour")])) is False  # rien en cours : l'agent répond
    asyncio.run(outil(t, "passer_la_main")("humain", "r", Contexte("+41790000001")))
    assert asyncio.run(t.garde("+41790000001", [Message("Vous êtes là ?")])) is True
    assert t.conversations.fil[-1] == ("+41790000001", "recu", "texte", "Vous êtes là ?")
    assert t.conversations.envois == []  # personne ne l'a prise : rien n'est relayé
    # prise par un gestionnaire : ses messages lui arrivent
    assert asyncio.run(t.choix("+41790000001", "visiteur", "tr:1:prendre")) == "Seule l'équipe peut prendre cette conversation."
    assert asyncio.run(t.choix("+41790000099", "gestionnaire", "tr:1:prendre")).startswith("La conversation 1 est à vous")
    assert asyncio.run(t.choix("+41790000098", "gestionnaire", "tr:1:prendre")).startswith("La conversation 1 n'est plus à prendre")
    asyncio.run(t.garde("+41790000001", [Message("Merci")]))
    assert t.conversations.envois[-1] == ("+41790000099", [{"texte": "Message de +41790000001 (conversation 1) : Merci"}], "reprise_message")


def test_l_equipe_repond_puis_rend_la_main(url):
    t = transfert(url)
    asyncio.run(outil(t, "passer_la_main")("réclamation", "r", Contexte("+41790000001")))
    repondre = outil(t, "repondre_en_reprise", "gestionnaire")
    assert asyncio.run(repondre(1, "Bonjour, ici Claire de l'agence.", Contexte("+41790000099"))) == {"id": 1, "envoi": "libre"}
    assert t.conversations.envois[-1] == ("+41790000001", [{"texte": "Bonjour, ici Claire de l'agence."}], "reprise")
    stockage.Fil(url).noter("+41790000001", "envoye", "reprise", "Bonjour, ici Claire de l'agence.", time.time())
    assert stockage.Reprises(url).une(1)["par"] == "+41790000099"
    assert "rendue" in asyncio.run(outil(t, "rendre_la_main", "gestionnaire")(1))
    with pytest.raises(ValueError, match="plus en cours"):
        asyncio.run(repondre(1, "encore", Contexte("+41790000099")))
    contexte = asyncio.run(t.contexte("+41790000001"))
    assert "l'équipe te la rend" in contexte and "Claire de l'agence" in contexte
    assert asyncio.run(t.contexte("+41790000001")) == ""  # dit une fois


# Dans le vrai tour : un webhook WhatsApp


def test_le_webhook_d_une_conversation_reprise_ne_reveille_pas_l_agent(url):
    from test_app import SECRET, FauxAgent, FauxExpediteur, attendre, corps, signe

    agent, exp = FauxAgent(), FauxExpediteur()
    app = creer({"CLIENT_CONFIG": json.dumps({**CONF, "transfert": True}), "DATABASE_URL": url, "META_APP_SECRET": SECRET,
                 "INTERNE_TOKEN": "interne"}, agent=agent, expediteur=exp, attente=0.01, seuil_regard=30)
    stockage.Reprises(url).ouvrir("+41790000000", "public", "humain", "r")
    c = corps("Vous êtes là ?")
    with TestClient(app) as t:
        assert t.post("/whatsapp", content=c, headers=signe(c)).status_code == 200
        t.portal.call(attendre(app))
        assert agent.appels == []  # l'agent ne répond pas : l'équipe a la main
        assert [(m["sens"], m["texte"]) for m in stockage.Fil(url).messages("+41790000000")] == [("recu", "Vous êtes là ?")]
    t = TestClient(app)
    # la console prend, répond, rend
    interne = {"x-megga-interne": "interne"}
    assert t.get("/interne/suivi/reprises", params={"etat": "ouverte"}, headers=interne).json()["reprises"][0]["id"] == 1
    assert t.post("/interne/reprises/1", json={"action": "prendre"}, headers=interne).json() == {"id": 1, "etat": "prise"}
    assert t.post("/interne/reprises/1", json={"action": "message", "texte": ""}, headers=interne).status_code == 400
    assert t.post("/interne/reprises/1", json={"action": "message", "texte": "Ici l'agence."}, headers=interne).json()["id"] == 1
    assert t.post("/interne/reprises/1", json={"action": "rendre"}, headers=interne).json()["etat"] == "rendue"
    assert t.post("/interne/reprises/1", json={"action": "rendre"}, headers=interne).status_code == 409
    assert t.post("/interne/reprises/1", json={"action": "voler"}, headers=interne).status_code == 400


def test_sans_transfert_pas_de_routes(url):
    from test_app import FauxAgent, FauxExpediteur

    app = creer({"CLIENT_CONFIG": json.dumps(CONF), "DATABASE_URL": url, "INTERNE_TOKEN": "interne"},
                agent=FauxAgent(), expediteur=FauxExpediteur())
    assert TestClient(app).get("/interne/suivi/reprises", headers={"x-megga-interne": "interne"}).status_code == 409


def test_la_consigne_va_aux_agents_qui_passent_la_main(url):
    conf = configuration.lire({**CONF, "transfert": True})
    from test_lot9_1 import ModeleOutil

    agent = construire(conf, None, {}, principal=ModeleOutil(), outils=transfert(url).outils_pour(None))
    assert reprises.CONSIGNE in agent.instructions.base if hasattr(agent.instructions, "base") else reprises.CONSIGNE in agent.instructions
    equipe = construire(conf, None, {}, principal=ModeleOutil(), outils=[], nom_role="gestionnaire")
    fixes = equipe.instructions.base if hasattr(equipe.instructions, "base") else equipe.instructions
    assert reprises.CONSIGNE not in fixes


def test_l_atelier_prend_repond_et_rend(tmp_path):
    from atelier.app import creer as creer_atelier
    from test_lot5 import ADMIN, CLE_PILOTAGE_TEXTE, FaussePorte, FauxModele, jeton_client, nouveau_client

    class Porte(FaussePorte):
        def __init__(self):
            super().__init__()
            self.actions, self.lus = [], []

        async def suivi(self, ident, chemin="", **params):
            self.lus.append((chemin, params.get("etat")))
            return {"reprises": []}

        async def reprise(self, ident, numero, corps):
            self.actions.append((numero, corps))
            return {"id": numero, "etat": "prise"}

    porte = Porte()
    t = TestClient(creer_atelier({"ADMIN_TOKEN": ADMIN, "DATABASE_URL": f"sqlite:///{tmp_path}/atelier.db",
                                  "ESSAIS_DIR": str(tmp_path / "essais"), "PILOTAGE_CLE": CLE_PILOTAGE_TEXTE},
                                 porte=porte, principal_essai=FauxModele()))
    nouveau_client(t)
    client = jeton_client(t)
    assert t.get("/atelier/clients/exemple/reprises", params={"etat": "ouverte"}, headers=client).json() == {"reprises": []}
    assert t.get("/atelier/clients/exemple/reprises", params={"etat": "x"}, headers=client).status_code == 400
    assert t.post("/atelier/clients/exemple/reprises/3", json={"action": "prendre"}, headers=client).status_code == 200
    assert t.post("/atelier/clients/exemple/reprises/3", json={"action": "message"}, headers=client).status_code == 400
    t.post("/atelier/clients/exemple/reprises/3", json={"action": "message", "texte": "Bonjour"}, headers=client)
    assert porte.actions == [(3, {"action": "prendre", "texte": ""}), (3, {"action": "message", "texte": "Bonjour"})]
    assert porte.lus == [("/reprises", "ouverte")]
    # le client active lui-même le transfert
    r = t.post("/atelier/clients/exemple/versions", headers=client, json={"changements": {"transfert": True}})
    assert r.status_code == 201 and r.json()["config"]["transfert"] is True
