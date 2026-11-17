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


@pytest.fixture(autouse=True)
def dns_public(monkeypatch):
    """Les webhooks des essais (crm.exemple.ch) résolvent vers une adresse publique, sans réseau."""
    async def adresses(hote):
        return ["127.0.0.1"] if hote in ("localhost", "127.0.0.1") else ["93.184.215.14"]

    monkeypatch.setattr(connecteurs, "adresses", adresses, raising=False)


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
    for mauvais in ({"leads": {"webhook": "http://crm.ch"}}, {"mcp": [{"nom": "crm", "url": "https://a.ch/mcp", "outils": ["a"]},
                                                                      {"nom": "crm", "url": "https://b.ch/mcp", "outils": ["a"]}]},
                    {"mcp": [{"nom": "crm", "url": "https://a.ch/mcp"}]},  # sans la liste de ses outils : refusé
                    {"mcp": [{"nom": "crm", "url": "https://a.ch/mcp", "outils": []}]},
                    {"mcp": [{"nom": "crm", "url": "https://a.ch/mcp", "jeton": 6}]}, {"mcp": [{"nom": "CRM", "url": "https://a.ch/mcp"}]},
                    {"mcp": [{"nom": "crm", "url": "https://a.ch/mcp", "outils": ["Creer Contact"]}]}):
        with pytest.raises(Exception):
            configuration.lire({**CONF, **mauvais})


def test_les_outils_mcp_attendent_l_accord_par_defaut():
    serveur = {"nom": "crm", "url": "https://mcp.crm.ch/mcp", "outils": ["creer_contact", "lister_contacts"]}
    c = configuration.lire({**CONF, "outils": ["connecteurs"], "mcp": [serveur], "approbations": {"crm_lister_contacts": "auto"}})
    assert approbations.regles_pour(c) == {"crm_creer_contact": "approbation", "crm_lister_contacts": "auto"}
    assert connecteurs.CONSIGNE_CONNECTEURS in consignes(c)  # ce qu'un serveur rend est une donnée


# Les leads


def test_un_lead_part_au_webhook_signe(url):
    recus, transport = recepteur([200])
    l = connecteurs.Leads(stockage.Leads(url), "https://crm.exemple.ch/leads", "secret-du-client", "exemple", "Alix", transport)
    [outil] = l.outils()

    async def essai():
        r = await outil("Un 4 pièces à Nyon, à acheter", 4, Contexte("+41790000001"), budget="1,5 M CHF", nom="Mme Dupont")
        await fini(l)
        return r

    assert asyncio.run(essai()) == "Demande 1 enregistrée ; l'envoi au logiciel de l'équipe est en cours."
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
    assert asyncio.run(outil("Une villa", 5, Contexte("+41790000001"))) == "Demande 1 enregistrée pour l'équipe."
    assert "score" in asyncio.run(outil("Une villa", 9, Contexte("+41790000001")))
    assert "besoin" in asyncio.run(outil("  ", 3, Contexte("+41790000001")))
    assert stockage.Leads(url).lister()[0]["etat"] == "garde"


def test_un_lead_se_complete_au_lieu_de_se_doubler(url):
    recus, transport = recepteur([200])
    l = connecteurs.Leads(stockage.Leads(url), "https://crm.exemple.ch/leads", transport=transport)
    outil = l.outils()[0]

    async def essai():
        await outil("Un 4 pièces à Nyon", 3, Contexte("+41790000001"))
        r = await outil("Un 4 pièces à Nyon", 4, Contexte("+41790000001"), budget="1,5 M CHF", lead=1)
        autre = await outil("Une villa", 5, Contexte("+41790000002"), lead=1)  # pas le lead d'une autre personne
        await fini(l)
        return r, autre

    r, autre = asyncio.run(essai())
    assert r == "Demande 1 complétée ; l'envoi au logiciel de l'équipe est en cours." and "introuvable" in autre
    [lead] = stockage.Leads(url).lister()
    assert (lead["score"], lead["budget"], lead["besoin"]) == (4, "1,5 M CHF", "Un 4 pièces à Nyon")
    assert [json.loads(x.content)["lead"]["id"] for x in recus] == [1, 1]  # le même id : le CRM met sa fiche à jour
    assert json.loads(recus[1].content)["lead"]["budget"] == "1,5 M CHF"


def test_un_webhook_vers_une_adresse_privee_est_refuse(url):
    recus, transport = recepteur([200])
    l = connecteurs.Leads(stockage.Leads(url), "https://localhost/leads", transport=transport)

    async def essai():
        await l.outils()[0]("Une villa", 5, Contexte("+41790000001"))
        return await l.vider(5)

    assert asyncio.run(essai()) == 0  # l'envoi attendu (à l'arrêt de l'agent aussi)
    [lead] = stockage.Leads(url).lister()
    assert recus == [] and (lead["etat"], lead["erreur"]) == ("echec", "adresse privée")


def test_les_leads_de_plus_d_un_an_s_effacent(url):
    magasin = stockage.Leads(url)
    vieux = magasin.noter("+41790000001", {"besoin": "Une villa", "score": 3})
    with magasin._e.begin() as c:
        c.execute(magasin._t.update().where(magasin._t.c.id == vieux).values(cree=time.time() - 400 * 86400))
    magasin.noter("+41790000002", {"besoin": "Un studio", "score": 2})
    assert [x["besoin"] for x in magasin.lister()] == ["Un studio"]


# Les connecteurs MCP


