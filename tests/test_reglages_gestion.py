"""Les paramètres que Greg règle dans sa gestion (packs/immobilier/reglages.py) : posés par-dessus la version en service,
relus avant chaque tour, servis sans redémarrer ; jamais de panne pour un réglage."""

import asyncio
import json

import httpx
import pytest
from pydantic import ValidationError

from noyau import config as configuration
from packs.immobilier.gestion import Gestion
from packs.immobilier.reglages import ReglagesDeLaGestion, appliquer, appliquer_au_mieux

CONF = configuration.lire("clients/four-seasons-properties.yaml")


def run(coro):
    return asyncio.run(coro)


def test_les_reglages_se_posent_sur_la_version():
    c = appliquer(CONF, {"voix_modele": "eleven_multilingual_v2", "voix_vitesse": 0.9, "voix_stabilite": 0.5, "modele": "claude-opus-5-5",
                         "secours": None, "reactions": False, "humeur": "aucune", "bonjour": None,
                         "accueil": {"fr": "Bonjour, je suis Alix.", "en": "Hello, I'm Alix."}})
    assert (c.voix.modele, c.voix.vitesse, c.voix.stabilite) == ("eleven_multilingual_v2", 0.9, 0.5)
    assert c.voix.voix == CONF.voix.voix  # la voix d'Elise reste
    assert (c.modeles.principal, c.modeles.secours, c.modeles.jetons) == ("claude-opus-5-5", None, CONF.modeles.jetons)
    assert c.reactions is False and c.bonjour is None
    assert c.roles.gestionnaire.humeur == "aucune" and c.roles.partenaire.humeur == CONF.roles.partenaire.humeur
    assert c.roles.visiteur.accueil["fr"] == "Bonjour, je suis Alix." and c.roles.visiteur.accueil["en"] == "Hello, I'm Alix."
    assert c.roles.gestionnaire.consignes == CONF.roles.gestionnaire.consignes


def test_sans_reglage_la_version_reste():
    assert appliquer(CONF, {}) == CONF


def test_un_reglage_hors_bornes_ne_passe_pas():
    with pytest.raises(ValidationError):
        appliquer(CONF, {"voix_vitesse": 3})


def test_un_reglage_faux_n_emporte_pas_les_autres():
    c, refuses = appliquer_au_mieux(CONF, {"voix_vitesse": 3, "reactions": False, "accueil": {"fr": "Court"}})
    assert c.reactions is False and c.voix.vitesse == CONF.voix.vitesse and sorted(refuses) == ["accueil", "voix_vitesse"]


class Horloge:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def _reglages(reponses):
    """Une gestion qui rend tour à tour les réponses données (statut, corps), et le compte des appels."""
    appels = []

    def site(requete: httpx.Request):
        appels.append((requete.url.path, requete.headers.get("x-gestion-compte")))
        statut, corps = reponses[min(len(appels), len(reponses)) - 1]
        return httpx.Response(statut, content=json.dumps(corps))

    servies, horloge = [], Horloge()
    r = ReglagesDeLaGestion(Gestion(CONF.gestion, "cle", transport=httpx.MockTransport(site)), "gl@fourseasonsgroup.ch", CONF,
                            servies.append, horloge=horloge)
    return r, servies, appels, horloge


def test_servis_quand_ils_changent_seulement():
    r, servies, appels, horloge = _reglages([(200, {"reglages": {"reactions": False, "modifie": "x"}}),
                                             (200, {"reglages": {"reactions": False, "modifie": "y"}}),
                                             (200, {"reglages": {"reactions": True}})])
    run(r.rafraichir())
    assert appels == [("/api/gestion/alix/reglages", "gl@fourseasonsgroup.ch")] and servies[-1].reactions is False
    run(r.rafraichir())
    assert len(appels) == 1  # pas avant 30 secondes
    horloge.t += 31
    run(r.rafraichir())
    assert len(appels) == 2 and len(servies) == 1  # la même chose : rien de resservi
    horloge.t += 31
    run(r.rafraichir())
    assert len(servies) == 2 and servies[-1].reactions is True


def test_jamais_de_panne_pour_un_reglage():
    r, servies, appels, horloge = _reglages([(500, {"erreur": "panne"}), (200, {"reglages": {"voix_vitesse": 3}}), (404, {})])
    run(r.rafraichir())
    assert not servies
    horloge.t += 31
    run(r.rafraichir())
    assert servies[-1] == CONF  # refusé par la validation : l'agent reste tel quel
    horloge.t += 31
    run(r.rafraichir())
    horloge.t += 31
    run(r.rafraichir())
    assert len(appels) == 3  # sans la route (404), la gestion n'est redemandée qu'après dix minutes


