"""Le mot du matin (16.11.2026) : chaque jour à l'heure réglée, un message d'encouragement à chaque gestionnaire."""

import datetime as dt
import json
from zoneinfo import ZoneInfo

import httpx
import pytest

from noyau import config as configuration, stockage
from noyau.roles import Personnes, lire_gestionnaires
from packs.immobilier.annonces import Services
from packs.immobilier.bonjour import SECOURS, Bonjour, prochain, propre
from packs.immobilier.gestion import Gestion
from test_lot7_2 import CONF, GREG, FauxExp, FauxSite, Tour, run

Z = ZoneInfo("Europe/Zurich")


def heure(j, h, m=0):
    return dt.datetime(2026, 11, j, h, m, tzinfo=Z).timestamp()


class Claude:
    def __init__(self, texte="Bonjour ! Belle journée de lundi, pleine de soleil et de belles visites. Je suis avec toi ☀️"):
        self.texte, self.appels = texte, []

    async def _texte(self, systeme, contenu, maximum):
        self.appels.append((systeme, contenu))
        if isinstance(self.texte, Exception):
            raise self.texte
        return self.texte


@pytest.fixture
def monde(tmp_path):
    url = f"sqlite:///{tmp_path}/b.db"
    exp = FauxExp()
    s = Services(Gestion(CONF.gestion, "cle", transport=httpx.MockTransport(FauxSite())),
                 Personnes(CONF, lire_gestionnaires(json.dumps({GREG: "greg@agence.ch"}))), stockage.Medias(url), stockage.Etats(url), exp,
                 None, (), None, None, None, "Four Seasons Properties", assistante=Claude(), bonjour="08:00")
    return Bonjour(s), s, exp


def test_la_configuration():
    assert CONF.bonjour == "08:00"
    with pytest.raises(Exception):
        configuration.Config.model_validate({**CONF.model_dump(mode="json"), "bonjour": "8h"})


def test_l_heure_du_mot():
    assert prochain(heure(16, 7), "08:00", "Europe/Zurich") == heure(16, 8)
    assert prochain(heure(16, 8), "08:00", "Europe/Zurich") == heure(17, 8)


def test_chaque_matin_un_mot(monde):
    b, s, exp = monde
    assert run(b.echeance(heure(16, 7))) == heure(16, 8) and exp.envois == []
    assert run(b.echeance(heure(16, 8, 1))) == heure(17, 8)
    assert exp.envois == [("texte", GREG, "Bonjour ! Belle journée de lundi, pleine de soleil et de belles visites. Je suis avec toi ☀️")]
    systeme, contenu = s.assistante.appels[0]
    assert "lundi 16 novembre" in contenu and "bonne humeur" in systeme
    run(b.echeance(heure(16, 12)))
    assert len(exp.envois) == 1  # une fois par jour
    # Le lendemain, Claude reçoit le mot d'hier pour ne pas se répéter.
    run(b.echeance(heure(17, 8, 1)))
    assert "Belle journée de lundi" in s.assistante.appels[1][0] and len(exp.envois) == 2


def test_reveille_trop_tard_pas_de_bonjour_a_midi(monde):
    b, s, exp = monde
    run(b.echeance(heure(16, 7)))
    assert run(b.echeance(heure(16, 12))) == heure(17, 8) and exp.envois == []


def test_sans_claude_une_phrase_de_secours(monde):
    b, s, exp = monde
    s.assistante = Claude(RuntimeError("panne"))
    run(b.echeance(heure(16, 7)))
    run(b.echeance(heure(16, 8, 1)))
    assert exp.envois[0][2] in SECOURS
    s.assistante = Claude("\u2014 # liste")  # illisible : la phrase de secours
    run(b.echeance(heure(17, 8, 1)))
    assert exp.envois[1][2] in SECOURS


def test_on_l_arrete_ou_on_le_deplace(monde):
    b, s, exp = monde
    (outil,) = b.outils()
    assert "arrêté" in run(outil(False, Tour(GREG, "t1")))
    run(b.echeance(heure(16, 7)))
    run(b.echeance(heure(16, 8, 1)))
    assert exp.envois == []
    assert "7 h 30" in run(outil(True, Tour(GREG, "t2"), heure="07:30"))
    assert run(b.echeance(heure(16, 9))) == heure(17, 7, 30)
    with pytest.raises(ValueError, match="HH:MM"):
        run(outil(True, Tour(GREG, "t3"), heure="7h"))
    with pytest.raises(ValueError, match="gestionnaires"):
        run(outil(True, Tour("+41790000099", "t4")))


