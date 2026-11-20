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
        assert [(c["personne"], c["messages"]) for c in conv] == [(MOI, 4)]
        fil = t.get(f"/interne/suivi/conversations/{MOI}", headers=INTERNE).json()["messages"]
        assert [(x["sens"], x["genre"]) for x in fil] == [("recu", "texte"), ("envoye", "texte")] * 2
        assert fil[0]["texte"] == "Bonjour" and fil[1]["texte"] == "Bonjour, ici votre agent d'essai."
        assert "sk-ant" not in json.dumps(fil)  # ni clé ni jeton dans la console, même dits par la personne
        assert t.get("/interne/suivi/conversations/abc", headers=INTERNE).status_code == 400
        assert len(t.get(f"/interne/suivi/conversations/{MOI}?limite=1", headers=INTERNE).json()["messages"]) == 1


def test_avant_le_fil_les_tours_d_agno(tmp_path):
    """Les conversations d'avant le fil se rebâtissent des tours ; un tour en échec montre l'excuse reçue."""
    from noyau.tour import EXCUSE

    agent, url = agent_et_base(tmp_path)
    asyncio.run(agent.arun("Bonjour", user_id=MOI, session_id=MOI))
    lecture = stockage.Suivi(url)
    assert lecture.conversations() == [{"personne": MOI, "messages": 2, "derniere": lecture.conversations()[0]["derniere"]}]
    fil = lecture.messages(MOI, 50, EXCUSE)
    assert [(m["sens"], m["texte"]) for m in fil] == [("recu", "Bonjour"), ("envoye", "Bonjour, ici votre agent d'essai.")]
    with stockage.moteur(url).begin() as c:
        c.execute(stockage.text("UPDATE agno_runs SET status = 'ERROR'"))
    assert lecture.messages(MOI, 50, EXCUSE)[-1]["texte"] == EXCUSE


def test_le_secours_est_compte(tmp_path):
    app, _ = serveur(tmp_path, principal=ModeleEnPanne(id="claude-sonnet-5-5", provider="Anthropic"),
                     secours=ModeleCompte(id="deepseek-v4-pro", provider="DeepSeek"))
    with TestClient(app) as t:
        ecrire(t, app, "Bonjour", "w1")
        s = t.get("/interne/suivi", headers=INTERNE).json()
        assert s["tours"] == 1 and s["secours"] == 1
        # chez DeepSeek, les jetons d'entrée comprennent le cache : il n'est pas compté deux fois
        assert s["modeles"]["deepseek-v4-pro"] == {"fournisseur": "DeepSeek", "tours": 1, "entree": 500, "sortie": 200,
                                                  "cache_lecture": 500, "cache_ecriture": 0}


def test_entree_hors_cache_selon_le_fournisseur():
    from noyau.suivi import entree_hors_cache

    m = {"input_tokens": 1000, "cache_read_tokens": 800}
    assert entree_hors_cache({**m, "id": "claude-sonnet-5-5", "provider": "Anthropic"}) == 1000
    assert entree_hors_cache({**m, "id": "eu.anthropic.claude-sonnet-5-5", "provider": "AwsBedrock"}) == 1000
    assert entree_hors_cache({**m, "id": "deepseek-v4-pro", "provider": "DeepSeek"}) == 200
    assert entree_hors_cache({"input_tokens": 10, "cache_read_tokens": 30, "id": "x"}) == 0


def test_sans_base_le_suivi_est_indisponible():
    from test_app import FauxAgent

    app = creer_agent({"CLIENT_CONFIG": CONF, "META_APP_SECRET": "s", "INTERNE_TOKEN": "jeton"}, agent=FauxAgent(), expediteur=FauxExpediteur())
    assert TestClient(app).get("/interne/suivi", headers=INTERNE).status_code == 503


