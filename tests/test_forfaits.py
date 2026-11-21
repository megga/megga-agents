"""Les forfaits et les clients payants (20.11.2026) : catalogue, abonnement, enveloppe de conversations, marge."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from atelier.app import creer as creer_atelier
from atelier.forfaits import Abonnement, Catalogue, Forfait, debut_du_mois, prix_du_mois, vue
from test_alertes import PorteAlertes
from test_lot5 import ADMIN, MEGGA, jeton_client, nouveau_client
from test_releve import AUJOURDHUI

ESSENTIEL = {"id": "essentiel", "nom": "Essentiel", "prix_mensuel": 290, "conversations": 200, "remise_annuelle": 20,
             "recharge": {"conversations": 100, "prix": 120}}
CATALOGUE = {"devise": "USD", "multiplicateur": 3, "forfaits": [ESSENTIEL]}


def test_debut_du_mois():
    d = date(2026, 1, 31)
    assert debut_du_mois(d, date(2026, 1, 15)) == d  # avant le début : le début
    assert debut_du_mois(d, date(2026, 2, 28)) == date(2026, 2, 28)  # le 31 tombe au dernier jour de février
    assert debut_du_mois(d, date(2026, 3, 30)) == date(2026, 2, 28)
    assert debut_du_mois(d, date(2026, 3, 31)) == date(2026, 3, 31)
    assert debut_du_mois(date(2025, 12, 10), date(2026, 1, 5)) == date(2025, 12, 10)  # à cheval sur l'année


def test_prix_annuel_remise():
    f = Forfait.model_validate(ESSENTIEL)
    assert prix_du_mois(f, "mensuel") == 290 and prix_du_mois(f, "annuel") == 232


def test_catalogue_refuse_les_doublons():
    with pytest.raises(ValueError):
        Catalogue.model_validate({"forfaits": [ESSENTIEL, ESSENTIEL]})


def test_vue_enveloppe_revenu_marge():
    cat = Catalogue.model_validate(CATALOGUE)
    abos = {"a": Abonnement(forfait="essentiel", statut="actif", debut="2026-11-01", seuil_recharge=50),
            "b": Abonnement(forfait="essentiel", statut="essai", debut="2026-11-10")}
    releve = {"devise": "USD", "clients": [
        {"id": "a", "entreprise": "A SA", "jours": {"2026-10-31": {"personnes": 99, "cout": 9}, "2026-11-02": {"personnes": 120, "cout": 30},
                                                   "2026-11-03": {"personnes": 60, "cout": 15}}},
        {"id": "b", "entreprise": "B SA", "jours": {"2026-11-12": {"personnes": 5, "cout": 1}}}]}
    recharges = [{"client": "a", "quand": 1793750400.0, "conversations": 100, "prix": 120}]  # 2026-11-04 UTC
    v = vue(cat, abos, recharges, releve, date(2026, 11, 20))
    a, b = v["clients"]
    assert a["mois"]["debut"] == "2026-11-01" and a["consommees"] == 180  # le 31 octobre est d'un autre mois
    assert a["enveloppe"] == 300 and a["reste"] == 120 and not a["proche"]
    assert a["revenu"] == 410 and a["cout"] == 45 and a["marge"] == 365
    assert b["revenu"] == 0 and b["consommees"] == 5  # en essai : rien n'est encaissé
    t = v["totaux"]
    assert t["actif"] == 1 and t["essai"] == 1 and t["revenu"] == 410 and t["cout"] == 46  # l'essai coûte aussi
    assert t["marge"] == 364
    # Un abonnement qui commence le mois prochain n'encaisse rien ce mois-ci.
    futur = {"c": Abonnement(forfait="essentiel", statut="actif", debut="2026-12-01")}
    assert vue(cat, futur, [], releve, date(2026, 11, 20))["clients"][0]["revenu"] == 0
    # Proche : sous le seuil choisi.
    abos["a"] = Abonnement(forfait="essentiel", statut="actif", debut="2026-11-01", seuil_recharge=150)
    assert vue(cat, abos, recharges, releve, date(2026, 11, 20))["clients"][0]["proche"]
    # Pas la même devise : aucune marge inventée.
    assert vue(cat, abos, recharges, {**releve, "devise": "CHF"}, date(2026, 11, 20))["totaux"]["marge"] is None


@pytest.fixture
def atelier(tmp_path):
    t = TestClient(creer_atelier({"ADMIN_TOKEN": ADMIN, "DATABASE_URL": f"sqlite:///{tmp_path}/a.db"}, porte=PorteAlertes()))
    nouveau_client(t)
    t.post("/atelier/clients/exemple/versions/1/activer", headers=MEGGA, json={"forcer": True})
    return t


def test_routes(atelier):
    t = atelier
    assert t.get("/atelier/forfaits", headers=MEGGA).json()["forfaits"] == []
    assert t.put("/atelier/forfaits", headers=MEGGA, json=CATALOGUE).status_code == 200
    abo = {"forfait": "essentiel", "statut": "actif", "debut": AUJOURDHUI}
    assert t.put("/atelier/clients/exemple/abonnement", headers=MEGGA, json={**abo, "forfait": "autre"}).status_code == 422
    assert t.put("/atelier/clients/exemple/abonnement", headers=MEGGA, json={**abo, "debut": "hier"}).status_code == 422
    assert t.put("/atelier/clients/exemple/abonnement", headers=MEGGA, json=abo).status_code == 200
    assert t.put("/atelier/forfaits", headers=MEGGA, json={**CATALOGUE, "forfaits": []}).status_code == 409  # encore pris
    assert t.post("/atelier/clients/exemple/recharges", headers=MEGGA, json={"conversations": 100, "prix": 120}).status_code == 201
    v = t.get("/atelier/abonnements", headers=MEGGA).json()
    c = v["clients"][0]
    assert v["releve_lisible"] and c["client"] == "exemple" and c["consommees"] == 4  # les personnes du jour
    assert c["enveloppe"] == 300 and c["revenu"] == 410 and c["recharges"]["nombre"] == 1
    assert t.delete("/atelier/clients/exemple/abonnement", headers=MEGGA).status_code == 200
    assert t.get("/atelier/abonnements", headers=MEGGA).json()["clients"] == []


def test_megga_seulement(atelier):
    t, client_ = atelier, jeton_client(atelier)
    assert t.get("/atelier/abonnements", headers=client_).status_code == 403
    assert t.put("/atelier/forfaits", headers=client_, json=CATALOGUE).status_code == 403
    assert t.put("/atelier/clients/exemple/abonnement", headers=client_, json={}).status_code == 403
    assert t.put("/atelier/clients/inconnu/abonnement", headers=MEGGA, json={}).status_code == 404
