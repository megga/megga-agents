"""Lot 6.6 : l'entrée par API. Un logiciel parle à l'agent d'un client et reçoit sa réponse, sans WhatsApp."""

import asyncio
import hashlib
import json
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect

from atelier.app import creer as creer_atelier
from noyau import api, cles, config as configuration, pilotage, stockage, suivi
from noyau.app import creer
from noyau.garde import Debit
from noyau.rappels import outils as outils_rappels
from test_app import FauxAgent, FauxExpediteur, attendre
from test_lot5 import ADMIN, MEGGA, FaussePorte, FauxModele, conf_exemple, jeton_client, nouveau_client

CONF = configuration.lire("clients/exemple.yaml").model_dump(mode="json")
SANS_WHATSAPP = {k: v for k, v in CONF.items() if k != "whatsapp"}


def agent_api(base_url, conf=None, agent=None, **options):
    """L'agent d'un client, sur une vraie base ; rend (client HTTP, agent, expéditeur, base)."""
    agent = agent or FauxAgent("Bonjour, je suis Alix.")
    exp = FauxExpediteur()
    app = creer({"CLIENT_CONFIG": json.dumps(conf or SANS_WHATSAPP), "DATABASE_URL": base_url, "INTERNE_TOKEN": "interne"},
                agent=agent, expediteur=exp, attente=0.01, **options)
    return TestClient(app), agent, exp, app


def nouvelle_cle(url, logiciel="dossier", par_minute=30):
    ident, cle, empreinte = api.nouvelle_cle()
    assert stockage.ClesApi(url).ajouter(ident, logiciel, empreinte, par_minute)
    return ident, {"authorization": f"Bearer {cle}"}


@pytest.fixture
def sqlite(tmp_path):
    return f"sqlite:///{tmp_path}/client.db"


# La configuration : WhatsApp facultatif


def test_configuration_sans_whatsapp():
    conf = configuration.lire(SANS_WHATSAPP)
    assert conf.whatsapp is None
    # Un ordre de pilotage n'en dit rien ; avec un numéro, l'ordre reste lisible par l'image précédente.
    assert "whatsapp" not in pilotage.config_a_envoyer(conf)
    avec = pilotage.config_a_envoyer(configuration.lire(CONF))
    assert avec["whatsapp"] == {"numero_id": CONF["whatsapp"]["numero_id"]} and "api" not in json.dumps(avec)


def test_sans_whatsapp_le_webhook_n_existe_pas(sqlite):
    t, *_ = agent_api(sqlite)
    assert t.post("/whatsapp", content=b"{}").status_code == 404
    assert t.get("/whatsapp", params={"hub.mode": "subscribe"}).status_code == 404
    assert t.get("/sante").json()["ok"] is True


# La route


def test_un_message_et_sa_reponse(sqlite):
    t, agent, exp, app = agent_api(sqlite, agent=FauxAgent("Bonjour \u2014 **bienvenue**, ma clé sk-abcdefghijklmnopqrstuvwxyz"))
    _, entete = nouvelle_cle(sqlite)
    r = t.post("/api/messages", headers=entete, json={"personne": "patient-42", "texte": " Bonjour "})
    assert r.status_code == 200, r.text
    # Les mêmes garde-fous que sur WhatsApp : ni tiret long ni secret
    assert r.json() == {"reponse": "Bonjour, *bienvenue*, ma clé [masqué]"}
    # Le même tour : mémoire et session propres à cette personne de ce logiciel, rien sur WhatsApp
    assert agent.appels == [("Bonjour", "api:dossier:patient-42", "api:dossier:patient-42")]
    assert exp.envois == [] and exp.autres == []
    asyncio.run(attendre(app)())
    fil = stockage.Fil(sqlite).messages("api:dossier:patient-42")
    assert [(m["sens"], m["texte"]) for m in fil] == [("recu", "Bonjour"), ("envoye", "Bonjour, *bienvenue*, ma clé [masqué]")]
    assert stockage.Contacts(sqlite).dernier("api:dossier:patient-42") is not None


def test_deux_logiciels_ne_melent_pas_leurs_gens(sqlite):
    t, agent, *_ = agent_api(sqlite)
    _, dossier = nouvelle_cle(sqlite, "dossier")
    _, site = nouvelle_cle(sqlite, "site")
    for entete in (dossier, site):
        assert t.post("/api/messages", headers=entete, json={"personne": "p1", "texte": "x"}).status_code == 200
    assert [a[1] for a in agent.appels] == ["api:dossier:p1", "api:site:p1"]