def tour_complet(c, personne, entrants):
    """Un tour, puis les écritures de suivi faites en arrière-plan."""
    async def tout():
        await c._tour(personne, entrants)
        while c.taches:
            await asyncio.gather(*list(c.taches), return_exceptions=True)

    asyncio.run(tout())


def test_le_journal_garde_les_echecs_sans_texte(tmp_path):
    from noyau.whatsapp import Entrant

    url = f"sqlite:///{tmp_path}/j.db"
    j = stockage.Journal(url)

    class AgentEnPanne:
        async def arun(self, *a, **k):
            raise RuntimeError("Claude et DeepSeek injoignables")

    class ExpEnPanne(FauxExpediteur):
        async def texte(self, vers, texte):
            raise ConnectionError("Meta injoignable")

    c = Conversations(lire("clients/exemple.yaml"), AgentEnPanne(), ExpEnPanne(), attente=0.01, journal=j)
    tour_complet(c, MOI, [Entrant(id="w1", de=MOI, texte="Mon secret", envoye=time.time(), genre="text")])
    j.noter("voix_caracteres", 120)
    j.noter("voix_caracteres", 80)
    totaux = j.totaux(0)
    assert totaux["tour_echec"]["nombre"] == 1 and totaux["envoi_echec"]["nombre"] == 1
    assert totaux["voix_caracteres"] == {"nombre": 2, "quantite": 200.0}
    alertes = j.alertes(0)
    assert {a["genre"] for a in alertes} == {"tour_echec", "envoi_echec"}
    assert "secret" not in json.dumps(alertes) and MOI not in json.dumps(alertes)
    assert j.alertes(time.time() + 60) == []
    from noyau.suivi import resumer

    assert resumer(lire("clients/exemple.yaml"), [], totaux, 0, 0)["tours_en_echec"] == 1  # une seule source


def test_un_journal_en_panne_ne_casse_pas_le_tour(tmp_path):
    from test_app import FauxAgent
    from noyau.whatsapp import Entrant

    class EnPanne:
        def noter(self, *a, **k):
            raise RuntimeError("base perdue")

    exp = FauxExpediteur()
    c = Conversations(lire("clients/exemple.yaml"), FauxAgent(reponse="Bien reçu."), exp, attente=0.01, journal=EnPanne(), fil=EnPanne())
    tour_complet(c, MOI, [Entrant(id="w1", de=MOI, texte="Bonjour", envoye=time.time(), genre="text")])
    assert exp.envois == [(MOI, "Bien reçu.")]


def test_le_suivi_ne_retarde_pas_la_reponse(tmp_path):
    """Une base lente pour le suivi : la réponse part sans attendre l'écriture du fil ni du journal."""
    import threading

    from test_app import FauxAgent
    from noyau.whatsapp import Entrant

    libre = threading.Event()

    class Lente:
        def __init__(self):
            self.notes = []

        def noter(self, *a, **k):
            libre.wait(5)
            self.notes.append(a)

    exp, fil = FauxExpediteur(), Lente()
    c = Conversations(lire("clients/exemple.yaml"), FauxAgent(reponse="Bien reçu."), exp, attente=0.01, fil=fil, journal=Lente())

    async def tout():
        await c._tour(MOI, [Entrant(id="w1", de=MOI, texte="Bonjour", envoye=time.time(), genre="text")])
        assert exp.envois == [(MOI, "Bien reçu.")] and fil.notes == []  # parti, alors que le fil attend encore
        libre.set()
        while c.taches:
            await asyncio.gather(*list(c.taches), return_exceptions=True)

    asyncio.run(tout())
    assert [n[1:3] for n in fil.notes] == [("recu", "texte"), ("envoye", "texte")]


