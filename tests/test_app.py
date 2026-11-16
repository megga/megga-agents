import asyncio
import hashlib
import hmac
import json
import time

from fastapi.testclient import TestClient

from noyau import config as configuration
from noyau import stockage
from noyau.app import Deja, creer

SECRET = "secret-essai"
CONF = json.dumps(configuration.lire("clients/exemple.yaml").model_dump())


class Sortie:
    def __init__(self, content, status="COMPLETED"):
        self.content = content
        self.status = status


class FauxAgent:
    def __init__(self, reponse="Bonjour \u2014 bienvenue", erreur=None, statut="COMPLETED"):
        self.appels = []
        self.reponse = reponse
        self.erreur = erreur
        self.statut = statut

    async def arun(self, texte, user_id=None, session_id=None):
        self.appels.append((texte, user_id, session_id))
        if self.erreur:
            raise self.erreur
        return Sortie(self.reponse, self.statut)


class FauxExpediteur:
    def __init__(self):
        self.envois = []
        self.autres = []

    async def texte(self, vers, texte):
        self.envois.append((vers, texte))

    async def lu(self, message_id):
        self.autres.append(("lu", message_id))

    async def reaction(self, vers, message_id, emoji):
        self.autres.append(("reaction", message_id, emoji))


def corps(texte="Bonjour", ident="wamid.1", numero="100000000000001"):
    return json.dumps({
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"field": "messages", "value": {
            "metadata": {"phone_number_id": numero},
            "messages": [{"from": "41790000000", "id": ident, "type": "text", "timestamp": str(int(time.time())), "text": {"body": texte}}],
        }}]}],
    }).encode()


def signe(c):
    return {"x-hub-signature-256": "sha256=" + hmac.new(SECRET.encode(), c, hashlib.sha256).hexdigest()}


def serveur(agent=None):
    agent = agent or FauxAgent()
    exp = FauxExpediteur()
    app = creer({"CLIENT_CONFIG": CONF, "META_APP_SECRET": SECRET}, agent=agent, expediteur=exp, attente=0.01, seuil_regard=30)
    return app, agent, exp


def attendre(app):
    async def tout():
        while app.state.taches:
            await asyncio.gather(*list(app.state.taches), return_exceptions=True)
    return tout


def test_sante_sans_rien_de_prive():
    app, _, _ = serveur()
    r = TestClient(app).get("/sante")
    from noyau.version import version

    assert r.json() == {"ok": True, "client": "exemple", "zone": "europe", "version": version(), "revision": "inconnue",
                        "config": 1, "schema": stockage.SCHEMA_VERSION, "installation": "megga"}


def test_signature_obligatoire():
    app, agent, _ = serveur()
    c = corps()
    assert TestClient(app).post("/whatsapp", content=c).status_code == 401
    assert TestClient(app).post("/whatsapp", content=c, headers={"x-hub-signature-256": "sha256=" + "0" * 64}).status_code == 401
    assert agent.appels == []


def test_un_message_une_reponse_nettoyee():
    app, agent, exp = serveur()
    with TestClient(app) as t:
        c = corps()
        r = t.post("/whatsapp", content=c, headers=signe(c))
        assert r.text == "reçu 1"
        t.portal.call(attendre(app))
    assert agent.appels == [("Bonjour", "+41790000000", "+41790000000")]
    assert exp.envois == [("+41790000000", "Bonjour, bienvenue")]


def test_doublon_ignore_et_autre_numero_ignore():
    app, agent, _ = serveur()
    with TestClient(app) as t:
        c = corps()
        t.post("/whatsapp", content=c, headers=signe(c))
        r = t.post("/whatsapp", content=c, headers=signe(c))
        assert r.text == "reçu 0"
        autre = corps(numero="999999999", ident="wamid.2")
        assert t.post("/whatsapp", content=autre, headers=signe(autre)).text == "reçu 0"
        t.portal.call(attendre(app))
    assert len(agent.appels) == 1


def test_un_tour_en_echec_ne_casse_rien():
    app, _, exp = serveur(FauxAgent(erreur=RuntimeError("panne")))
    with TestClient(app) as t:
        c = corps()
        assert t.post("/whatsapp", content=c, headers=signe(c)).status_code == 200
        t.portal.call(attendre(app))
        assert t.get("/sante").status_code == 200
    assert len(exp.envois) == 1 and "souci technique" in exp.envois[0][1] and "panne" not in exp.envois[0][1]


def test_deja():
    d = Deja(taille=2)
    assert d.nouveau("a") and not d.nouveau("a")
    d.nouveau("b"), d.nouveau("c")
    assert d.nouveau("a")


def test_erreur_du_modele_jamais_envoyee():
    app, _, exp = serveur(FauxAgent(reponse="Error code: 401 authentication_error", statut="ERROR"))
    with TestClient(app) as t:
        c = corps()
        t.post("/whatsapp", content=c, headers=signe(c))
        t.portal.call(attendre(app))
    assert len(exp.envois) == 1
    assert "401" not in exp.envois[0][1] and "souci technique" in exp.envois[0][1]