@pytest.mark.parametrize("personne", ["+41791234567", "41791234567", "079.123.45.67", "079-123-45-67", "42", "", "a" * 41,
                                      "jean dupont", "jean@exemple.ch", "api:x", None, 42])
def test_jamais_un_numero_de_telephone(sqlite, personne):
    t, agent, *_ = agent_api(sqlite)
    _, entete = nouvelle_cle(sqlite)
    r = t.post("/api/messages", headers=entete, json={"personne": personne, "texte": "Bonjour"})
    assert r.status_code == 400 and "personne" in r.json()["erreur"]
    assert agent.appels == []


def test_les_refus(sqlite):
    t, agent, *_ = agent_api(sqlite)
    ident, entete = nouvelle_cle(sqlite)
    bon = {"personne": "p1", "texte": "Bonjour"}
    assert t.post("/api/messages", json=bon).status_code == 401
    assert t.post("/api/messages", headers={"authorization": "Bearer mga_" + "x" * 43}, json=bon).status_code == 401
    assert t.post("/api/messages", headers={"authorization": "Bearer interne"}, json=bon).status_code == 401
    assert t.post("/api/messages", headers=entete, content=b"pas du json").status_code == 400
    assert t.post("/api/messages", headers=entete, json=["p1", "x"]).status_code == 400
    assert t.post("/api/messages", headers=entete, json={**bon, "autre": 1}).status_code == 400
    assert t.post("/api/messages", headers=entete, json={"personne": "p1", "texte": "  "}).status_code == 400
    assert t.post("/api/messages", headers=entete, json={"personne": "p1", "texte": "x" * 4001}).status_code == 400
    assert t.post("/api/messages", headers=entete, content=b" " * (17 * 1024)).status_code == 413
    assert agent.appels == []
    # Une clé retirée ne sert plus, tout de suite
    assert t.post("/api/messages", headers=entete, json=bon).status_code == 200
    stockage.ClesApi(sqlite).retirer(ident)
    assert t.post("/api/messages", headers=entete, json=bon).status_code == 401


def test_le_debit_par_cle(sqlite):
    t, agent, *_ = agent_api(sqlite)
    _, entete = nouvelle_cle(sqlite, par_minute=2)
    _, autre = nouvelle_cle(sqlite, "site", par_minute=2)
    statuts = [t.post("/api/messages", headers=entete, json={"personne": f"p{i}", "texte": "x"}).status_code for i in range(3)]
    assert statuts == [200, 200, 429]
    r = t.post("/api/messages", headers=entete, json={"personne": "p9", "texte": "x"})
    assert r.status_code == 429 and 1 <= int(r.headers["retry-after"]) <= 60 and r.json()["attente"] == int(r.headers["retry-after"])
    # L'autre clé a son propre débit
    assert t.post("/api/messages", headers=autre, json={"personne": "p1", "texte": "x"}).status_code == 200
    assert len(agent.appels) == 3


def test_le_debit_par_personne(sqlite):
    t, agent, _, app = agent_api(sqlite)
    app.state.conversations.debit = Debit(maximum=1, fenetre=600)
    _, entete = nouvelle_cle(sqlite, par_minute=3)
    assert t.post("/api/messages", headers=entete, json={"personne": "p1", "texte": "x"}).status_code == 200
    # L'attente dite est la vraie (la fenêtre de la personne est de 10 minutes), et le refus n'est pas noté
    for _ in range(3):
        r = t.post("/api/messages", headers=entete, json={"personne": "p1", "texte": "encore"})
        assert r.status_code == 429 and r.json()["erreur"] == "trop de messages pour cette personne"
        assert 590 <= int(r.headers["retry-after"]) <= 600
    asyncio.run(attendre(app)())
    assert [m["texte"] for m in stockage.Fil(sqlite).messages("api:dossier:p1")] == ["x", "Bonjour, je suis Alix."]
    # Les refus pour la personne n'usent pas le débit de la clé (3 par minute) : les autres passent
    assert t.post("/api/messages", headers=entete, json={"personne": "p2", "texte": "x"}).status_code == 200
    assert t.post("/api/messages", headers=entete, json={"personne": "p3", "texte": "x"}).status_code == 200
    assert t.post("/api/messages", headers=entete, json={"personne": "p4", "texte": "x"}).status_code == 429
    assert len(agent.appels) == 3