def test_le_fil_montre_tout_ce_que_la_personne_a_vecu(tmp_path):
    """Messages reçus sans tour (débit dépassé), rappels envoyés par l'agent : tout est au fil."""
    from test_app import FauxAgent
    from noyau.whatsapp import Entrant

    url = f"sqlite:///{tmp_path}/f.db"
    fil = stockage.Fil(url)

    class Ouvert:
        def dernier(self, personne):
            return time.time()

        def noter(self, *a):
            pass

    c = Conversations(lire("clients/exemple.yaml"), FauxAgent(reponse="Bien reçu."), FauxExpediteur(), contacts=Ouvert(),
                      attente=0.01, fil=fil)

    async def tout():
        assert await c.ecrire_de_soi_meme(MOI, "Rappel : appeler l'agence", "rappel") == "libre"
        while c.taches:
            await asyncio.gather(*list(c.taches), return_exceptions=True)

    asyncio.run(tout())
    assert [(m["sens"], m["genre"], m["texte"]) for m in fil.messages(MOI)] == [("envoye", "rappel", "Rappel : appeler l'agence")]

    class Ferme:
        def permis(self, personne):
            return False

        def prevenir(self, personne):
            return True

    c.debit = Ferme()
    tour_complet(c, MOI, [Entrant(id="w2", de=MOI, texte="Encore moi", envoye=time.time(), genre="text")])
    derniers = [(m["sens"], m["texte"]) for m in fil.messages(MOI)][-2:]
    assert derniers[0] == ("recu", "Encore moi") and derniers[1][0] == "envoye"  # reçu sans tour, puis le message de débit


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
    assert c["collegues"] == {}


def test_le_cout_de_chaque_collegue():
    lea = {"claude-sonnet-5-5": {"entree": 1_000_000, "sortie": 0}, "deepseek-v4-pro": {"entree": 10, "sortie": 5}}
    activite = {"modeles": {"claude-sonnet-5-5": {"entree": 3_000_000, "sortie": 0}, "deepseek-v4-pro": {"entree": 10, "sortie": 5}},
                "echanges": {"reponses": 2, "collegues": {"lea": {"reponses": 2, "modeles": lea}}}}
    c = couts(activite, Tarifs.model_validate({"modeles": {"claude-sonnet-5-5": {"entree": 3, "sortie": 15}}}))
    assert c["total"] == 9.0 and c["collegues"] == {"lea": 3.0}  # déjà compté dans le total, montré à part
    assert c["sans_tarif"] == ["deepseek-v4-pro"]


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
        maintenant = time.time() * 1000
        for v in e.values():
            v["conteneur"] = {"demarre": False, "alertes": [
                {"quand": maintenant - 9 * 86400 * 1000, "quoi": "transmission", "message": "trop ancienne", "resolue": None},
                {"quand": maintenant - 3600 * 1000, "quoi": "demarrage", "message": "secret manquant", "resolue": maintenant - 60_000},
                {"quand": maintenant - 60 * 1000, "quoi": "transmission", "message": "conteneur arrêté", "resolue": None},
            ]}
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
    # le début de la période, arrondi à 5 minutes pour que des lectures rapprochées tombent dans la mémoire de la porte
    assert (ident, chemin) == ("exemple", "") and params["depuis"] % 300 == 0
    assert 0 <= (time.time() - 30 * 86400) - params["depuis"] < 300


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


