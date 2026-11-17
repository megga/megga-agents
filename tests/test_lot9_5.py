"""Lot 9.5 : le client et ses chiffres (valeur), la conformité (mention de l'IA, droits des personnes), ses modèles."""

import json
import time

import pytest
from fastapi.testclient import TestClient

from atelier import regles
from noyau import config as configuration, connecteurs, stockage
from noyau.agent import modele
from noyau.app import creer
from noyau.typographie import nettoyer

CONF = configuration.lire("clients/exemple.yaml").model_dump(mode="json")
INTERNE = {"x-megga-interne": "interne"}


@pytest.fixture
def url(tmp_path):
    return f"sqlite:///{tmp_path}/client.db"


def agent_whatsapp(url, **conf):
    from test_app import SECRET, FauxAgent, FauxExpediteur

    agent, exp = FauxAgent("Bonjour !"), FauxExpediteur()
    app = creer({"CLIENT_CONFIG": json.dumps({**CONF, **conf}), "DATABASE_URL": url, "META_APP_SECRET": SECRET, "INTERNE_TOKEN": "interne"},
                agent=agent, expediteur=exp, attente=0.01, seuil_regard=30)
    return app, agent, exp


def ecrire(app, t, texte, ident):
    from test_app import attendre, corps, signe

    c = corps(texte, ident)
    assert t.post("/whatsapp", content=c, headers=signe(c)).status_code == 200
    t.portal.call(attendre(app))


# Les modèles du client


def test_le_catalogue_dit_qui_fait_tourner_chaque_modele():
    c = regles.catalogue()
    detail = {m["id"]: m for m in c["modeles_detail"]}
    assert set(detail) == set(c["modeles"])
    assert detail["mistral-large-latest"]["hebergement"].startswith("Union européenne")
    assert detail["deepseek-v4-pro"]["hebergement"] == "Chine"


def test_mistral_seulement_avec_sa_cle_et_un_secours_choisi():
    sans, avec = regles.offerts({}), regles.offerts({"MISTRAL_API_KEY": "cle"})
    assert "mistral-large-latest" not in sans + tuple(regles.catalogue(sans)["modeles"]) and "mistral-large-latest" in avec
    base = {**CONF, "modeles": {"principal": "claude-sonnet-5-5", "secours": "deepseek-v4-pro"}}
    with pytest.raises(regles.Refus) as e:  # sans sa clé, chaque tour échouerait
        regles.appliquer("client", base, {"modeles": {"principal": "mistral-large-latest", "secours": None}}, None, sans)
    assert e.value.statut == 400
    with pytest.raises(regles.Refus) as e:  # le secours resterait DeepSeek, en Chine
        regles.appliquer("client", base, {"modeles": {"principal": "mistral-large-latest"}}, None, avec)
    assert e.value.statut == 400 and "secours" in e.value.message
    c = regles.appliquer("client", base, {"modeles": {"principal": "mistral-large-latest", "secours": "mistral-medium-latest"}}, None, avec)
    assert (c.modeles.principal, c.modeles.secours) == ("mistral-large-latest", "mistral-medium-latest")
    # une configuration écrite à la main : pas de secours d'office derrière un modèle européen
    with pytest.raises(ValueError):
        configuration.Modeles(principal="mistral-large-latest")
    assert configuration.Modeles(principal="mistral-large-latest", secours=None).secours is None


def test_un_modele_mistral():
    m = modele("mistral-large-latest", {"MISTRAL_API_KEY": "cle"})
    assert (m.id, m.base_url, m.api_key) == ("mistral-large-latest", "https://api.mistral.ai/v1", "cle")
    with pytest.raises(ValueError):
        modele("gpt-9", {})


# La mention de l'IA


def test_la_mention_de_l_ia_au_debut_d_une_conversation(url):
    app, agent, exp = agent_whatsapp(url, mention_ia=True)
    with TestClient(app) as t:
        ecrire(app, t, "Bonjour", "wamid.1")
        ecrire(app, t, "Encore moi", "wamid.2")
    textes = [x[1] for x in exp.envois]
    assert textes[0] == "Vous échangez avec Alix, l'assistant virtuel d'Entreprise exemple : une intelligence artificielle."
    assert textes[1:] == ["Bonjour !", "Bonjour !"]  # une fois par conversation, pas à chaque message


def test_sans_reglage_pas_de_mention_et_avec_transfert_l_offre_d_un_humain(url, tmp_path):
    app, _, exp = agent_whatsapp(url)
    with TestClient(app) as t:
        ecrire(app, t, "Bonjour", "wamid.1")
    assert [x[1] for x in exp.envois] == ["Bonjour !"]
    app, _, exp = agent_whatsapp(f"sqlite:///{tmp_path}/autre.db", mention_ia=True, transfert=True, langue="en")
    with TestClient(app) as t:
        ecrire(app, t, "Hello", "wamid.3")
    assert exp.envois[0][1].endswith("You can ask to speak to a member of the team.")