def test_le_debit_libre_et_attente():
    d = Debit(maximum=2, fenetre=60)
    assert d.libre("a", 0) and d.attente("a", 0) == 1
    assert d.permis("a", 0) and d.permis("a", 10)
    assert not d.libre("a", 20) and not d.libre("a", 20)  # regarder ne compte pas
    assert d.attente("a", 20) == 40
    assert d.libre("a", 61) and d.attente("a", 61) == 1


def test_sans_whatsapp_rien_ne_part():
    from noyau.whatsapp import SansWhatsApp

    exp = SansWhatsApp()
    for appel in (exp.texte("p", "x"), exp.modele("p", "m", "fr", []), exp.lu("w"), exp.reaction("p", "w", ""),
                  exp.vocal("p", b"", True), exp.telecharger("m")):
        with pytest.raises(RuntimeError, match="WhatsApp"):
            asyncio.run(appel)
    assert not hasattr(exp, "autre")


def test_avec_l_api_d_agentos_nos_routes_restent_ouvertes(sqlite):
    """JWT_VERIFICATION_KEY ouvre l'API d'AgentOS, gardée par jeton ; nos routes gardent leur propre garde."""
    from agno.agent import Agent

    from test_lot5 import FauxModele

    agent = Agent(id="exemple", model=FauxModele(), telemetry=False)
    _, entete = nouvelle_cle(sqlite)
    app = creer({"CLIENT_CONFIG": json.dumps(CONF), "DATABASE_URL": sqlite, "INTERNE_TOKEN": "interne", "META_APP_SECRET": "s",
                 "JWT_VERIFICATION_KEY": "cle-publique-essai"}, agent=agent, expediteur=FauxExpediteur())
    t = TestClient(app)
    assert t.post("/api/messages", headers=entete, json={"personne": "p1", "texte": "Bonjour"}).status_code == 200
    assert t.get("/sante").status_code == 200
    assert t.post("/whatsapp", content=b"{}").text == "signature"  # la garde de Meta, pas celle d'AgentOS
    assert t.get("/interne/cles", headers={"x-megga-interne": "interne"}).status_code == 200
    assert t.get("/interne/suivi/conversations/api%3Adossier%3Ap1", headers={"x-megga-interne": "interne"}).status_code == 200
    assert t.get("/agents").status_code == 401  # l'API d'AgentOS demande son jeton


def test_un_tour_en_echec(sqlite):
    t, _, _, app = agent_api(sqlite, agent=FauxAgent(erreur=RuntimeError("clé du modèle refusée sk-xxxxxxxxxxxxxxxxxxxx")))
    _, entete = nouvelle_cle(sqlite)
    r = t.post("/api/messages", headers=entete, json={"personne": "p1", "texte": "x"})
    assert r.status_code == 503
    assert r.json() == {"erreur": "l'agent n'a pas pu répondre", "reponse": "Je rencontre un petit souci technique. Je reviens vers vous dès que possible."}
    asyncio.run(attendre(app)())
    assert stockage.Journal(sqlite).totaux(0)["tour_echec"]["nombre"] == 1


def test_avec_whatsapp_aussi(sqlite):
    """Un client sur WhatsApp peut aussi brancher un logiciel : les deux entrées vivent ensemble."""
    t, agent, *_ = agent_api(sqlite, conf=CONF)
    _, entete = nouvelle_cle(sqlite)
    assert t.post("/api/messages", headers=entete, json={"personne": "p1", "texte": "x"}).status_code == 200
    assert t.post("/whatsapp", content=b"{}").status_code == 401  # sans signature, mais la route existe


def test_pas_de_rappels_par_api(tmp_path):
    rappeler, mes_rappels, _ = outils_rappels(stockage.Rappels(f"sqlite:///{tmp_path}/r.db"), "Europe/Zurich")

    class Contexte:
        user_id = "api:dossier:p1"

    with pytest.raises(ValueError, match="rappels"):
        rappeler("2030-01-01T09:00", "appeler", run_context=Contexte())
    with pytest.raises(ValueError, match="rappels"):
        mes_rappels(run_context=Contexte())


# Les clés : routes internes (Cloudflare, par l'atelier) et commande (chez le client)