def test_un_serveur_sans_son_jeton_est_laisse_de_cote():
    c = configuration.lire({**CONF, "mcp": [{"nom": "crm", "url": "https://mcp.crm.ch/mcp", "outils": ["creer_contact"], "jeton": 2},
                                            {"nom": "agenda", "url": "https://mcp.agenda.ch/mcp", "outils": ["creneaux"]}]})
    boites = connecteurs.outils_mcp(c.mcp, {})
    assert len(boites) == 1 and boites[0].tool_name_prefix == "agenda"
    [crm, agenda] = connecteurs.outils_mcp(c.mcp, {"MCP_JETON_2": "jeton-crm"})
    assert crm.server_params.headers == {"Authorization": "Bearer jeton-crm"} and crm.include_tools == ["creer_contact"]
    assert agenda.include_tools == ["creneaux"]


def test_un_serveur_en_panne_est_mis_de_cote():
    serveur = configuration.ServeurMcp.model_construct(nom="crm", url=f"http://127.0.0.1:{port_libre()}/mcp", outils=("a",), jeton=None)
    [boite] = connecteurs.outils_mcp([serveur], {})

    async def essai():
        debut = time.monotonic()
        with pytest.raises(Exception):
            await boite.build_tools()
        premier = time.monotonic() - debut
        debut = time.monotonic()
        with pytest.raises(Exception):
            await boite.build_tools()  # mis de côté : pas de nouvel essai avant quelques minutes
        return premier, time.monotonic() - debut

    premier, second = asyncio.run(essai())
    assert premier < connecteurs.DELAI_CONNEXION + 1 and second < 0.05 and connecteurs.DELAI_CONNEXION <= 3


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
    async def creer_contact(nom: str, telephone: str) -> str:
        """Crée un contact dans le CRM."""
        await asyncio.sleep({"M. Lent": 1.5, "Mme Vite": 0.5}.get(nom, 0))
        crees.append((nom, telephone))
        return f"contact {nom} créé"

    @serveur.tool()
    def supprimer_tout() -> str:
        """Supprime tous les contacts."""
        crees.clear()
        return "tout est supprimé"

    @serveur.tool()
    def echouer() -> str:
        """Une action que le CRM refuse."""
        raise ValueError("le CRM est plein")

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
    serveur = configuration.ServeurMcp.model_construct(nom="crm", url=adresse, outils=("creer_contact", "echouer"), jeton=None)

    async def tour(regles, outil="crm_creer_contact", arguments=None):
        g = approbations.Gardien(stockage.Audit(url), stockage.Approbations(url))
        [boite] = connecteurs.outils_mcp([serveur], {})
        # Le serveur est celui de la configuration : ses outils attendent l'accord de l'équipe, sauf « auto »
        conf = configuration.lire({**CONF, "approbations": regles}).model_copy(update={"mcp": (serveur,)})
        modele = ModeleOutil(outil=outil, arguments={"nom": "Mme Dupont", "telephone": "+41790000001"} if arguments is None else arguments)
        agent = construire(conf, None, {}, principal=modele, outils=[boite], gardien=g)
        sortie = await agent.arun("Ajoute Mme Dupont au CRM", user_id="+41790000001", session_id="+41790000001")
        noms = sorted((boite.functions or {}).keys())
        issue = None
        if regles.get(outil) != "auto":
            [d] = stockage.Approbations(url).lister("attente")
            issue = await g.decider(d["id"], True, "+41790000099")
        assert boite.session is None  # aucune session gardée hors d'un appel : ni après le tour, ni après l'accord
        await g.vider(5)
        return sortie, noms, issue, modele

    sortie, noms, _, _ = asyncio.run(tour({"crm_creer_contact": "auto"}))
    assert noms == ["crm_creer_contact", "crm_echouer"]  # seuls les outils nommés sont proposés, préfixés
    assert crees == [("Mme Dupont", "+41790000001")] and "contact Mme Dupont créé" in sortie.content
    assert '<donnees_mcp serveur="crm">' in sortie.content  # ce que rend le serveur est balisé comme une donnée
    crees.clear()
    _, _, issue, modele = asyncio.run(tour({}))
    assert "attend l'accord" in modele.vus[0]  # pas fait avant l'accord…
    assert issue["etat"] == "faite" and crees == [("Mme Dupont", "+41790000001")]  # …puis fait par l'équipe
    _, _, issue, _ = asyncio.run(tour({}, "crm_echouer", {}))
    assert issue["etat"] == "echec" and "echouer" in issue["resultat"]  # une erreur du serveur n'est pas « faite »


def test_deux_tours_simultanes_sur_le_meme_serveur(url, serveur_mcp):
    """Deux personnes, deux agents, un serveur : le tour qui finit le premier ne coupe pas celui de l'autre, commencé après."""
    from test_lot9_1 import ModeleOutil

    adresse, crees = serveur_mcp
    serveur = configuration.ServeurMcp.model_construct(nom="crm", url=adresse, outils=("creer_contact",), jeton=None)
    [boite] = connecteurs.outils_mcp([serveur], {})
    conf = configuration.lire(CONF)

    def agent(nom):
        modele = ModeleOutil(outil="crm_creer_contact", arguments={"nom": nom, "telephone": "+41790000001"})
        return construire(conf, None, {}, principal=modele, outils=[boite], gardien=approbations.Gardien())

    async def essai():
        rapide, lent = agent("Mme Vite"), agent("M. Lent")

        async def plus_tard():
            await asyncio.sleep(0.2)
            return await lent.arun("Ajoute M. Lent", user_id="+41790000003", session_id="+41790000003")

        sorties = await asyncio.gather(plus_tard(), rapide.arun("Ajoute Mme Vite", user_id="+41790000002", session_id="+41790000002"))
        return [s.content for s in sorties]

    sorties = asyncio.run(essai())
    assert "contact M. Lent créé" in sorties[0] and "contact Mme Vite créé" in sorties[1], sorties
    assert sorted(crees) == [("M. Lent", "+41790000001"), ("Mme Vite", "+41790000001")] and boite.session is None


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
