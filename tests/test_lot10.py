"""Lot 10 : les modèles d'accueil par métier."""

import pytest
from test_lot6_pilote import MEGGA, activer, canal, nouvelle_version, releve_signe  # noqa: F401 (canal : fixture)

from noyau import config as configuration
from noyau import version
from pilote import service as pilote_service

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