def test_les_cles_par_les_routes_internes(sqlite):
    t, agent, *_ = agent_api(sqlite)
    interne = {"x-megga-interne": "interne"}
    _, cle, empreinte = api.nouvelle_cle()
    corps = {"id": "0123456789ab", "logiciel": "dossier", "empreinte": empreinte, "par_minute": 10}
    assert t.post("/interne/cles", json=corps).status_code == 401
    assert t.post("/interne/cles", headers={"x-megga-interne": "autre"}, json=corps).status_code == 401
    assert t.post("/interne/cles", headers=interne, json=corps).json() == {"id": "0123456789ab", "logiciel": "dossier", "par_minute": 10}
    assert t.post("/interne/cles", headers=interne, json=corps).status_code == 409
    for mauvais in ({**corps, "id": "x"}, {**corps, "logiciel": "Dossier Patients"}, {**corps, "empreinte": cle},
                    {**corps, "par_minute": 0}, {**corps, "par_minute": "10"}, {"id": "0123456789ac"}):
        assert t.post("/interne/cles", headers=interne, json=mauvais).status_code == 400
    liste = t.get("/interne/cles", headers=interne).json()["cles"]
    assert [(c["id"], c["logiciel"], c["retiree"]) for c in liste] == [("0123456789ab", "dossier", None)]
    assert "empreinte" not in json.dumps(liste)
    assert t.post("/api/messages", headers={"authorization": f"Bearer {cle}"}, json={"personne": "p1", "texte": "x"}).status_code == 200
    assert t.delete("/interne/cles/0123456789ab", headers=interne).json() == {"id": "0123456789ab", "retiree": True}
    assert t.delete("/interne/cles/0123456789ab", headers=interne).json()["retiree"] is False
    assert t.post("/api/messages", headers={"authorization": f"Bearer {cle}"}, json={"personne": "p1", "texte": "x"}).status_code == 401


def test_la_commande_chez_le_client(sqlite):
    lignes = []
    assert cles.principal(["creer", "dossier-patients", "5"], {"DATABASE_URL": sqlite}, lignes.append) == 0
    cle = lignes[-1]
    assert api.CLE.fullmatch(cle)
    ident = lignes[0].split()[1]
    lignes.clear()
    assert cles.principal(["lister"], {"DATABASE_URL": sqlite}, lignes.append) == 0
    assert lignes[0].startswith(f"{ident}  dossier-patients  5/min") and cle not in lignes[0]
    t, agent, *_ = agent_api(sqlite)
    assert t.post("/api/messages", headers={"authorization": f"Bearer {cle}"}, json={"personne": "p1", "texte": "x"}).status_code == 200
    assert cles.principal(["retirer", ident], {"DATABASE_URL": sqlite}, lignes.append) == 0
    assert t.post("/api/messages", headers={"authorization": f"Bearer {cle}"}, json={"personne": "p1", "texte": "x"}).status_code == 401
    # Les refus
    for args in (["creer", "Dossier"], ["creer"], ["creer", "dossier", "0"], ["creer", "dossier", "beaucoup"], ["retirer", "x"], [], ["autre"]):
        assert cles.principal(args, {"DATABASE_URL": sqlite}, lignes.append) == 2, args
    assert cles.principal(["lister"], {}, lignes.append) == 1


# Le suivi et les coûts


def test_le_suivi_compte_les_tours_par_api():
    conf = configuration.lire(SANS_WHATSAPP)
    tours = [{"personne": "41790000000", "quand": 1, "statut": "COMPLETED", "modeles": [{"id": "claude-sonnet-5-5", "input_tokens": 10}]},
             {"personne": "api:dossier:p1", "quand": 2, "statut": "COMPLETED", "modeles": [{"id": "claude-sonnet-5-5", "input_tokens": 5}]}]
    r = suivi.resumer(conf, tours, {}, 0, 0)
    assert (r["tours"], r["tours_api"], r["personnes"], r["modeles"]["claude-sonnet-5-5"]["entree"]) == (2, 1, 2, 15)
    assert suivi.PERSONNE.fullmatch("api:dossier:patient-42") and suivi.PERSONNE.fullmatch("+41790000000")
    for mauvais in ("api:dossier:42", "api:Dossier:p1", "api::p1", "api:dossier:p/1", "abc"):
        assert not suivi.PERSONNE.fullmatch(mauvais), mauvais


