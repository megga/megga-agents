"""Le pays de chaque client (20.11.2026) : un réglage de l'atelier pour la carte du monde, réglé par MEGGA seul."""

import pytest
from fastapi.testclient import TestClient

from atelier.app import creer as creer_atelier
from atelier.pays import CODES
from test_lot5 import ADMIN, MEGGA, FaussePorte, jeton_client, nouveau_client


@pytest.fixture
def atelier(tmp_path):
    t = TestClient(creer_atelier({"ADMIN_TOKEN": ADMIN, "DATABASE_URL": f"sqlite:///{tmp_path}/a.db"}, porte=FaussePorte()))
    nouveau_client(t)
    return t


def test_codes_iso():
    assert {"CH", "FR", "ES", "AE", "US"} <= CODES and len(CODES) == 250 and all(len(c) == 2 for c in CODES)


def test_regler_lire_retirer(atelier):
    t = atelier
    assert t.get("/atelier/clients/exemple", headers=MEGGA).json()["pays"] is None
    r = t.put("/atelier/clients/exemple/pays", headers=MEGGA, json={"pays": "ch"})
    assert r.status_code == 200 and r.json() == {"client": "exemple", "pays": "CH"}
    assert t.get("/atelier/clients/exemple", headers=MEGGA).json()["pays"] == "CH"
    assert [c["pays"] for c in t.get("/atelier/clients", headers=MEGGA).json()["clients"]] == ["CH"]
    assert t.put("/atelier/clients/exemple/pays", headers=MEGGA, json={"pays": None}).json()["pays"] is None
    assert t.get("/atelier/clients", headers=MEGGA).json()["clients"][0]["pays"] is None


def test_refus(atelier):
    t = atelier
    assert t.put("/atelier/clients/exemple/pays", headers=MEGGA, json={"pays": "ZZ"}).status_code == 422
    assert t.put("/atelier/clients/exemple/pays", headers=MEGGA, json={"pays": 41}).status_code == 422
    assert t.put("/atelier/clients/inconnu/pays", headers=MEGGA, json={"pays": "CH"}).status_code == 404
    assert t.put("/atelier/clients/exemple/pays", headers=jeton_client(t), json={"pays": "CH"}).status_code == 403
