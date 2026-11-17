"""L'audit du 17.11.2026 (des réponses fausses ou incohérentes d'un agent, surtout dans ses vocaux) : chaque cause, et sa
correction. L'agent redisait une capacité perdue pendant une panne, ne voyait pas les rappels qu'il avait envoyés,
saluait un gestionnaire du prénom d'un autre ; la réécriture pour l'oral inventait ; les fiches envoyées n'étaient
pas dans le suivi."""

import asyncio
import json
import time

from fastapi.testclient import TestClient

from noyau import accueil as accueils
from noyau import config as configuration
from noyau import stockage
from noyau.agent import modele
from noyau.tour import Conversations
from packs.immobilier.travail import capacites
from test_lot2 import Agent, Exp, FauxContacts, conf, entrant, tourner
from test_lot7_1 import GREG

MOI = "+41790000000"
NOMS = {"greg": "Greg", "gregory": "Greg", "julien": "Julien"}


def test_la_temperature_de_l_oral(monkeypatch):
    """La réécriture pour la voix prend la température réglée (vide : celle du fournisseur) ; jamais avec la réflexion."""
    from noyau import app

    assert modele("deepseek-flash", {"DEEPSEEK_API_KEY": "x"}, temperature=0.3).temperature == 0.3
    assert modele("deepseek-flash", {"DEEPSEEK_API_KEY": "x"}).temperature is None
    assert modele("claude-haiku-5-5", {"ANTHROPIC_API_KEY": "x"}, temperature=0.3).temperature == 0.3
    assert modele("claude-sonnet-5-5", {"ANTHROPIC_API_KEY": "x"}, reflexion=True, temperature=0.3).temperature is None
    vus = []
    monkeypatch.setattr(app, "modele", lambda nom, cles, **k: vus.append((nom, k)))
    monkeypatch.setattr("agno.agent.Agent.__init__", lambda self, **k: None)
    c = configuration.lire("clients/four-seasons-properties.yaml")
    app._reecriture(c, {})
    assert vus == [("deepseek-flash", {"temperature": c.modeles.temperature_oral})]
    assert c.modeles.temperature_oral is not None and c.modeles.temperature_oral <= 0.5


def test_un_message_envoye_de_soi_meme_reste_dans_le_contexte(tmp_path):
    """Un rappel parti à l'heure entre dans le Contexte deux jours : l'agent ne le croit plus raté, ne le refait pas."""
    url = f"sqlite:///{tmp_path}/r.db"
    rappels, etats = stockage.Rappels(url), stockage.Etats(url)
    exp = Exp()
    c = Conversations(conf(whatsapp={"numero_id": "100000000000001"}), Agent(), exp, contacts=FauxContacts(time.time() - 60),
                      rappels=rappels, etats=etats)
    rappels.ajouter(MOI, time.time() - 5, "appeler M. Martin")
    asyncio.run(c.envoyer_rappels_echus(time.time()))
    assert any("appeler M. Martin" in str(j) for j in exp.journal)
    ctx = asyncio.run(c.contexte(MOI))
    assert "envoyé de toi-même" in ctx and "le rappel" in ctx and "appeler M. Martin" in ctx and "ne les reprogramme pas" in ctx
    # Plus de deux jours après : il sort du Contexte.
    etats.ecrire(MOI, "de_soi", [{"quand": time.time() - 49 * 3600, "genre": "rappel", "texte": "ancien"}])
    assert "envoyé de toi-même" not in asyncio.run(c.contexte(MOI))
    # Les huit derniers seulement.
    for i in range(12):
        asyncio.run(c._retenir_envoi(MOI, "differe", f"message {i}"))
    gardes = etats.lire(MOI, "de_soi")
    assert len(gardes) == 8 and gardes[-1]["texte"] == "message 11"


def test_oublier_une_conversation(tmp_path):
    """Après une panne qui lui a fait dire des choses fausses, la conversation repart à neuf ; le fil reste."""
    url = f"sqlite:///{tmp_path}/o.db"
    etats = stockage.Etats(url)

    class Suite(Agent):
        async def arun(self, texte, user_id=None, session_id=None, images=None):
            self.sessions = [*getattr(self, "sessions", []), session_id]
            return await super().arun(texte, user_id=user_id, session_id=session_id, images=images)

    agent = Suite("Bien reçu.")
    c = Conversations(conf(historique={"tours": 40, "inactivite": 12}), agent, Exp(), attente=0.01, etats=etats)
    asyncio.run(tourner(c, entrant("w1")))
    asyncio.run(c.oublier(MOI))
    asyncio.run(tourner(c, entrant("w2")))
    assert agent.sessions[0] == MOI and agent.sessions[-1].startswith(f"{MOI}:")
    assert etats.lire(MOI, "session")["id"] == agent.sessions[-1]


