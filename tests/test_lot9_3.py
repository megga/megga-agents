"""Lot 9.3 : le transfert vers un humain (noyau/reprises.py)."""

import asyncio
import contextlib
import json
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from noyau import config as configuration, reprises, stockage
from noyau.agent import construire
from noyau.app import creer

CONF = configuration.lire("clients/exemple.yaml").model_dump(mode="json")
# Le transfert demande le rôle gestionnaire : c'est à l'équipe que l'agent passe la main.
CONF_T = {**CONF, "transfert": True, "roles": {"gestionnaire": {}, "visiteur": {}}}


@pytest.fixture
def url(tmp_path):
    return f"sqlite:///{tmp_path}/client.db"


class Contexte:
    def __init__(self, user_id):
        self.user_id = user_id


class FaussesConversations:
    def __init__(self, echec=False):
        self.envois, self.apres, self.fil, self.echec = [], [], [], echec

    def apres_le_tour(self, personne, f):
        self.apres.append(f)

    async def envoyer_de_soi_meme(self, personne, messages, usage, variables=None, langue="", garder=True):
        if self.echec:
            raise RuntimeError("Meta 503")
        self.envois.append((personne, messages, usage))
        return "libre"

    def _noter_fil(self, personne, sens, genre, texte):
        self.fil.append((personne, sens, genre, texte))

    async def _numeroter(self, personne, media, rang):
        return 3


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
    assert r.a_relire("+41790000001")["relue"] == 0 and r.a_relire("+41790000001")["relue"] == 1  # relue pendant un jour


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


def test_pas_de_transfert_sans_personne_pour_la_prendre(url):
    t = transfert(url, gestionnaires=())
    r = asyncio.run(outil(t, "passer_la_main")("humain", "x", Contexte("+41790000001")))
    assert "pas possible" in r and stockage.Reprises(url).lister() == []
    with pytest.raises(ValueError, match="demande le rôle gestionnaire"):
        configuration.lire({**CONF, "transfert": True})
    assert configuration.lire(CONF_T).transfert is True


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


def test_un_relais_en_echec_laisse_la_main_a_l_humain(url):
    t = transfert(url)
    asyncio.run(outil(t, "passer_la_main")("humain", "r", Contexte("+41790000001")))
    asyncio.run(t.choix("+41790000099", "gestionnaire", "tr:1:prendre"))
    t.conversations.echec = True  # Meta en panne
    assert asyncio.run(t.garde("+41790000001", [Message("Allô ?")])) is True
    assert t.conversations.fil == [("+41790000001", "recu", "texte", "Allô ?")]  # noté une fois


def test_un_media_pendant_la_reprise_est_numerote(url):
    t = transfert(url)
    asyncio.run(outil(t, "passer_la_main")("humain", "r", Contexte("+41790000001")))
    asyncio.run(t.choix("+41790000099", "gestionnaire", "tr:1:prendre"))
    photo = SimpleNamespace(genre="image", id="m1", type="image/jpeg", nom="")
    asyncio.run(t.garde("+41790000001", [Message("la fissure", media=photo)]))
    assert t.conversations.fil[-1] == ("+41790000001", "recu", "image", "[média 3] la fissure")
    assert t.conversations.envois[-1][1] == [{"texte": "Message de +41790000001 (conversation 1) : [média 3] la fissure"}]


def test_seul_celui_qui_l_a_prise_la_rend(url):
    t = transfert(url, ("+41790000099", "+41790000098"))
    asyncio.run(outil(t, "passer_la_main")("humain", "r", Contexte("+41790000001")))
    asyncio.run(t.choix("+41790000099", "gestionnaire", "tr:1:prendre"))
    assert "seule la personne qui l'a prise" in asyncio.run(t.choix("+41790000098", "gestionnaire", "tr:1:rendre"))
    assert "seule la personne qui l'a prise" in asyncio.run(outil(t, "rendre_la_main", "gestionnaire")(1, Contexte("+41790000098")))
    assert asyncio.run(t.choix("+41790000099", "gestionnaire", "tr:1:rendre")) == "La conversation 1 est rendue à l'agent."
    asyncio.run(outil(t, "passer_la_main")("humain", "r", Contexte("+41790000002")))
    asyncio.run(t.choix("+41790000099", "gestionnaire", "tr:2:prendre"))
    assert asyncio.run(t.rendre(2))["etat"] == "rendue"  # la console


