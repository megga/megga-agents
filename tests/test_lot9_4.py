"""Lot 9.4 : les leads et les connecteurs MCP d'un client (noyau/connecteurs.py)."""

import asyncio
import json
import socket
import threading
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from noyau import approbations, config as configuration, connecteurs, stockage
from noyau.agent import construire, consignes
from noyau.app import creer

CONF = configuration.lire("clients/exemple.yaml").model_dump(mode="json")


@pytest.fixture
def url(tmp_path):
    return f"sqlite:///{tmp_path}/client.db"


class Contexte:
    def __init__(self, user_id):
        self.user_id = user_id


def recepteur(statuts):
    """Un faux webhook : il note ce qu'il reçoit et répond les statuts donnés, l'un après l'autre."""
    recus = []

    def repondre(requete):
        recus.append(requete)
        return httpx.Response(statuts[min(len(recus), len(statuts)) - 1])

    return recus, httpx.MockTransport(repondre)


async def fini(l):
    while l._taches:
        await asyncio.gather(*list(l._taches))


# La configuration


def test_la_configuration():
    c = configuration.lire({**CONF, "outils": ["leads", "connecteurs"], "leads": {"webhook": "https://crm.exemple.ch/l"},
                            "mcp": [{"nom": "crm", "url": "https://mcp.crm.ch/mcp", "outils": ["creer_contact"], "jeton": 1}]})
    assert c.mcp[0].jeton == 1 and connecteurs.CONSIGNE_LEADS in consignes(c)
    for mauvais in ({"leads": {"webhook": "http://crm.ch"}}, {"mcp": [{"nom": "crm", "url": "https://a.ch/mcp"}, {"nom": "crm", "url": "https://b.ch/mcp"}]},
                    {"mcp": [{"nom": "crm", "url": "https://a.ch/mcp", "jeton": 6}]}, {"mcp": [{"nom": "CRM", "url": "https://a.ch/mcp"}]},
                    {"mcp": [{"nom": "crm", "url": "https://a.ch/mcp", "outils": ["Creer Contact"]}]}):
        with pytest.raises(Exception):
            configuration.lire({**CONF, **mauvais})


# Les leads


def test_un_lead_part_au_webhook_signe(url):
    recus, transport = recepteur([200])
    l = connecteurs.Leads(stockage.Leads(url), "https://crm.exemple.ch/leads", "secret-du-client", "exemple", "Alix", transport)
    [outil] = l.outils()

    async def essai():
        r = await outil("Un 4 pièces à Nyon, à acheter", 4, Contexte("+41790000001"), budget="1,5 M CHF", nom="Mme Dupont")
        await fini(l)
        return r

    assert asyncio.run(essai()) == "Lead 1 enregistré et transmis à l'équipe commerciale."
    [requete] = recus
    corps = requete.content
    assert requete.headers["x-megga-signature"] == connecteurs.signature("secret-du-client", corps)
    lead = json.loads(corps)["lead"]
    assert (lead["besoin"], lead["score"], lead["budget"], lead["contact"], lead["nom"]) == (
        "Un 4 pièces à Nyon, à acheter", 4, "1,5 M CHF", "+41790000001", "Mme Dupont")
    assert json.loads(corps)["client"] == "exemple"
    assert stockage.Leads(url).lister()[0]["etat"] == "envoye"


def test_un_webhook_en_panne_est_retente_puis_note(url, monkeypatch):
    monkeypatch.setattr(connecteurs, "PAUSE_ENVOI", 0)
    recus, transport = recepteur([500, 503])
    l = connecteurs.Leads(stockage.Leads(url), "https://crm.exemple.ch/leads", transport=transport)

    async def essai():
        await l.outils()[0]("Location à Lausanne", 2, Contexte("+41790000001"))
        await fini(l)

    asyncio.run(essai())
    assert len(recus) == 2 and "x-megga-signature" not in recus[0].headers  # sans secret, pas de signature
    [lead] = stockage.Leads(url).lister()
    assert (lead["etat"], lead["erreur"]) == ("echec", "statut 503")


def test_sans_webhook_et_les_refus(url):
    l = connecteurs.Leads(stockage.Leads(url))
    outil = l.outils()[0]
    assert asyncio.run(outil("Une villa", 5, Contexte("+41790000001"))) == "Lead 1 enregistré pour l'équipe."
    assert "score" in asyncio.run(outil("Une villa", 9, Contexte("+41790000001")))
    assert "besoin" in asyncio.run(outil("  ", 3, Contexte("+41790000001")))
    assert stockage.Leads(url).lister()[0]["etat"] == "garde"


# Les connecteurs MCP


def test_un_serveur_sans_son_jeton_est_laisse_de_cote():
    c = configuration.lire({**CONF, "mcp": [{"nom": "crm", "url": "https://mcp.crm.ch/mcp", "outils": ["creer_contact"], "jeton": 2},
                                            {"nom": "agenda", "url": "https://mcp.agenda.ch/mcp"}]})
    boites = connecteurs.outils_mcp(c.mcp, {})
    assert len(boites) == 1 and boites[0].tool_name_prefix == "agenda"
    [crm, agenda] = connecteurs.outils_mcp(c.mcp, {"MCP_JETON_2": "jeton-crm"})
    assert crm.server_params.headers == {"Authorization": "Bearer jeton-crm"} and crm.include_tools == ["creer_contact"]
    assert agenda.include_tools is None