def test_le_tour_attend_les_reglages_pendant_son_attente():
    from noyau.tour import Conversations
    from test_lot7_6 import FauxAgent
    from test_lot7_4 import FauxExp

    c = Conversations(CONF, FauxAgent(), FauxExp(), attente=0.01)
    vus = []

    async def avant():
        vus.append(c.conf.reactions)
        c.conf = appliquer(CONF, {"reactions": False})

    async def tour(personne, messages, role="public"):
        vus.append(c.conf.reactions)

    c.avant_le_tour, c._tour = avant, tour
    c._boites["+41790000001"] = type("B", (), {"messages": [object()], "role": "gestionnaire"})()
    run(c._attendre("+41790000001"))
    assert vus == [True, False]


def test_l_agent_sert_les_reglages_sans_redemarrer(tmp_path):
    from test_lot7_1 import FSP_WA, GESTIONNAIRES, AgentNomme, FauxExpediteur

    from noyau.app import creer

    env = {"CLIENT_CONFIG": json.dumps(FSP_WA), "DATABASE_URL": f"sqlite:///{tmp_path}/g.db", "GESTION_CLE": "cle",
           "GESTIONNAIRES": GESTIONNAIRES, "ELEVENLABS_API_KEY": "cle-voix"}
    app = creer(env, agent=AgentNomme("public"), agents={n: AgentNomme(n) for n in ("gestionnaire", "partenaire", "visiteur")},
                expediteur=FauxExpediteur())
    c = app.state.conversations
    lecteur = c.avant_le_tour.__self__
    assert lecteur.compte == "greg@agence.ch"

    def site(requete):
        return httpx.Response(200, content=json.dumps({"reglages": {"voix_vitesse": 0.8, "reactions": False}}))

    lecteur.gestion = Gestion(lecteur.base.gestion, "cle", transport=httpx.MockTransport(site))
    run(c.avant_le_tour())
    assert c.conf.reactions is False and app.state.config.reactions is False
    assert c.voie.reglages.vitesse == 0.8
    assert c.agents["gestionnaire"].nom == "gestionnaire"  # agents donnés par l'essai : gardés, les modèles n'ont pas changé


def test_sans_gestion_rien_n_est_relu(tmp_path):
    from test_lot7_1 import FSP_WA, AgentNomme, FauxExpediteur

    from noyau.app import creer

    app = creer({"CLIENT_CONFIG": json.dumps(FSP_WA), "DATABASE_URL": f"sqlite:///{tmp_path}/g.db"}, agent=AgentNomme("public"),
                agents={n: AgentNomme(n) for n in ("gestionnaire", "partenaire", "visiteur")}, expediteur=FauxExpediteur())
    assert app.state.conversations.avant_le_tour is None


def test_un_autre_modele_refait_les_agents(tmp_path):
    from test_lot7_1 import FSP_WA, GESTIONNAIRES, FauxExpediteur

    from noyau.app import creer

    env = {"CLIENT_CONFIG": json.dumps(FSP_WA), "DATABASE_URL": f"sqlite:///{tmp_path}/g.db", "GESTION_CLE": "cle",
           "GESTIONNAIRES": GESTIONNAIRES, "ANTHROPIC_API_KEY": "cle-claude", "DEEPSEEK_API_KEY": "cle-deepseek"}
    app = creer(env, expediteur=FauxExpediteur())
    c = app.state.conversations
    avant = c.agents["gestionnaire"]
    assert avant.model.id == "claude-sonnet-5-5"
    lecteur = c.avant_le_tour.__self__
    lecteur.gestion = Gestion(lecteur.base.gestion, "cle", transport=httpx.MockTransport(
        lambda r: httpx.Response(200, content=json.dumps({"reglages": {"modele": "claude-opus-5-5"}}))))
    run(c.avant_le_tour())
    assert c.agents["gestionnaire"] is not avant and c.agents["gestionnaire"].model.id == "claude-opus-5-5"
    assert c.agent.model.id == "claude-opus-5-5"
    nom = lambda o: getattr(o, "name", None) or getattr(o, "__name__", "")  # noqa: E731
    assert [nom(o) for o in c.agents["gestionnaire"].tools] == [nom(o) for o in avant.tools] and avant.tools