def test_le_fil_d_une_personne_par_api(sqlite):
    t, *_ = agent_api(sqlite)
    _, entete = nouvelle_cle(sqlite)
    t.post("/api/messages", headers=entete, json={"personne": "patient-42", "texte": "Bonjour"})
    interne = {"x-megga-interne": "interne"}
    conv = t.get("/interne/suivi/conversations", headers=interne).json()["conversations"]
    assert [c["personne"] for c in conv] == ["api:dossier:patient-42"]
    r = t.get("/interne/suivi/conversations/api%3Adossier%3Apatient-42", headers=interne)
    assert [m["texte"] for m in r.json()["messages"]] == ["Bonjour", "Bonjour, je suis Alix."]


# Les clés dans l'atelier


class PorteAuxCles(FaussePorte):
    """La porte d'essai, avec le conteneur du client qui garde les empreintes."""

    def __init__(self):
        super().__init__()
        self.cles_recues = []

    async def cles(self, ident, methode="GET", chemin="", corps=None):
        self.cles_recues.append((ident, methode, chemin, corps))
        if methode == "POST":
            return {"id": corps["id"], "logiciel": corps["logiciel"], "par_minute": corps["par_minute"]}
        if methode == "DELETE":
            return {"id": chemin[1:], "retiree": True}
        return {"cles": []}


@pytest.fixture
def atelier(tmp_path):
    porte = PorteAuxCles()
    app = creer_atelier({"ADMIN_TOKEN": ADMIN, "DATABASE_URL": f"sqlite:///{tmp_path}/atelier.db"}, porte=porte,
                        principal_essai=FauxModele())
    t = TestClient(app)
    t.porte = porte
    return t


def test_l_atelier_cree_une_cle_montree_une_fois(atelier):
    nouveau_client(atelier)
    r = atelier.post("/atelier/clients/exemple/cles", headers=MEGGA, json={"logiciel": "dossier", "par_minute": 12})
    assert r.status_code == 201, r.text
    d = r.json()
    assert api.CLE.fullmatch(d["cle"]) and (d["logiciel"], d["par_minute"]) == ("dossier", 12)
    # Seule l'empreinte part au conteneur ; l'atelier ne garde rien de la clé
    (ident, methode, chemin, corps), = atelier.porte.cles_recues
    assert (ident, methode, corps["id"]) == ("exemple", "POST", d["id"])
    assert corps["empreinte"] == hashlib.sha256(d["cle"].encode()).hexdigest() and d["cle"] not in json.dumps(corps)
    assert atelier.get("/atelier/clients/exemple/cles", headers=MEGGA).json() == {"client": "exemple", "cles": []}
    assert atelier.delete(f"/atelier/clients/exemple/cles/{d['id']}", headers=MEGGA).json() == {"client": "exemple", "id": d["id"], "retiree": True}


def test_le_client_cree_ses_cles_et_seulement_les_siennes(atelier):
    nouveau_client(atelier)
    nouveau_client(atelier, id="voisin", whatsapp={"numero_id": "100000000000077"})
    client = jeton_client(atelier)
    assert atelier.post("/atelier/clients/exemple/cles", headers=client, json={"logiciel": "site"}).json()["par_minute"] == api.PAR_MINUTE
    assert atelier.post("/atelier/clients/voisin/cles", headers=client, json={"logiciel": "site"}).status_code == 404
    assert atelier.post("/atelier/clients/exemple/cles", json={"logiciel": "site"}).status_code == 401
    for mauvais in ({"logiciel": "Mon Site"}, {}, {"logiciel": "site", "par_minute": 601}, {"logiciel": "site", "par_minute": True}):
        assert atelier.post("/atelier/clients/exemple/cles", headers=client, json=mauvais).status_code == 400
    assert atelier.delete("/atelier/clients/exemple/cles/pas-une-cle", headers=client).status_code == 400


def test_hors_cloudflare_les_cles_se_creent_chez_le_client(atelier):
    nouveau_client(atelier, id="chez-lui", zone="client", whatsapp={"numero_id": "100000000000078"})
    r = atelier.post("/atelier/clients/chez-lui/cles", headers=MEGGA, json={"logiciel": "dossier"})
    assert r.status_code == 409 and "python -m noyau.cles" in r.json()["erreur"]
    assert atelier.porte.cles_recues == []


def test_un_client_sans_whatsapp_dans_l_atelier(atelier):
    r = atelier.post("/atelier/clients", headers=MEGGA, json={"gabarit": "generaliste", "nom_agent": "Lea",
                                                                "client": {"id": "cabinet", "entreprise": "Cabinet du Lac", "zone": "europe"}})
    assert r.status_code == 201, r.text
    conf = atelier.get("/atelier/clients/cabinet/versions/1", headers=MEGGA).json()["config"]
    assert conf.get("whatsapp") is None