def test_la_mention_attend_une_vraie_reponse(url):
    from test_app import attendre, signe

    app, _, exp = agent_whatsapp(url, mention_ia=True, entreprise="Brun Immobilier")
    lieu = json.dumps({"object": "whatsapp_business_account", "entry": [{"changes": [{"field": "messages", "value": {
        "metadata": {"phone_number_id": "100000000000001"},
        "messages": [{"from": "41790000000", "id": "wamid.0", "type": "location", "timestamp": str(int(time.time())),
                      "location": {"latitude": 46.2, "longitude": 6.1}}]}}]}]}).encode()
    with TestClient(app) as t:
        assert t.post("/whatsapp", content=lieu, headers=signe(lieu)).status_code == 200
        t.portal.call(attendre(app))
        ecrire(app, t, "Bonjour", "wamid.1")
        ecrire(app, t, "Encore moi", "wamid.2")
    textes = [x[1] for x in exp.envois]
    mention = "Vous échangez avec Alix, l'assistant virtuel de Brun Immobilier : une intelligence artificielle."
    assert textes[1:] == [mention, "Bonjour !", "Bonjour !"]  # après le message illisible, et une seule fois
    assert stockage.Etats(url).lire("+41790000000", "mention_ia")


def test_la_mention_par_api(url):
    from test_lot6_api import agent_api, nouvelle_cle

    t, *_ = agent_api(url, conf={**{k: v for k, v in CONF.items() if k != "whatsapp"}, "mention_ia": True})
    _, entete = nouvelle_cle(url)
    premier = t.post("/api/messages", headers=entete, json={"personne": "p1", "texte": "Bonjour"}).json()["reponse"]
    second = t.post("/api/messages", headers=entete, json={"personne": "p1", "texte": "Et ensuite ?"}).json()["reponse"]
    assert premier.startswith("Vous échangez avec Alix") and "intelligence artificielle" not in second


# Les droits des personnes


def test_exporter_puis_effacer_les_donnees_d_une_personne(url):
    app, _, _ = agent_whatsapp(url)
    t = TestClient(app)
    maintenant = time.time()
    for p in ("+41790000001", "+41790000002"):
        stockage.Fil(url).noter(p, "recu", "texte", f"Bonjour de {p}", maintenant)
        stockage.Contacts(url).noter(p, maintenant)
    stockage.Rappels(url).ajouter("+41790000001", maintenant + 3600, "Visite")
    lu = t.get("/interne/personnes/+41790000001", headers=INTERNE).json()
    assert {"megga_fil", "megga_contacts", "megga_rappels"} <= set(lu["donnees"]) and "+41790000002" not in json.dumps(lu)
    assert t.get("/interne/personnes/+41790000001").status_code == 401
    assert t.get("/interne/personnes/nimporte quoi", headers=INTERNE).status_code == 400
    efface = t.delete("/interne/personnes/+41790000001", headers=INTERNE).json()["effacees"]
    assert efface["megga_fil"] == 1 and efface["megga_rappels"] == 1
    assert t.get("/interne/personnes/+41790000001", headers=INTERNE).json()["donnees"] == {}
    assert len(stockage.Fil(url).messages("+41790000002")) == 1  # les autres restent


def test_chaque_table_dit_qui_elle_designe(url):
    for table in stockage.TABLES:
        table(url)
    nos = {t.name for t in stockage._tables(stockage.moteur(url)).sorted_tables if t.name.startswith("megga_")}
    assert nos - set(stockage.PERSONNES) == set()


def test_l_export_ne_remet_ni_la_consigne_ni_les_autres(url):
    from sqlalchemy import insert

    stockage.preparer(url)
    e = stockage.moteur(url)
    tables = {t.name: t for t in stockage._tables(e).sorted_tables}
    with e.begin() as c:
        c.execute(insert(tables["agno_sessions"]).values(session_id="s", session_type="agent", user_id="+41790000001",
                                                         agent_data={"consigne": "le prompt de MEGGA"}, created_at=1))
        c.execute(insert(tables["agno_memories"]).values(memory_id="m", memory={"memory": "aime les villas"}, user_id="+41790000001",
                                                         created_at=1, updated_at=1))
    stockage.Fil(url).noter("+41790000001", "recu", "texte", "Bonjour", time.time())
    stockage.Approbations(url).demander("+41790000002", "public", "envoyer_fiche", {})
    stockage.Approbations(url).decider(1, False, "+41790000001")  # elle a seulement décidé pour un autre
    lu = stockage.donnees_personne(url, "+41790000001")
    assert set(lu) == {"agno_memories", "megga_fil"} and "prompt" not in json.dumps(lu)