def test_megga_ne_lit_jamais_une_conversation(atelier):
    """MEGGA suit la santé et les chiffres, jamais ce qui se dit (20.11.2026) : refusé avant toute lecture de la porte."""
    t = atelier
    avant = len(t.porte.suivis)
    for route in ("/atelier/clients/exemple/conversations", f"/atelier/clients/exemple/conversations/{MOI}"):
        r = t.get(route, headers=MEGGA)
        assert r.status_code == 403 and "ne se lisent que par lui" in r.text
    assert len(t.porte.suivis) == avant
    assert t.get("/atelier/clients/exemple/suivi", headers=MEGGA).status_code == 200  # les chiffres, oui
    assert t.get("/atelier/clients/inconnu-x/conversations", headers=MEGGA).status_code == 404  # un client inconnu reste inconnu


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
    assert sorted(genres) == ["conteneur_demarrage", "conteneur_transmission", "ecart", "tour_echec"]  # la panne de 9 jours est hors période
    assert a == sorted(a, key=lambda x: x["quand"], reverse=True)
    par_genre = {x["genre"]: x for x in a}
    assert par_genre["conteneur_demarrage"]["resolue"] is not None  # réglée : la console peut l'afficher comme telle
    assert par_genre["conteneur_transmission"]["resolue"] is None
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

    porte = Muette()
    t = TestClient(creer_atelier({"ADMIN_TOKEN": ADMIN, "DATABASE_URL": f"sqlite:///{tmp_path}/a.db"}, porte=porte))
    nouveau_client(t)
    r = t.get("/atelier/clients/exemple/suivi", headers=MEGGA)
    assert r.status_code == 502 and r.json()["details"]["statut"] == 503
    assert r.json()["erreur"] == "suivi indisponible : le conteneur du client ne répond pas"


@pytest.mark.parametrize("statut, texte, message", [
    (401, "refusé", "le conteneur refuse la lecture (jeton interne : le jeton d'administration a-t-il changé ?)"),
    (503, '{"erreur":"suivi indisponible"}', "le conteneur répond, mais sa base n'est pas branchée"),
    (0, "sans réponse (ReadTimeout)", "la porte n'a pas répondu"),
    (500, "boum", "réponse inattendue du conteneur (500)"),
])
def test_les_erreurs_du_conteneur_sont_distinguees(tmp_path, statut, texte, message):
    class Panne(PorteSuivie):
        async def suivi(self, ident, chemin="", **params):
            from atelier.porte import PorteErreur

            raise PorteErreur(statut, texte)

    t = TestClient(creer_atelier({"ADMIN_TOKEN": ADMIN, "DATABASE_URL": f"sqlite:///{tmp_path}/a.db"}, porte=Panne()))
    nouveau_client(t)
    r = t.get("/atelier/clients/exemple/suivi", headers=MEGGA)
    assert r.json()["erreur"] == f"suivi indisponible : {message}"
    assert r.status_code == (504 if statut == 0 else 502)


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


