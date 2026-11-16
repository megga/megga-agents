"""Lot 10 : les modèles d'accueil par métier."""

import asyncio
import json

import pytest
from test_lot6_pilote import MEGGA, activer, canal, nouvelle_version, releve_signe  # noqa: F401 (canal : fixture)

from noyau import config as configuration
from noyau import connecteurs, stockage, version
from noyau.app import creer
from pilote import service as pilote_service
from test_lot9_3 import Contexte, FaussesConversations

NOUVEAUX = ("sante", "hotellerie", "juridique", "commerce", "fiduciaire", "garage")
CONF = configuration.lire("clients/exemple.yaml").model_dump(mode="json")


def test_les_huit_metiers():
    assert configuration.NOMS_METIERS == ("general", "immobilier", *NOUVEAUX)
    assert configuration.METIERS_D_AVANT == ("general", "immobilier")
    for m in NOUVEAUX:
        assert configuration.METIERS[m] == configuration.OUTILS_DES_ROLES[m] == configuration.GROUPES_DU_NOYAU
        assert configuration.lire({**CONF, "metier": m, "outils": ["connaissances", "leads"]}).metier == m
        with pytest.raises(Exception):  # le pack immobilier ne va qu'au métier immobilier
            configuration.lire({**CONF, "metier": m, "outils": ["immobilier"], "catalogue": "demo:megga-estates"})


def test_la_carte_donne_les_metiers():
    assert version.carte()["metiers"] == list(configuration.NOMS_METIERS)
    assert "metiers" in pilote_service.SANTE  # le pilote le remonte


def test_un_metier_que_l_image_ne_connait_pas():
    from atelier.app import metier_inconnu

    assert metier_inconnu({"version": "0.3.0", "schema": 2}, "sante")  # sans metiers : une image d'avant
    assert not metier_inconnu({"version": "0.3.0", "schema": 2}, "immobilier")
    assert not metier_inconnu({"version": "0.4.0", "metiers": ["general", "sante"]}, "sante")
    assert metier_inconnu({"version": "0.4.0", "metiers": ["general"]}, "garage")
    for inconnu in (None, {}, {"ok": False, "erreur": "injoignable"}):
        assert not metier_inconnu(inconnu, "sante")  # on ne sait pas : l'installation jugera
    for illisible in ("sante", ["sante", 3], None):
        assert metier_inconnu({"version": "0.4.0", "metiers": illisible}, "sante")


def test_le_releve_garde_les_metiers(canal):
    c = canal
    agent = {"ok": True, "version": "0.4.0", "schema": 2, "metiers": ["general", "sante"]}
    assert releve_signe(c, {"pilotage": "suivi", "etat": {"agent": agent}}).status_code == 200
    gardes = c.t.get("/atelier/clients/exemple/installation", headers=MEGGA).json()
    assert gardes["installation"]["agent"]["metiers"] == ["general", "sante"]


def test_l_activation_refuse_un_metier_inconnu(canal):
    c = canal
    v = nouvelle_version(c.t, metier="sante")
    avant = {"ok": True, "version": "0.3.0", "schema": 2}  # une image d'avant : pas de metiers
    assert releve_signe(c, {"pilotage": "suivi", "etat": {"agent": avant}}).status_code == 200
    r = activer(c.t, v)
    assert r.status_code == 409 and "ne connaît pas le métier sante" in r.json()["erreur"], r.text
    recente = {**avant, "version": "0.4.0", "metiers": ["general", "immobilier", "sante"]}
    c.horloge.t += 10
    assert releve_signe(c, {"pilotage": "suivi", "etat": {"agent": recente}}).status_code == 200
    assert activer(c.t, v).status_code == 200


# L'équipe prévenue d'une demande


@pytest.fixture
def url(tmp_path):
    return f"sqlite:///{tmp_path}/client.db"


def leads(url, gestionnaires=("+41790000099", "+41790000098"), **k):
    l = connecteurs.Leads(stockage.Leads(url), agent="Alix", gestionnaires=gestionnaires, **k)
    l.conversations = FaussesConversations()
    return l


def test_une_demande_previent_l_equipe_apres_le_tour(url):
    l = leads(url)
    r = asyncio.run(l.outils()[0]("Un rendez-vous pour le service de ma Clio", 4, Contexte("+41790000001"), delai="jeudi", nom="M. Favre"))
    assert r == "Demande 1 enregistrée ; l'équipe est prévenue."
    assert len(l.conversations.apres) == 2 and l.conversations.envois == []   # rien avant la fin du tour
    for f in l.conversations.apres:
        asyncio.run(f())
    assert [(qui, usage) for qui, _, usage in l.conversations.envois] == [("+41790000099", "lead"), ("+41790000098", "lead")]
    texte = l.conversations.envois[0][1][0]["texte"]
    assert all(m in texte for m in ("Clio", "jeudi", "M. Favre", "+41790000001", "4/5"))


def test_sans_equipe_ou_alerte_coupee_rien_ne_part(url):
    for l in (leads(url, gestionnaires=()), leads(url, alerte=False)):
        assert asyncio.run(l.outils()[0]("Une table pour 4", 3, Contexte("+41790000001"))).endswith("enregistrée pour l'équipe.")
        assert l.conversations.apres == []


def test_l_alerte_masque_les_secrets_nomme_l_api_et_saute_l_auteur(url):
    l = leads(url)
    asyncio.run(l.outils()[0]("Devis, ma clé sk-abcdefghijklmnopqrstuvwxyz", 2, Contexte("api:dossier:42")))
    for f in l.conversations.apres:
        asyncio.run(f())
    texte = l.conversations.envois[0][1][0]["texte"]
    assert "sk-" not in texte and "[masqué]" in texte and "api:dossier:42" in texte and "+api" not in texte
    l2 = leads(url)
    asyncio.run(l2.outils()[0]("Une villa", 5, Contexte("+41790000099")))   # un gestionnaire note lui-même
    for f in l2.conversations.apres:
        asyncio.run(f())
    assert [qui for qui, _, _ in l2.conversations.envois] == ["+41790000098"]


def test_le_client_coupe_l_alerte_dans_sa_configuration():
    assert configuration.lire({**CONF, "outils": ["leads"], "leads": {"alerte": False}}).leads.alerte is False
    assert configuration.lire({**CONF, "outils": ["leads"]}).leads is None   # sans leads : l'alerte vaut vrai


def test_l_app_branche_les_conversations(url):
    from test_app import FauxAgent, FauxExpediteur

    l = connecteurs.Leads(stockage.Leads(url))
    app = creer({"CLIENT_CONFIG": json.dumps({**CONF, "outils": ["leads"]}), "DATABASE_URL": url, "INTERNE_TOKEN": "interne"},
                agent=FauxAgent(), expediteur=FauxExpediteur(), leads=l)
    assert l.conversations is app.state.conversations