def test_l_effacement_trouve_la_personne_partout_et_garde_son_blocage(url):
    app, _, _ = agent_whatsapp(url)
    t = TestClient(app)
    p, autre = "+41790000001", "+41790000002"
    maintenant = time.time()
    stockage.Questions(url).poser(p, autre, "La villa est libre ?", "villa", "fr", None, nom="Jean")
    reseau = stockage.Reseau(url)
    reseau.creer(p, "Agence Jean", autre, "villa à Genève", [{"reference": "R1"}])
    reseau.reprendre_recherche({"id": "r1", "partenaire": p, "criteres": "{}", "resume": "villa", "cree": maintenant,
                                "derniere": maintenant, "close": None})
    stockage.Carnet(url).noter({"nature": "vente", "lieu": "Genève", "famille": "appartement", "devise": "CHF", "prix_m2": 12000,
                                "date": maintenant, "note": 1}, par=p)
    stockage.Bloques(url).bloquer(p, autre, nom="Jean")
    stockage.Audit(url).noter(p, "envoyer_fiche", "libre", "faite", 0.1)
    # « 41… » comme « +41… »
    fait = t.delete("/interne/personnes/41790000001", headers=INTERNE).json()
    assert fait["effacees"] == {"megga_questions": 1, "megga_demandes": 1, "megga_propositions": 1, "megga_recherches": 1}
    assert fait["pseudonymisees"] == {"megga_releves": 1, "megga_bloques": 1, "megga_audit": 1}
    assert stockage.Bloques(url).bloque(p)  # bloquée pour abus, elle le reste
    assert p not in json.dumps([stockage.Bloques(url).lister(), stockage.Audit(url).lire(), stockage.Carnet(url).releves()])
    assert "Jean" not in json.dumps(stockage.Bloques(url).lister())
    assert t.get("/interne/personnes/41790000001", headers=INTERNE).json()["personne"] == p


# Ce que l'agent fait gagner


def test_la_valeur_de_la_periode(url):
    leads = connecteurs.Leads(stockage.Leads(url))
    from test_app import FauxAgent, FauxExpediteur

    app = creer({"CLIENT_CONFIG": json.dumps({**CONF, "outils": ["leads"], "transfert": True, "minutes_par_conversation": 6}),
                 "DATABASE_URL": url, "INTERNE_TOKEN": "interne"}, agent=FauxAgent(), expediteur=FauxExpediteur(), leads=leads)
    maintenant = time.time()
    for p in ("+41790000001", "+41790000002", "+41790000003"):
        stockage.Fil(url).noter(p, "recu", "texte", "Bonjour", maintenant)
        stockage.Fil(url).noter(p, "envoye", "texte", "Bonjour !", maintenant + 1)
    stockage.Fil(url).noter("+41790000009", "recu", "texte", "Il y a longtemps", maintenant - 40 * 86400)
    stockage.Reprises(url).ouvrir("+41790000003", "public", "humain", "r")
    stockage.Leads(url).noter("+41790000001", {"besoin": "villa", "score": 5})
    stockage.Leads(url).noter("+41790000002", {"besoin": "studio", "score": 2})
    d = stockage.Approbations(url)
    d.demander("+41790000001", "public", "envoyer_fiche", {})
    d.decider(1, False, "console")
    v = TestClient(app).get("/interne/suivi/valeur", params={"depuis": maintenant - 7 * 86400}, headers=INTERNE).json()
    assert v == {"conversations": 3, "resolues_sans_humain": 2, "transmises": 1, "taux_sans_humain": 0.667, "leads": 2,
                 "leads_chauds": 1, "actions_faites": 0, "actions_refusees": 1, "actions_en_attente": 0, "minutes_gagnees": 12,
                 "minutes_par_conversation": 6}