@pytest.mark.parametrize("moteur", ["sqlite"] + (["postgres"] if __import__("os").environ.get("TEST_POSTGRES_URL") else []))
def test_le_suivi_sur_les_deux_bases(moteur, tmp_path):
    """Tours, fil, journal et réglages, sur SQLite comme sur Postgres (la base de chaque client et celle de l'atelier)."""
    import os
    import random

    from noyau.suivi import message_lisible

    personne = "+4179" + "".join(random.choices("0123456789", k=8))  # base partagée sous Postgres
    futur = 4_000_000_000.0
    if moteur == "sqlite":
        agent, url = agent_et_base(tmp_path)
    else:
        url = os.environ["TEST_POSTGRES_URL"]
        agent = construire(lire("clients/exemple.yaml"), stockage.base_agno(url), {"ANTHROPIC_API_KEY": "x", "DEEPSEEK_API_KEY": "y"},
                           principal=ModeleCompte(id="claude-sonnet-5-5", provider="Anthropic"))
    lecture, fil, journal, reglages = stockage.Suivi(url), stockage.Fil(url), stockage.Journal(url), stockage.Reglages(url)
    cle = f"essai-{personne[1:]}"
    try:
        avant = time.time() - 5
        asyncio.run(agent.arun("Bonjour", user_id=personne, session_id=personne))
        tours = [t for t in lecture.tours(avant) if t["personne"] == personne]
        assert len(tours) == 1 and tours[0]["modeles"][0]["input_tokens"] == 1000  # les métriques seules, lues par JSON
        assert personne in [c["personne"] for c in lecture.conversations(500)]
        assert [m["texte"] for m in lecture.messages(personne)] == ["Bonjour", "Bonjour, ici votre agent d'essai."]

        fil.noter(personne, "recu", "texte", "Ma clé sk-ant-api03-abcdefghijklmnopqrstuv", 1.0)
        fil.noter(personne, "envoye", "rappel", "Rappel : visite", 2.0)
        assert [(m["sens"], m["genre"]) for m in fil.messages(personne)] == [("recu", "texte"), ("envoye", "rappel")]
        assert "sk-ant" not in message_lisible(fil.messages(personne)[0])["texte"]
        assert {"personne": personne, "messages": 2, "derniere": 2.0} in fil.conversations(500) and not fil.vide()

        journal.noter("tour_echec", 1, "RuntimeError", futur)
        journal.noter("voix_caracteres", 300, "", futur)
        assert journal.totaux(futur - 1) == {"tour_echec": {"nombre": 1, "quantite": 1.0}, "voix_caracteres": {"nombre": 1, "quantite": 300.0}}
        assert [a["genre"] for a in journal.alertes(futur - 1)] == ["tour_echec"]

        reglages.ecrire(cle, {"devise": "CHF"})
        reglages.ecrire(cle, {"devise": "EUR"})
        assert reglages.lire(cle) == {"devise": "EUR"}
    finally:
        # Base partagée : on n'y laisse rien, même en cas d'échec (l'essai d'export relit toute la base).
        from sqlalchemy import delete as supprimer

        with stockage.moteur(url).begin() as c:
            c.execute(supprimer(fil._t).where(fil._t.c.personne == personne))
            c.execute(supprimer(journal._t).where(journal._t.c.quand >= futur - 1))
            c.execute(supprimer(reglages._t).where(reglages._t.c.cle == cle))
            runs = lecture._runs()
            if runs is not None:
                c.execute(supprimer(runs).where(runs.c.user_id == personne))
            schema = "ai." if moteur == "postgres" else ""
            c.execute(stockage.text(f"DELETE FROM {schema}agno_sessions WHERE user_id = :p"), {"p": personne})


def test_le_journal_garde_les_delais_et_les_reponses_lentes(tmp_path):
    from test_app import FauxAgent

    from noyau.suivi import resumer
    from noyau.whatsapp import Entrant

    j = stockage.Journal(f"sqlite:///{tmp_path}/d.db")
    c = Conversations(lire("clients/exemple.yaml"), FauxAgent(), FauxExpediteur(), attente=0.01, journal=j)
    tour_complet(c, MOI, [Entrant(id="w1", de=MOI, texte="Bonjour", envoye=time.time(), genre="text")])
    t = j.totaux(0)
    assert t["delai_lecture"]["nombre"] == 1 and t["delai_reponse"]["nombre"] == 1 and "reponse_lente" not in t
    # un message resté deux cents secondes : lu et répondu en retard, noté comme lent, sans texte ni numéro
    tour_complet(c, MOI, [Entrant(id="w2", de=MOI, texte="Mon secret", envoye=time.time() - 200, genre="text")])
    t = j.totaux(0)
    assert t["delai_reponse"]["nombre"] == 2 and t["reponse_lente"]["nombre"] == 1 and t["delai_lecture"]["quantite"] >= 200
    lentes = [a for a in j.alertes(0) if a["genre"] == "reponse_lente"]
    assert len(lentes) == 1 and "lecture" in lentes[0]["detail"] and "secret" not in json.dumps(lentes) and MOI not in json.dumps(lentes)
    d = resumer(lire("clients/exemple.yaml"), [], t, 0, 0)["delais"]
    assert d["lentes"] == 1 and d["reponse"]["nombre"] == 2 and d["lecture"]["moyenne"] >= 100
    assert resumer(lire("clients/exemple.yaml"), [], {}, 0, 0)["delais"] == {
        "lecture": {"nombre": 0, "moyenne": None}, "reponse": {"nombre": 0, "moyenne": None}, "lentes": 0}