def test_qui_ecrit_d_apres_le_profil():
    """Un gestionnaire n'est plus salué du prénom d'un autre : le Contexte dit qui écrit, s'il le sait."""
    assert "C'est Julien qui t'écrit" in accueils.nom_connu("Julien Dupont", NOMS)
    assert "C'est Greg qui t'écrit" in accueils.nom_connu("Grégory Lyonnet", NOMS)
    assert accueils.nom_connu("JD", NOMS) == "" and accueils.nom_connu(None, NOMS) == ""
    assert accueils.nom_connu("Julien et Greg", NOMS) == ""  # deux prénoms : rien plutôt qu'un faux
    c = Conversations(conf(roles={"gestionnaire": {"noms_du_profil": NOMS}}), Agent(), Exp())
    c._roles[MOI], c._profils[MOI] = "gestionnaire", "Julien"
    assert "C'est Julien qui t'écrit" in asyncio.run(c.contexte(MOI))
    c._roles[MOI] = "visiteur"
    assert "qui t'écrit" not in asyncio.run(c.contexte(MOI))


def test_les_envois_des_outils_dans_le_fil(tmp_path):
    """Une fiche ou une vidéo envoyée par un outil entre dans le fil, que le suivi relit."""
    fil = stockage.Fil(f"sqlite:///{tmp_path}/f.db")
    c = Conversations(conf(), Agent(), Exp(), fil=fil)

    async def f():
        c.noter_envoi(MOI, "document", "villa-cologny-anonyme.pdf")
        while c.taches:
            await asyncio.gather(*list(c.taches), return_exceptions=True)

    asyncio.run(f())
    assert [(m["sens"], m["genre"], m["texte"]) for m in fil.messages(MOI)] == [("envoye", "document", "villa-cologny-anonyme.pdf")]


def test_les_capacites_disent_la_voix_sans_detour():
    c = configuration.lire("clients/four-seasons-properties.yaml")
    g = c.les_roles()["gestionnaire"]
    texte = capacites(c, g)
    assert "ma réponse part d'elle-même en vocal" in texte and "sans outil" in texte and "les partenaires" in texte
    sans_voix = c.model_copy(update={"voix": c.voix.model_copy(update={"voix": None})})
    assert "je réponds toujours par écrit" in capacites(sans_voix, g)


def test_les_routes_d_entretien(tmp_path):
    """Par la porte (jeton interne) : oublier une conversation, voir et annuler les rappels d'une personne."""
    from noyau.app import creer
    from test_lot7_1 import FSP_WA, GESTIONNAIRES, SECRET, AgentNomme, ExpediteurMedias

    url = f"sqlite:///{tmp_path}/e.db"
    rappels = stockage.Rappels(url)
    ident = rappels.ajouter(GREG, time.time() + 3600, "appeler")
    env = {"CLIENT_CONFIG": json.dumps(FSP_WA), "DATABASE_URL": url, "META_APP_SECRET": SECRET, "INTERNE_TOKEN": "interne",
           "GESTIONNAIRES": GESTIONNAIRES}
    app = creer(env, agent=AgentNomme("public"), agents={n: AgentNomme(n) for n in ("gestionnaire", "partenaire", "visiteur")},
                expediteur=ExpediteurMedias(), attente=0.01, rappels=rappels)
    h = {"x-megga-interne": "interne"}
    with TestClient(app) as t:
        assert t.post("/interne/oublier", json={"personne": GREG}).status_code == 401
        assert t.post("/interne/oublier", json={"personne": "greg"}, headers=h).status_code == 400
        assert t.post("/interne/oublier", json={"personne": GREG}, headers=h).json() == {"oubliee": True}
        assert t.get(f"/interne/rappels/{GREG}").status_code == 401
        liste = t.get(f"/interne/rappels/{GREG}", headers=h).json()["rappels"]
        assert [(r["id"], r["texte"]) for r in liste] == [(ident, "appeler")]
        assert t.post("/interne/rappels/annuler", json={"personne": GREG, "id": ident}, headers=h).json() == {"annule": True}
        assert t.get(f"/interne/rappels/{GREG}", headers=h).json() == {"rappels": []}
        assert t.post("/interne/rappels/annuler", json={"personne": GREG, "id": ident}, headers=h).json() == {"annule": False}


def test_la_configuration_de_four_seasons_apres_l_audit():
    """Les consignes de Four Seasons : toutes les langues, la voix, qui écrit ; l'oral qui n'ajoute rien."""
    c = configuration.lire("clients/four-seasons-properties.yaml")
    g = c.les_roles()["gestionnaire"]
    assert g.noms_du_profil.get("julien") == "Julien" and g.noms_du_profil.get("greg") == "Greg"
    assert "toutes les grandes langues" in g.consignes and "russe" in g.consignes
    assert "Il s'appelle Greg : appelle-le toujours Greg" not in g.consignes
    assert "sans dire d'où il vient" in c.oral.consignes
    brut = open("clients/four-seasons-properties.yaml", encoding="utf-8").read()
    assert "+41" not in brut and "@" not in brut
    json.dumps(c.model_dump(mode="json"))
