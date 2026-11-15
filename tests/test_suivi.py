"""Lot 5, suivi : volumes, modèles, conversations, alertes et coûts d'un agent."""

import asyncio
import json
import time
from dataclasses import dataclass

import pytest
from agno.metrics import MessageMetrics
from agno.models.response import ModelResponse
from fastapi.testclient import TestClient

from atelier.app import creer as creer_atelier
from atelier.couts import Tarifs, couts
from noyau import stockage
from noyau.agent import construire
from noyau.app import creer as creer_agent
from noyau.config import lire
from noyau.tour import Conversations
from test_app import CONF, FauxExpediteur, corps, signe
from test_lot5 import ADMIN, MEGGA, FaussePorte, FauxModele, jeton_client, nouveau_client

INTERNE = {"x-megga-interne": "jeton"}
MOI = "+41790000000"


@dataclass
class ModeleCompte(FauxModele):
    """Un faux modèle qui rend aussi ses jetons, comme le ferait Claude."""

    def _repondre(self, messages):
        r = super()._repondre(messages)
        r.response_usage = MessageMetrics(input_tokens=1000, output_tokens=200, total_tokens=1200, cache_read_tokens=500)
        return r


@dataclass
class ModeleEnPanne(FauxModele):
    def _repondre(self, messages):
        from agno.exceptions import ModelProviderError

        raise ModelProviderError("panne", status_code=500, model_name=self.id, model_id=self.id)


def agent_et_base(tmp_path, principal=None, secours=None):
    url = f"sqlite:///{tmp_path}/client.db"
    conf = lire("clients/exemple.yaml")
    agent = construire(conf, stockage.base_agno(url), {"ANTHROPIC_API_KEY": "x", "DEEPSEEK_API_KEY": "y"},
                       principal=principal or ModeleCompte(id="claude-sonnet-5-5", provider="Anthropic"), secours=secours)
    return agent, url


def serveur(tmp_path, **k):
    agent, url = agent_et_base(tmp_path, **k)
    exp = FauxExpediteur()
    app = creer_agent({"CLIENT_CONFIG": CONF, "META_APP_SECRET": "secret-essai", "INTERNE_TOKEN": "jeton", "DATABASE_URL": url},
                      agent=agent, expediteur=exp, attente=0.01, seuil_regard=30)
    return app, url


def ecrire(t, app, texte, ident):
    c = corps(texte, ident)
    t.post("/whatsapp", content=c, headers=signe(c))

    async def tout():
        while app.state.taches:
            await asyncio.gather(*list(app.state.taches), return_exceptions=True)

    t.portal.call(tout)


# Dans le conteneur du client


def test_suivi_d_apres_les_vrais_tours(tmp_path):
    app, url = serveur(tmp_path)
    avant = time.time() - 5
    with TestClient(app) as t:
        assert t.get("/interne/suivi").status_code == 401
        assert t.get("/interne/suivi", headers={"x-megga-interne": "faux"}).status_code == 401
        ecrire(t, app, "Bonjour", "w1")
        ecrire(t, app, "Ma clé est sk-ant-api03-abcdefghijklmnopqrstuv", "w2")
        s = t.get(f"/interne/suivi?depuis={int(avant)}", headers=INTERNE).json()
        assert s["tours"] == 2 and s["personnes"] == 1 and s["tours_en_echec"] == 0 and s["secours"] == 0
        m = s["modeles"]["claude-sonnet-5-5"]
        assert (m["tours"], m["entree"], m["sortie"], m["cache_lecture"]) == (2, 2000, 400, 1000)
        assert t.get(f"/interne/suivi?depuis={int(time.time()) + 60}", headers=INTERNE).json()["tours"] == 0

        conv = t.get("/interne/suivi/conversations", headers=INTERNE).json()["conversations"]
        assert [(c["personne"], c["echanges"]) for c in conv] == [(MOI, 2)]
        e = t.get(f"/interne/suivi/conversations/{MOI}", headers=INTERNE).json()["echanges"]
        assert [x["entendu"] for x in e][0] == "Bonjour"
        assert "sk-ant" not in json.dumps(e)  # ni clé ni jeton dans la console, même dits par la personne
        assert e[0]["reponse"] == "Bonjour, ici votre agent d'essai."
        assert t.get("/interne/suivi/conversations/abc", headers=INTERNE).status_code == 400
        assert len(t.get(f"/interne/suivi/conversations/{MOI}?limite=1", headers=INTERNE).json()["echanges"]) == 1


def test_le_secours_est_compte(tmp_path):
    app, _ = serveur(tmp_path, principal=ModeleEnPanne(id="claude-sonnet-5-5", provider="Anthropic"),
                     secours=ModeleCompte(id="deepseek-v4-pro", provider="DeepSeek"))
    with TestClient(app) as t:
        ecrire(t, app, "Bonjour", "w1")
        s = t.get("/interne/suivi", headers=INTERNE).json()
        assert s["tours"] == 1 and s["secours"] == 1
        assert s["modeles"]["deepseek-v4-pro"]["sortie"] == 200