def test_la_valeur_compte_des_conversations_du_public(url):
    from noyau.garde import TROP
    from test_app import FauxAgent, FauxExpediteur

    conf = {**CONF, "transfert": True, "roles": {"gestionnaire": {}, "visiteur": {}}}
    app = creer({"CLIENT_CONFIG": json.dumps(conf), "DATABASE_URL": url, "INTERNE_TOKEN": "interne",
                 "GESTIONNAIRES": json.dumps({"+41790000008": "gestion"})}, agent=FauxAgent(),
                agents={"gestionnaire": FauxAgent(), "visiteur": FauxAgent()}, expediteur=FauxExpediteur())
    fil, maintenant = stockage.Fil(url), time.time()
    stockage.Reprises(url).ouvrir("+41790000003", "visiteur", "humain", "r")  # ouverte avant la période, toujours en cours
    depuis = maintenant + 10
    for quand in (depuis + 100, depuis + 30 * 3600):  # deux conversations, à plus de douze heures l'une de l'autre
        fil.noter("+41790000001", "recu", "texte", "Bonjour", quand)
        fil.noter("+41790000001", "envoye", "texte", "Bonjour !", quand + 1)
    for p in ("+41790000003", "+41790000008"):  # une transmise à l'équipe ; un gestionnaire
        fil.noter(p, "recu", "texte", "Bonjour", depuis + 100)
        fil.noter(p, "envoye", "texte", "Bonjour !", depuis + 101)
    fil.noter("+41790000004", "recu", "texte", "Vite", depuis + 100)  # arrêtée par le débit : pas de réponse
    fil.noter("+41790000004", "envoye", "texte", nettoyer(TROP), depuis + 101)
    v = TestClient(app).get("/interne/suivi/valeur", params={"depuis": depuis}, headers=INTERNE).json()
    assert (v["conversations"], v["resolues_sans_humain"], v["transmises"]) == (3, 2, 1)


# L'atelier


def test_l_atelier(tmp_path):
    from atelier.app import creer as creer_atelier
    from test_lot5 import ADMIN, CLE_PILOTAGE_TEXTE, MEGGA, FaussePorte, FauxModele, jeton_client, nouveau_client

    class Porte(FaussePorte):
        def __init__(self):
            super().__init__()
            self.appels = []

        async def suivi(self, ident, chemin="", **params):
            return {"conversations": 3} if chemin == "/valeur" else {}

        async def personne(self, ident, methode, personne):
            self.appels.append((methode, personne))
            return {"personne": personne, "donnees": {}} if methode == "GET" else {"personne": personne, "effacees": {"megga_fil": 2}}

    porte = Porte()
    t = TestClient(creer_atelier({"ADMIN_TOKEN": ADMIN, "DATABASE_URL": f"sqlite:///{tmp_path}/atelier.db", "MISTRAL_API_KEY": "cle",
                                  "ESSAIS_DIR": str(tmp_path / "essais"), "PILOTAGE_CLE": CLE_PILOTAGE_TEXTE},
                                 porte=porte, principal_essai=FauxModele()))
    nouveau_client(t)
    client = jeton_client(t)
    assert t.get("/atelier/clients/exemple/valeur", params={"jours": 30}, headers=client).json() == {"periode_jours": 30, "conversations": 3}
    assert t.get("/atelier/clients/exemple/personnes/+41790000001", headers=client).json()["donnees"] == {}
    assert t.delete("/atelier/clients/exemple/personnes/+41790000001", headers=client).status_code == 400  # sans confirmation
    assert t.delete("/atelier/clients/exemple/personnes/+41790000001", params={"confirmer": "oui"}, headers=client).json()["effacees"] == {"megga_fil": 2}
    assert t.get("/atelier/clients/exemple/personnes/nimporte", headers=client).status_code == 400
    assert porte.appels == [("GET", "+41790000001"), ("DELETE", "+41790000001")]
    journal = stockage.JournalPilotage(f"sqlite:///{tmp_path}/atelier.db").lire("exemple")
    assert [(j["evenement"], j["detail"]) for j in journal] == [("effacement", "données d'une personne effacées, à la demande du client")]
    # le client règle sa mention de l'IA, ses minutes et ses modèles
    r = t.post("/atelier/clients/exemple/versions", headers=client, json={"changements": {
        "mention_ia": True, "minutes_par_conversation": 8, "modeles": {"principal": "mistral-large-latest", "secours": "claude-sonnet-5-5"}}})
    assert r.status_code == 201, r.text
    c = r.json()["config"]
    assert (c["mention_ia"], c["minutes_par_conversation"], c["modeles"]["principal"]) == (True, 8, "mistral-large-latest")
    # Ses modèles sont à lui : il met cette version en service sans MEGGA
    v = r.json()["version"]
    t.post(f"/atelier/clients/exemple/versions/{v}/essai", headers=client, json={"message": "Bonjour"})
    assert t.post(f"/atelier/clients/exemple/versions/{v}/activer", headers=client).status_code == 200, "le client choisit ses modèles"
    # Le modèle de l'oral et du fil reste à MEGGA : revenir à une version d'avant ne le change pas
    r = t.post("/atelier/clients/exemple/versions", headers=MEGGA, json={"changements": {"modeles": {"oral": "claude-haiku-5-5"}}})
    v_oral = r.json()["version"]
    assert t.post(f"/atelier/clients/exemple/versions/{v_oral}/activer", headers=MEGGA, json={"forcer": True}).status_code == 200
    r = t.post(f"/atelier/clients/exemple/versions/{v}/activer", headers=client)
    assert r.status_code == 403 and "réglages de MEGGA" in r.json()["erreur"]