def test_une_conversation_rendue_ne_repasse_pas_prise(url):
    r = stockage.Reprises(url)
    r.ouvrir("+41790000001", "visiteur", "m", "r")
    r.prendre(1, "+41790000099")
    vrai, rendue = r._e, []

    class Moteur:  # la console rend la conversation entre la lecture et l'écriture de l'équipe
        @contextlib.contextmanager
        def begin(self):
            with vrai.begin() as c:
                class Connexion:
                    def execute(self, q, *a):
                        sortie = c.execute(q, *a)
                        if getattr(q, "is_select", False) and not rendue:
                            rendue.append(c.execute(stockage.update(r._t).values(etat="rendue")))
                        return sortie
                yield Connexion()

    r._e = Moteur()
    assert r.ecrite(1, "console") is None
    r._e = vrai
    assert r.une(1)["etat"] == "rendue"


def test_a_l_echeance_la_personne_et_le_gestionnaire_sont_prevenus(url, monkeypatch):
    t = transfert(url)
    passer = outil(t, "passer_la_main")
    asyncio.run(passer("humain", "r", Contexte("+41790000001")))
    asyncio.run(passer("humain", "r", Contexte("+41790000002")))
    asyncio.run(t.choix("+41790000099", "gestionnaire", "tr:2:prendre"))
    maintenant = time.time()
    assert asyncio.run(t.echeance(maintenant)) == pytest.approx(maintenant + 24 * 3600, abs=60)
    assert t.conversations.envois == []
    plus_tard = maintenant + 73 * 3600  # elle ne réécrit pas : l'échéance prévient quand même
    monkeypatch.setattr(stockage.time, "time", lambda: plus_tard)
    assert asyncio.run(t.echeance(plus_tard)) is None
    assert [(qui, usage) for qui, _, usage in t.conversations.envois] == [
        ("+41790000001", "reprise_fin"), ("+41790000002", "reprise_fin"), ("+41790000099", "reprise_fin")]
    assert t.conversations.envois[0][1] == [{"texte": reprises.EXCUSES["fr"]}]
    assert "conversation 2 avec +41790000002 revient à Alix" in t.conversations.envois[2][1][0]["texte"]
    contexte = asyncio.run(t.contexte("+41790000001"))
    assert "mot d'excuse" in contexte and "excuse-toi" not in contexte


def test_l_agent_relit_les_dix_derniers_messages_de_l_equipe_dans_l_ordre(url):
    t = transfert(url)
    asyncio.run(outil(t, "passer_la_main")("humain", "r", Contexte("+41790000001")))
    fil, debut = stockage.Fil(url), time.time()
    for i in range(1, 13):
        fil.noter("+41790000001", "envoye", "reprise", f"message {i:02}", debut + i)
    stockage.Reprises(url).rendre(1)
    contexte = asyncio.run(t.contexte("+41790000001"))
    assert "message 01" not in contexte and "message 02" not in contexte
    positions = [contexte.index(f"message {i:02}") for i in range(3, 13)]
    assert positions == sorted(positions)