def test_sans_base_le_suivi_est_indisponible():
    from test_app import FauxAgent

    app = creer_agent({"CLIENT_CONFIG": CONF, "META_APP_SECRET": "s", "INTERNE_TOKEN": "jeton"}, agent=FauxAgent(), expediteur=FauxExpediteur())
    assert TestClient(app).get("/interne/suivi", headers=INTERNE).status_code == 503


def test_le_journal_garde_les_echecs_sans_texte(tmp_path):
    url = f"sqlite:///{tmp_path}/j.db"
    j = stockage.Journal(url)

    class AgentEnPanne:
        async def arun(self, *a, **k):
            raise RuntimeError("Claude et DeepSeek injoignables")

    class ExpEnPanne(FauxExpediteur):
        async def texte(self, vers, texte):
            raise ConnectionError("Meta injoignable")

    from noyau.whatsapp import Entrant

    c = Conversations(lire("clients/exemple.yaml"), AgentEnPanne(), ExpEnPanne(), attente=0.01, journal=j)
    asyncio.run(c._tour(MOI, [Entrant(id="w1", de=MOI, texte="Mon secret", envoye=time.time(), genre="text")]))
    j.noter("voix_caracteres", 120)
    j.noter("voix_caracteres", 80)
    totaux = j.totaux(0)
    assert totaux["tour_echec"]["nombre"] == 1 and totaux["envoi_echec"]["nombre"] == 1
    assert totaux["voix_caracteres"] == {"nombre": 2, "quantite": 200.0}
    alertes = j.alertes(0)
    assert {a["genre"] for a in alertes} == {"tour_echec", "envoi_echec"}
    assert "secret" not in json.dumps(alertes) and MOI not in json.dumps(alertes)
    assert j.alertes(time.time() + 60) == []


def test_un_journal_en_panne_ne_casse_pas_le_tour(tmp_path):
    from test_app import FauxAgent
    from noyau.whatsapp import Entrant

    class JournalEnPanne:
        def noter(self, *a, **k):
            raise RuntimeError("base perdue")

    class ExpEnPanne(FauxExpediteur):
        async def texte(self, vers, texte):
            raise ConnectionError("Meta injoignable")

    c = Conversations(lire("clients/exemple.yaml"), FauxAgent(), ExpEnPanne(), attente=0.01, journal=JournalEnPanne())
    asyncio.run(c._tour(MOI, [Entrant(id="w1", de=MOI, texte="Bonjour", envoye=time.time(), genre="text")]))


# Les coûts


def test_couts():
    activite = {
        "modeles": {"claude-sonnet-5-5": {"entree": 2_000_000, "sortie": 100_000, "cache_lecture": 1_000_000, "cache_ecriture": 0},
                    "deepseek-v4-pro": {"entree": 10, "sortie": 5}},
        "journal": {"voix_caracteres": {"nombre": 3, "quantite": 4000}, "vocal_entendu": {"nombre": 2, "quantite": 2}},
    }
    t = Tarifs.model_validate({"modeles": {"claude-sonnet-5-5": {"entree": 3, "sortie": 15, "cache_lecture": 0.3}},
                               "voix_par_1000_caracteres": 0.5})
    c = couts(activite, t)
    assert c["postes"] == {"claude-sonnet-5-5": 7.8, "voix": 2.0}
    assert c["total"] == 9.8 and c["devise"] == "USD"
    assert c["sans_tarif"] == ["deepseek-v4-pro", "ecoute"]  # rien n'est inventé
    assert couts({}, Tarifs())["total"] == 0


# L'atelier


class PorteSuivie(FaussePorte):
    """Une porte qui rend aussi le suivi d'un conteneur."""

    def __init__(self, panne=None, **k):
        super().__init__(**k)
        self.suivis = []
        self.panne = panne

    async def suivi(self, ident, chemin="", **params):
        from atelier.porte import PorteErreur

        self.suivis.append((ident, chemin, params))
        if chemin == "/alertes" and self.panne:
            raise PorteErreur(*self.panne)
        if chemin == "/alertes":
            return {"alertes": [{"quand": time.time() - 60, "genre": "tour_echec", "detail": "RuntimeError"}]}
        if chemin.startswith("/conversations/"):
            return {"personne": chemin.split("/")[-1], "echanges": [{"quand": 1, "entendu": "Bonjour", "reponse": "Bonjour !"}]}
        if chemin == "/conversations":
            return {"conversations": [{"personne": MOI, "echanges": 3, "derniere": 1}]}
        return {"tours": 3, "modeles": {"claude-sonnet-5-5": {"entree": 1_000_000, "sortie": 0}}, "journal": {}}

    async def etats(self, ident=None):
        e = await super().etats(ident)
        for v in e.values():
            v["conteneur"] = {"demarre": False, "alerte": {"quand": time.time() * 1000, "quoi": "demarrage", "message": "secret manquant"}}
        return e


