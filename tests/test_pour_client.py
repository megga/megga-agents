"""La console agit au nom d'un client (son espace client) : avec ses droits de client, jamais ceux de MEGGA."""

import pytest
from fastapi.testclient import TestClient

from atelier.app import creer
from test_lot5 import ADMIN, MEGGA, FaussePorte, FauxModele

A = {"id": "agence-a", "entreprise": "Agence A", "zone": "europe", "numero_id": "100000000000091"}
B = {"id": "agence-b", "entreprise": "Agence B", "zone": "europe", "numero_id": "100000000000092"}


@pytest.fixture
def t(tmp_path):
    t = TestClient(creer({"ADMIN_TOKEN": ADMIN, "DATABASE_URL": f"sqlite:///{tmp_path}/a.db", "ESSAIS_DIR": str(tmp_path / "e")},
                         porte=FaussePorte(), principal_essai=FauxModele()))
    for c in (A, B):
        assert t.post("/atelier/clients", headers=MEGGA, json={"gabarit": "generaliste", "client": c, "nom_agent": "Lea"}).status_code == 201
    return t


def pour(client):
    return {**MEGGA, "x-megga-client": client}


def test_au_nom_d_un_client_les_droits_du_client(t):
    assert [c["id"] for c in t.get("/atelier/clients", headers=pour("agence-a")).json()["clients"]] == ["agence-a"]
    assert t.get("/atelier/clients/agence-b", headers=pour("agence-a")).status_code == 404
    r = t.post("/atelier/clients", headers=pour("agence-a"), json={"gabarit": "generaliste", "client": {**A, "id": "autre"}, "nom_agent": "X"})
    assert r.status_code == 403
    r = t.post("/atelier/clients/agence-a/versions", headers=pour("agence-a"), json={"changements": {"consignes": "autre chose"}})
    assert r.status_code == 403 and "réservés à MEGGA" in r.text
    r = t.post("/atelier/clients/agence-a/versions", headers=pour("agence-a"), json={"changements": {"nom_agent": "Rose"}})
    assert r.status_code == 201
    assert t.post("/atelier/clients/agence-a/jetons", headers=pour("agence-a")).status_code == 403
    assert t.get("/atelier/releves", headers=pour("agence-a")).status_code == 403


def test_l_en_tete_ne_vaut_qu_avec_le_jeton_de_megga(t):
    assert t.get("/atelier/clients", headers={"x-megga-client": "agence-a"}).status_code == 401
    assert t.get("/atelier/clients", headers=pour("Agence A!")).status_code == 400
    assert t.get("/atelier/clients/inconnu", headers=pour("inconnu")).status_code == 404
    assert len(t.get("/atelier/clients", headers=MEGGA).json()["clients"]) == 2  # sans l'en-tête : MEGGA
