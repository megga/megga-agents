"""Lot 5 : les modèles par métier (gabarits) et les erreurs en français clair."""

import pytest
from fastapi.testclient import TestClient

from atelier import gabarits, regles
from atelier.app import creer
from noyau.config import Config
from test_lot5 import ADMIN, MEGGA, FaussePorte, FauxModele, conf_exemple, jeton_client, nouveau_client

IDENTITE = {"id": "agence-lac", "entreprise": "Agence du Lac", "zone": "europe", "numero_id": "100000000000042"}


@pytest.fixture
def atelier(tmp_path):
    porte = FaussePorte()
    modele = FauxModele()
    t = TestClient(creer({"ADMIN_TOKEN": ADMIN, "DATABASE_URL": f"sqlite:///{tmp_path}/a.db", "ESSAIS_DIR": str(tmp_path / "essais")},
                         porte=porte, principal_essai=modele))
    t.porte, t.modele = porte, modele
    return t


def test_chaque_gabarit_donne_un_agent_complet():
    for g in gabarits.lister():
        conf = Config.model_validate(gabarits.nouvelle_config(g["id"], IDENTITE, "Lea"))
        assert conf.nom_agent == "Lea" and conf.metier == g["metier"] and conf.voix.voix
        assert regles.manques(conf) == []  # prêt à essayer et à mettre en service tel quel
        for texte in (conf.consignes, conf.ton, g["titre"], g["description"]):
            assert not any(c in texte for c in "\u2014\u2013\u00b7")


def test_le_client_choisit_un_metier_et_un_prenom(atelier):
    """Créé par MEGGA d'après un gabarit, réglé par le client d'après un autre, essayé, mis en service."""
    t = atelier
    r = t.post("/atelier/clients", headers=MEGGA, json={"gabarit": "generaliste", "client": IDENTITE, "nom_agent": "Lea"})
    assert r.status_code == 201, r.text
    client = jeton_client(t, "agence-lac")
    assert [g["id"] for g in t.get("/atelier/gabarits", headers=client).json()["gabarits"]] == ["generaliste", "immobilier"]

    v2 = t.post("/atelier/clients/agence-lac/gabarit", headers=client, json={"gabarit": "immobilier", "nom_agent": "Iris"})
    assert v2.status_code == 201, v2.text
    c = v2.json()["config"]
    assert (c["metier"], c["nom_agent"], c["entreprise"], c["whatsapp"]["numero_id"]) == ("immobilier", "Iris", "Agence du Lac", "100000000000042")
    assert "agence immobilière" in c["consignes"] and v2.json()["manques"] == [] and v2.json()["auteur"] == "client"

    assert t.post("/atelier/clients/agence-lac/versions/2/essai", headers=client, json={"message": "Bonjour"}).status_code == 200
    r = t.post("/atelier/clients/agence-lac/versions/2/activer", headers=client)
    assert r.status_code == 200 and t.porte.activations[-1][2]["nom_agent"] == "Iris"


def test_le_gabarit_garde_ce_qui_tient_au_client_et_a_megga(atelier):
    t = atelier
    nouveau_client(t, modeles={"principal": "claude-opus-5-5", "secours": None}, catalogue="https://agence.example/flux.json")
    r = t.post("/atelier/clients/exemple/gabarit", headers=MEGGA, json={"gabarit": "immobilier"})
    c = r.json()["config"]
    assert c["modeles"]["principal"] == "claude-opus-5-5" and c["nom_agent"] == "Alix"  # sans prénom donné, il reste
    assert c["outils"] == ["immobilier"]  # le catalogue est branché : le pack reste actif
    autre = jeton_client(t)
    nouveau_client(t, id="voisin", whatsapp={"numero_id": "100000000000077"})
    assert t.post("/atelier/clients/voisin/gabarit", headers=autre, json={"gabarit": "immobilier"}).status_code == 404


def test_refus_en_clair(atelier):
    t = atelier
    r = t.post("/atelier/clients", headers=MEGGA, json={"gabarit": "boulangerie", "client": IDENTITE, "nom_agent": "Lea"})
    assert r.status_code == 400 and r.json()["erreur"] == "Choisissez un modèle : généraliste, immobilier."
    r = t.post("/atelier/clients", headers=MEGGA, json={"gabarit": "generaliste", "client": {"id": "x1"}, "nom_agent": "Lea"})
    assert r.json()["erreur"] == "Il manque : entreprise, zone, numero_id."
    assert t.post("/atelier/clients", headers=jeton_client_cree(t), json={"gabarit": "generaliste", "client": IDENTITE}).status_code == 403


def jeton_client_cree(t):
    nouveau_client(t)
    return jeton_client(t)


@pytest.mark.parametrize("changements, champ, message", [
    ({"nom_agent": "L" * 41}, "nom_agent", "Le prénom doit faire 40 caractères au plus."),
    ({"nom_agent": ""}, "nom_agent", "Donnez un prénom à votre agent."),
    ({"voix": "pas une voix !"}, "voix.voix", "Choisissez une voix dans la liste."),
    ({"metier": "boulanger"}, "metier", "Choisissez un métier : general ou immobilier."),
    ({"outils": ["immobilier"]}, "", "Ces outils ne vont pas avec ce métier : immobilier."),
    ({"outils": ["fax"]}, "outils", "Cet outil n'existe pas."),
    ({"ton": "vif \u2014 et drôle"}, "ton", "Pas de tiret long ni de point médian."),
    ({"ton": "x" * 201}, "ton", "Le ton doit faire 200 caractères au plus."),
])
def test_erreurs_du_client_en_francais(atelier, changements, champ, message):
    t = atelier
    client = jeton_client_cree(t)
    r = t.post("/atelier/clients/exemple/valider", headers=client, json={"changements": changements})
    assert r.status_code == 422
    assert r.json()["details"][0] == {"champ": champ, "message": message}


def test_erreurs_de_megga_en_francais(atelier):
    t = atelier
    r = t.post("/atelier/clients", headers=MEGGA, json={"config": conf_exemple(zone="lune", couleur="bleu")})
    details = {d["champ"]: d["message"] for d in r.json()["details"]}
    assert details == {"zone": "Choisissez une zone : suisse, europe, etats-unis ou client.", "couleur": "Réglage inconnu."}
    r = t.post("/atelier/clients", headers=MEGGA, json={"config": {**conf_exemple(), "whatsapp": {"numero_id": "abc"}}})
    assert r.json()["details"] == [{"champ": "whatsapp.numero_id", "message": "L'identifiant du numéro WhatsApp : des chiffres seulement."}]
    r = t.put("/atelier/tarifs", headers=MEGGA, json={"modeles": {"claude-sonnet-5-5": {"entree": -1, "sortie": 3}}})
    assert r.json()["details"] == [{"champ": "modeles.claude-sonnet-5-5.entree", "message": "La valeur doit être d'au moins 0."}]
    for message in [d["message"] for d in r.json()["details"]] + list(details.values()):
        assert "\u2014" not in message and "\u00b7" not in message