def test_l_equipe_repond_puis_rend_la_main(url):
    t = transfert(url)
    asyncio.run(outil(t, "passer_la_main")("réclamation", "r", Contexte("+41790000001")))
    repondre = outil(t, "repondre_en_reprise", "gestionnaire")
    assert asyncio.run(repondre(1, "Bonjour, ici Claire de l'agence.", Contexte("+41790000099"))) == {"id": 1, "envoi": "libre"}
    assert t.conversations.envois[-1] == ("+41790000001", [{"texte": "Bonjour, ici Claire de l'agence.", "usage": "reprise"}], "reprise")
    assert stockage.Reprises(url).une(1)["par"] == "+41790000099"
    assert "rendue" in asyncio.run(outil(t, "rendre_la_main", "gestionnaire")(1, Contexte("+41790000099")))
    with pytest.raises(ValueError, match="plus en cours"):
        asyncio.run(repondre(1, "encore", Contexte("+41790000099")))
    assert "l'équipe te l'a rendue" in asyncio.run(t.contexte("+41790000001"))


# Dans le vrai tour : un webhook WhatsApp


def app_transfert(url, exp=None, **conf):
    from test_app import SECRET, FauxAgent, FauxExpediteur

    agent = FauxAgent()
    app = creer({"CLIENT_CONFIG": json.dumps({**CONF_T, **conf}), "DATABASE_URL": url, "META_APP_SECRET": SECRET,
                 "INTERNE_TOKEN": "interne"}, agent=agent, agents={"gestionnaire": agent, "visiteur": agent},
                expediteur=exp or FauxExpediteur(), attente=0.01, seuil_regard=30)
    return app, agent


def ecrire(t, app, texte, ident):
    from test_app import attendre, corps, signe

    c = corps(texte, ident)
    assert t.post("/whatsapp", content=c, headers=signe(c)).status_code == 200
    t.portal.call(attendre(app))


def test_le_webhook_d_une_conversation_reprise_ne_reveille_pas_l_agent(url):
    from test_app import attendre

    app, agent = app_transfert(url)
    stockage.Reprises(url).ouvrir("+41790000000", "visiteur", "humain", "r")
    interne = {"x-megga-interne": "interne"}
    with TestClient(app) as t:
        ecrire(t, app, "Vous êtes là ?", "wamid.1")
        assert agent.appels == []  # l'agent ne répond pas : l'équipe a la main
        assert [(m["sens"], m["texte"]) for m in stockage.Fil(url).messages("+41790000000")] == [("recu", "Vous êtes là ?")]
        # l'échéance de la conversation oubliée est attendue (/interne/rappels)
        assert t.post("/interne/rappels", headers=interne).json()["prochain"] == pytest.approx(time.time() + 24 * 3600, abs=60)
        # la console prend, répond, rend
        assert t.get("/interne/suivi/reprises", params={"etat": "ouverte"}, headers=interne).json()["reprises"][0]["id"] == 1
        assert t.post("/interne/reprises/1", json={"action": "prendre"}, headers=interne).json() == {"id": 1, "etat": "prise"}
        assert t.post("/interne/reprises/1", json={"action": "message", "texte": ""}, headers=interne).status_code == 400
        assert t.post("/interne/reprises/1", json={"action": "message", "texte": "Ici l'agence."}, headers=interne).json()["id"] == 1
        t.portal.call(attendre(app))
        ecrire(t, app, "Et pour la visite ?", "wamid.2")
        assert t.post("/interne/reprises/1", json={"action": "rendre"}, headers=interne).json()["etat"] == "rendue"
        assert t.post("/interne/reprises/1", json={"action": "rendre"}, headers=interne).status_code == 409
        assert t.post("/interne/reprises/1", json={"action": "voler"}, headers=interne).status_code == 400
    # l'agent reprend : il lit ce que l'équipe a dit, et ce que la personne a écrit depuis, pendant plus d'un tour
    t = reprises.Transfert(stockage.Reprises(url), stockage.Fil(url))
    for _ in range(2):
        contexte = asyncio.run(t.contexte("+41790000000"))
        assert "« Ici l'agence. »" in contexte and "« Et pour la visite ? »" in contexte and "« Vous êtes là ? »" not in contexte