def port_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def serveur_mcp():
    """Un vrai serveur MCP local (streamable-http), avec deux outils d'un faux CRM."""
    import uvicorn
    from mcp.server.mcpserver import MCPServer

    crees = []
    serveur = MCPServer("crm")

    @serveur.tool()
    def creer_contact(nom: str, telephone: str) -> str:
        """Crée un contact dans le CRM."""
        crees.append((nom, telephone))
        return f"contact {nom} créé"

    @serveur.tool()
    def supprimer_tout() -> str:
        """Supprime tous les contacts."""
        crees.clear()
        return "tout est supprimé"

    port = port_libre()
    u = uvicorn.Server(uvicorn.Config(serveur.streamable_http_app(), host="127.0.0.1", port=port, log_level="error"))
    fil = threading.Thread(target=u.run, daemon=True)
    fil.start()
    for _ in range(100):
        if u.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/mcp", crees
    u.should_exit = True
    fil.join(5)


def test_un_vrai_serveur_mcp_et_les_approbations(url, serveur_mcp):
    from test_lot9_1 import ModeleOutil

    adresse, crees = serveur_mcp
    serveur = configuration.ServeurMcp.model_construct(nom="crm", url=adresse, outils=("creer_contact",), jeton=None)

    async def tour(regles):
        g = approbations.Gardien(stockage.Audit(url), stockage.Approbations(url))
        [boite] = connecteurs.outils_mcp([serveur], {})
        conf = configuration.lire({**CONF, "approbations": regles})
        modele = ModeleOutil(outil="crm_creer_contact", arguments={"nom": "Mme Dupont", "telephone": "+41790000001"})
        agent = construire(conf, None, {}, principal=modele, outils=[boite], gardien=g)
        sortie = await agent.arun("Ajoute Mme Dupont au CRM", user_id="+41790000001", session_id="+41790000001")
        noms = sorted((boite.functions or {}).keys())
        issue = None
        if regles:
            issue = await g.decider(1, True, "+41790000099")
        await boite.close()
        return sortie, noms, issue, modele

    sortie, noms, _, _ = asyncio.run(tour({}))
    assert noms == ["crm_creer_contact"]  # seul l'outil nommé est proposé, préfixé
    assert crees == [("Mme Dupont", "+41790000001")] and "contact Mme Dupont créé" in sortie.content
    crees.clear()
    _, _, issue, modele = asyncio.run(tour({"crm_creer_contact": "approbation"}))
    assert "attend l'accord" in modele.vus[0]  # pas fait avant l'accord…
    assert issue["etat"] == "faite" and crees == [("Mme Dupont", "+41790000001")]  # …puis fait par l'équipe


# Les routes


def test_les_routes(url, tmp_path):
    from test_app import FauxAgent, FauxExpediteur

    l = connecteurs.Leads(stockage.Leads(url))
    app = creer({"CLIENT_CONFIG": json.dumps({**CONF, "outils": ["leads"]}), "DATABASE_URL": url, "INTERNE_TOKEN": "interne"},
                agent=FauxAgent(), expediteur=FauxExpediteur(), leads=l)
    asyncio.run(l.outils()[0]("Une villa", 5, Contexte("+41790000001")))
    lus = TestClient(app).get("/interne/suivi/leads", headers={"x-megga-interne": "interne"}).json()["leads"]
    assert [(x["besoin"], x["score"], x["etat"]) for x in lus] == [("Une villa", 5, "garde")]
    sans = creer({"CLIENT_CONFIG": json.dumps(CONF), "DATABASE_URL": url, "INTERNE_TOKEN": "interne"}, agent=FauxAgent(), expediteur=FauxExpediteur())
    assert TestClient(sans).get("/interne/suivi/leads", headers={"x-megga-interne": "interne"}).status_code == 409

    from atelier.app import creer as creer_atelier
    from test_lot5 import ADMIN, CLE_PILOTAGE_TEXTE, FaussePorte, FauxModele, jeton_client, nouveau_client

    class Porte(FaussePorte):
        async def suivi(self, ident, chemin="", **params):
            return {"leads": [{"id": 1}]} if chemin == "/leads" else {}

    t = TestClient(creer_atelier({"ADMIN_TOKEN": ADMIN, "DATABASE_URL": f"sqlite:///{tmp_path}/atelier.db",
                                  "ESSAIS_DIR": str(tmp_path / "essais"), "PILOTAGE_CLE": CLE_PILOTAGE_TEXTE},
                                 porte=Porte(), principal_essai=FauxModele()))
    nouveau_client(t)
    client = jeton_client(t)
    assert t.get("/atelier/clients/exemple/leads", params={"jours": 30}, headers=client).json() == {"periode_jours": 30, "leads": [{"id": 1}]}
    r = t.post("/atelier/clients/exemple/versions", headers=client, json={"changements": {"leads": {"webhook": "https://crm.exemple.ch/l"}}})
    assert r.status_code == 201 and r.json()["config"]["leads"]["webhook"] == "https://crm.exemple.ch/l"