@pytest.fixture
def atelier(tmp_path):
    porte = PorteSuivie()
    t = TestClient(creer_atelier({"ADMIN_TOKEN": ADMIN, "DATABASE_URL": f"sqlite:///{tmp_path}/a.db"}, porte=porte))
    t.porte = porte
    nouveau_client(t)
    t.post("/atelier/clients/exemple/versions/1/activer", headers=MEGGA, json={"forcer": True})
    return t


def test_suivi_et_couts_pour_megga(atelier):
    t = atelier
    assert t.put("/atelier/tarifs", headers=MEGGA, json={"modeles": {"claude-sonnet-5-5": {"entree": 3, "sortie": 15}}}).status_code == 200
    s = t.get("/atelier/clients/exemple/suivi?jours=30", headers=MEGGA).json()
    assert s["periode_jours"] == 30 and s["activite"]["tours"] == 3 and s["version_en_service"] == 1
    assert s["couts"]["postes"] == {"claude-sonnet-5-5": 3.0}
    ident, chemin, params = t.porte.suivis[-1]
    assert (ident, chemin) == ("exemple", "") and abs(params["depuis"] - (time.time() - 30 * 86400)) < 5


def test_le_client_voit_son_activite_mais_pas_les_couts(atelier):
    t = atelier
    client = jeton_client(t)
    s = t.get("/atelier/clients/exemple/suivi", headers=client).json()
    assert s["activite"]["tours"] == 3 and "couts" not in s
    for methode, route in (("get", "/atelier/tarifs"), ("put", "/atelier/tarifs")):
        assert getattr(t, methode)(route, headers=client, **({"json": {}} if methode == "put" else {})).status_code == 403
    conv = t.get("/atelier/clients/exemple/conversations", headers=client).json()
    assert conv["conversations"][0]["personne"] == MOI
    e = t.get(f"/atelier/clients/exemple/conversations/{MOI}?limite=5", headers=client).json()
    assert e["echanges"][0]["entendu"] == "Bonjour"
    assert t.porte.suivis[-1] == ("exemple", f"/conversations/{MOI}", {"limite": 5})


def test_entrees_du_suivi(atelier):
    t = atelier
    for q in ("jours=0", "jours=400", "jours=abc"):
        assert t.get(f"/atelier/clients/exemple/suivi?{q}", headers=MEGGA).status_code == 400
    assert t.get("/atelier/clients/exemple/conversations?limite=500", headers=MEGGA).status_code == 400
    assert t.get("/atelier/clients/exemple/conversations/abc", headers=MEGGA).status_code == 400
    assert t.put("/atelier/tarifs", headers=MEGGA, json={"modeles": {"x": {"entree": -1, "sortie": 1}}}).status_code == 422
    assert t.put("/atelier/tarifs", headers=MEGGA, json={"devise": "dollars"}).status_code == 422
    assert t.get("/atelier/clients/autre/suivi", headers=MEGGA).status_code == 404


def test_alertes_rassemblees(atelier):
    t = atelier
    t.porte.activations.append(("exemple", 9, {}))  # l'annuaire sert une autre version que l'atelier
    a = t.get("/atelier/clients/exemple/alertes", headers=MEGGA).json()["alertes"]
    genres = [x["genre"] for x in a]
    assert set(genres) == {"ecart", "conteneur_demarrage", "tour_echec"}
    assert a == sorted(a, key=lambda x: x["quand"], reverse=True)
    t.porte.panne = (0, "sans réponse")
    genres = [x["genre"] for x in t.get("/atelier/clients/exemple/alertes", headers=MEGGA).json()["alertes"]]
    assert "conteneur_injoignable" in genres


def test_suivi_hors_porte(tmp_path):
    t = TestClient(creer_atelier({"ADMIN_TOKEN": ADMIN, "DATABASE_URL": f"sqlite:///{tmp_path}/a.db"}, porte=PorteSuivie()))
    nouveau_client(t, zone="suisse")
    assert t.get("/atelier/clients/exemple/suivi", headers=MEGGA).status_code == 409


def test_conteneur_muet(tmp_path):
    class Muette(PorteSuivie):
        async def suivi(self, ident, chemin="", **params):
            from atelier.porte import PorteErreur

            raise PorteErreur(503, '{"erreur":"conteneur injoignable"}')

    t = TestClient(creer_atelier({"ADMIN_TOKEN": ADMIN, "DATABASE_URL": f"sqlite:///{tmp_path}/a.db"}, porte=Muette()))
    nouveau_client(t)
    r = t.get("/atelier/clients/exemple/suivi", headers=MEGGA)
    assert r.status_code == 502 and r.json()["details"]["statut"] == 503


def test_porte_http_suivi():
    import httpx

    from atelier.porte import Porte

    vus = []

    def repondre(r: httpx.Request):
        vus.append(str(r.url))
        return httpx.Response(200, json={"tours": 0})

    p = Porte("https://porte.essai", "jeton", transport=httpx.MockTransport(repondre))
    asyncio.run(p.suivi("exemple", "/conversations", limite=5, depuis=None))
    assert vus == ["https://porte.essai/admin/clients/exemple/suivi/conversations?limite=5"]