def test_la_reponse_de_l_equipe_hors_des_24_heures_va_au_contexte(url):
    from test_app import FauxExpediteur

    class Expediteur(FauxExpediteur):
        async def modele(self, vers, nom, langue, variables):
            self.envois.append((vers, nom))

    exp = Expediteur()
    app, _ = app_transfert(url, exp, modeles_meta={"reprise": {"nom": "fsp_agent_reprise"}})
    stockage.Contacts(url).noter("+41790000000", time.time() - 3 * 86400)  # hors des 24 heures
    stockage.Reprises(url).ouvrir("+41790000000", "visiteur", "humain", "r")
    interne = {"x-megga-interne": "interne"}
    with TestClient(app) as t:
        assert t.post("/interne/reprises/1", json={"action": "message", "texte": "Ici l'agence."}, headers=interne).json()["envoi"] == "modele"
        assert exp.envois == [("+41790000000", "fsp_agent_reprise")]
        t.post("/interne/reprises/1", json={"action": "rendre"}, headers=interne)
        ecrire(t, app, "Afficher", "wamid.1")  # la réponse gardée part
    assert ("+41790000000", "Ici l'agence.") in exp.envois
    assert "« Ici l'agence. »" in asyncio.run(reprises.Transfert(stockage.Reprises(url), stockage.Fil(url)).contexte("+41790000000"))


def test_sans_transfert_pas_de_routes(url):
    from test_app import FauxAgent, FauxExpediteur

    app = creer({"CLIENT_CONFIG": json.dumps(CONF), "DATABASE_URL": url, "INTERNE_TOKEN": "interne"},
                agent=FauxAgent(), expediteur=FauxExpediteur())
    assert TestClient(app).get("/interne/suivi/reprises", headers={"x-megga-interne": "interne"}).status_code == 409


def test_la_consigne_va_aux_agents_qui_passent_la_main(url):
    conf = configuration.lire(CONF_T)
    from test_lot9_1 import ModeleOutil

    def fixes(agent):
        return agent.instructions.base if hasattr(agent.instructions, "base") else agent.instructions

    agent = construire(conf, None, {}, principal=ModeleOutil(), outils=transfert(url).outils_pour(None))
    assert reprises.CONSIGNE in fixes(agent)
    equipe = construire(conf, None, {}, principal=ModeleOutil(), outils=transfert(url).outils_pour("gestionnaire"),
                        nom_role="gestionnaire")
    assert reprises.CONSIGNE not in fixes(equipe)
    essai = construire(conf, None, {}, principal=ModeleOutil(), outils=[])  # l'essai de l'atelier n'a pas l'outil
    assert reprises.CONSIGNE not in fixes(essai)


def test_l_atelier_prend_repond_et_rend(tmp_path):
    from atelier.app import creer as creer_atelier
    from test_lot5 import ADMIN, CLE_PILOTAGE_TEXTE, MEGGA, FaussePorte, FauxModele, jeton_client, nouveau_client

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
    assert t.post("/atelier/clients/exemple/reprises/3", json={"action": "rendre"}, headers=client).status_code == 200
    assert porte.actions == [(3, {"action": "prendre", "texte": ""}), (3, {"action": "message", "texte": "Bonjour"}),
                             (3, {"action": "rendre", "texte": ""})]
    assert porte.lus == [("/reprises", "ouverte")]
    # le client active lui-même le transfert, s'il a des gestionnaires pour prendre la main
    r = t.post("/atelier/clients/exemple/versions", headers=client, json={"changements": {"transfert": True}})
    assert r.status_code == 422 and "demande le rôle gestionnaire" in r.json()["details"][0]["message"]
    assert t.post("/atelier/clients/exemple/versions", headers=MEGGA,
                  json={"changements": {"roles": CONF_T["roles"]}}).status_code == 201
    r = t.post("/atelier/clients/exemple/versions", headers=client, json={"changements": {"transfert": True}})
    assert r.status_code == 201 and r.json()["config"]["transfert"] is True