def test_l_image_precedente_ne_recoit_pas_de_configuration_sans_whatsapp():
    from atelier.app import trop_ancienne

    minimum = configuration.SANS_WHATSAPP_SCHEMA
    assert minimum == stockage.SCHEMA_VERSION  # l'image de ce code sert une configuration sans WhatsApp
    assert trop_ancienne({"version": "0.2.0", "schema": 1}, minimum)
    assert not trop_ancienne({"version": "0.2.0", "schema": 2}, minimum)  # le numéro de version n'y fait rien
    assert not trop_ancienne({"version": "0.4.0", "schema": 3}, minimum)
    for inconnu in (None, {}, {"schema": None}, {"schema": "1"}, {"schema": True}):
        assert not trop_ancienne(inconnu, minimum)  # inconnu : l'installation jugera


# La base : la personne s'élargit (migration 2), lisible par l'image précédente


@pytest.fixture(params=["sqlite"] + (["postgres"] if os.environ.get("TEST_POSTGRES_URL") else []))
def base_neuve(request, tmp_path):
    """Une base à elle seule : sous Postgres, une base créée pour l'essai, puis effacée."""
    if request.param == "sqlite":
        yield f"sqlite:///{tmp_path}/v1.db"
        return
    import uuid

    from sqlalchemy import create_engine, text

    url = os.environ["TEST_POSTGRES_URL"]
    nom = f"essai_{uuid.uuid4().hex[:10]}"
    racine = create_engine(stockage.moteur(url).url, isolation_level="AUTOCOMMIT")
    with racine.connect() as c:
        c.execute(text(f'CREATE DATABASE "{nom}"'))
    try:
        yield url.rsplit("/", 1)[0] + "/" + nom
    finally:
        with stockage._VERROU:
            for cle in [k for k in stockage._MOTEURS if k.endswith("/" + nom)]:
                stockage._MOTEURS.pop(cle).dispose()
        with racine.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{nom}" WITH (FORCE)'))
        racine.dispose()


def test_migration_elargit_la_personne(base_neuve):
    base = base_neuve
    e = stockage.moteur(base)
    pg = e.dialect.name == "postgresql"
    stockage.Contacts(base)
    stockage.Fil(base)
    stockage.Rappels(base)
    schema = stockage.SCHEMA if pg else None
    if pg:  # une base de la version 1 : personne en 32 caractères
        with e.begin() as c:
            for table in ("megga_contacts", "megga_rappels", "megga_fil"):
                c.execute(stockage.text(f'ALTER TABLE "{schema}"."{table}" ALTER COLUMN personne TYPE VARCHAR(32)'))
    e2, t = stockage._table_schema(base)
    with e2.begin() as c:
        c.execute(t.delete())
        c.execute(t.insert().values(cle="megga", version=1))
    stockage.Contacts(base).noter("41790000000", 2.0)  # une personne d'avant, gardée
    assert stockage.migrer(base) == 2
    if pg:
        for table in ("megga_contacts", "megga_rappels", "megga_fil"):
            col = next(c for c in inspect(e).get_columns(table, schema=schema) if c["name"] == "personne")
            assert col["type"].length == stockage.PERSONNE
    longue = api.personne_interne("dossier-patients-ab", "x" * 40)
    stockage.Contacts(base).noter(longue, 1.0)
    assert stockage.Contacts(base).dernier(longue) == 1.0
    assert stockage.Contacts(base).dernier("41790000000") == 2.0
    # L'image précédente (version 1) démarre encore sur cette base
    assert stockage.migrer(base, version=1) == 2


@pytest.mark.skipif(not os.environ.get("TEST_POSTGRES_URL"), reason="Postgres d'essai absent")
def test_les_cles_sous_postgres():
    url = os.environ["TEST_POSTGRES_URL"]
    c = stockage.ClesApi(url)
    ident, cle, empreinte = api.nouvelle_cle()
    assert c.ajouter(ident, "dossier", empreinte, 5)
    assert not c.ajouter(ident, "dossier", empreinte, 5)
    assert c.par_empreinte(api.empreinte(cle)) == {"id": ident, "logiciel": "dossier", "par_minute": 5}
    assert c.retirer(ident) and c.par_empreinte(empreinte) is None