def test_le_mot_est_propre():
    assert propre("Bonjour \u2014 belle journée à toi, pleine de joie !") == "Bonjour, belle journée à toi, pleine de joie !"
    assert propre("court") is None and propre("# Titre\n- liste de choses à faire aujourd'hui") is None
    for t in SECOURS:
        assert propre(t) == t and "—" not in t and "·" not in t


# Relecture du 16.11.2026

class Conversations:
    def __init__(self, dernier, modele=False):
        import contextlib
        import types

        self._dernier, self.envois, self.journal = dernier, [], []
        self.conf = types.SimpleNamespace(modeles_meta={"bonjour": object()} if modele else {})
        self.contacts = types.SimpleNamespace(dernier=lambda personne: self._dernier)
        self.entre_les_tours = lambda personne: contextlib.nullcontext()

    async def envoyer_de_soi_meme(self, personne, messages, usage, variables=None, langue="", garder=True):
        self.envois.append((personne, messages[0]["texte"], usage, garder))
        return "libre"

    def noter_journal(self, genre, quantite=1, detail=""):
        self.journal.append((genre, detail))


def test_hors_des_24_heures_rien_ne_part_et_claude_n_est_pas_appele(monde):
    import time as t

    b, s, exp = monde
    s.conversations = Conversations(dernier=t.time() - 3 * 86400)
    assert run(b.envoyer(GREG, heure(16, 8))) is None
    assert s.assistante.appels == [] and s.conversations.envois == [] and s.conversations.journal[0][0] == "bonjour_attente"
    assert s.etats.lire(GREG, "bonjour_derniers") is None
    s.conversations = Conversations(dernier=t.time() - 3600)  # Greg a écrit il y a une heure
    assert run(b.envoyer(GREG, heure(16, 8))) and s.conversations.envois[0][2:] == ("bonjour", False)
    s.conversations = Conversations(dernier=None, modele=True)  # un modèle Meta « bonjour » réglé : il part
    assert run(b.envoyer(GREG, heure(17, 8)))


def test_changer_l_heure_ne_donne_pas_un_second_mot_le_meme_jour(monde):
    b, s, exp = monde
    (outil,) = b.outils()
    run(b.echeance(heure(16, 7)))
    run(b.echeance(heure(16, 8, 1)))
    assert len(exp.envois) == 1
    run(outil(True, Tour(GREG, "t1"), heure="09:00"))
    assert run(b.echeance(heure(16, 8, 30))) == heure(17, 9)
    run(b.echeance(heure(16, 9, 1)))
    assert len(exp.envois) == 1


def test_le_mot_tient_a_la_consigne():
    assert propre("Bonjour ! Quelle belle journée 🌞🏡✨ pour faire de belles visites.") is None  # trois émojis
    assert propre("Bonjour ! Prêt pour une belle journée pleine de rencontres ?") is None  # une question
    assert propre("Voici ton mot du jour : belle journée à toi, pleine de joie.") is None
    assert propre("Bonjour aux courtier·ère·s, belle journée pleine de joie.") is None
    assert propre("Bonjour ! Belle journée à toi, pleine de joie et de beaux projets ☀️")


def test_hors_des_24_heures_le_modele_porte_le_mot(monde):
    b, s, exp = monde
    s.conversations = Conversations(dernier=None, modele=True)
    vus = []

    async def envoyer(personne, messages, usage, variables=None, langue="", garder=True):
        vus.append((usage, variables, garder))
        return "modele"

    s.conversations.envoyer_de_soi_meme = envoyer
    run(b.envoyer(GREG, heure(16, 8)))
    (usage, variables, garder), = vus
    assert usage == "bonjour" and garder is False and variables[0].startswith("Belle journée de lundi") and not variables[0].endswith(".")
    assert CONF.modeles_meta["bonjour"].nom == "fsp_agent_bonjour"
