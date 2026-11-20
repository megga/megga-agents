"""Le relevé chiffré (20.11.2026) : des chiffres jour par jour, jamais un texte, un nom ni un numéro.

Le conteneur le calcule (/interne/releve), la porte le range dans son annuaire, l'atelier le rassemble pour la
console de MEGGA (GET /atelier/releves), avec les coûts et les agents silencieux.
"""

import asyncio
import json
import time

import pytest
from fastapi.testclient import TestClient

from atelier.app import creer as creer_atelier
from atelier.couts import Tarifs
from atelier.releves import SILENCE_S, rassembler
from noyau import stockage
from noyau.suivi import jours_utc
from test_lot5 import ADMIN, MEGGA, FaussePorte, jeton_client, nouveau_client
from test_suivi import INTERNE, MOI, ecrire, serveur

# Dans le conteneur du client


def test_jours_utc():
    midi = 1_795_000_000 // 86400 * 86400 + 43200
    jours = jours_utc(2, midi)
    assert [j for j, _, _ in jours] == [time.strftime("%Y-%m-%d", time.gmtime(midi - 86400)), time.strftime("%Y-%m-%d", time.gmtime(midi))]
    assert jours[1][1] == midi - 43200 and jours[1][2] == midi + 43200 and jours[0][2] == jours[1][1]


def test_le_releve_n_a_que_des_chiffres(tmp_path):
    app, url = serveur(tmp_path)
    with TestClient(app) as t:
        assert t.get("/interne/releve").status_code == 401
        ecrire(t, app, "Bonjour, je cherche un appartement", "w1")
        ecrire(t, app, "Ma clé est sk-ant-api03-abcdefghijklmnopqrstuv", "w2")
        stockage.Journal(url).noter("tour_echec", detail="RuntimeError")
        r = t.get("/interne/releve", headers=INTERNE).json()
    aujourdhui = time.strftime("%Y-%m-%d", time.gmtime())
    assert r["forme"] == 1 and list(r["jours"]) == [time.strftime("%Y-%m-%d", time.gmtime(time.time() - 86400)), aujourdhui]
    j = r["jours"][aujourdhui]
    assert (j["tours"], j["personnes"], j["tours_en_echec"]) == (2, 1, 1)
    assert j["modeles"]["claude-sonnet-5-5"]["entree"] == 2000 and j["journal"]["tour_echec"] == {"nombre": 1, "quantite": 1.0}
    assert r["jours"][min(r["jours"])]["tours"] == 0 and r["derniere_activite"] > time.time() - 60
    texte = json.dumps(r)
    for prive in (MOI, MOI[1:], "Bonjour", "appartement", "sk-ant", "RuntimeError"):
        assert prive not in texte  # ni numéro, ni message, ni détail technique du journal


def test_le_releve_borne_ses_jours(tmp_path):
    app, _ = serveur(tmp_path)
    with TestClient(app) as t:
        assert len(t.get("/interne/releve?jours=1", headers=INTERNE).json()["jours"]) == 1
        assert len(t.get("/interne/releve?jours=99", headers=INTERNE).json()["jours"]) == 3


# Dans l'atelier

AUJOURDHUI = time.strftime("%Y-%m-%d", time.gmtime())
CHIFFRES = {"tours": 10, "tours_api": 2, "tours_en_echec": 1, "secours": 1, "personnes": 4,
            "modeles": {"claude-sonnet-5-5": {"fournisseur": "Anthropic", "tours": 10, "entree": 1_000_000, "sortie": 0,
                                              "cache_lecture": 0, "cache_ecriture": 0},
                        "inconnu-1": {"fournisseur": None, "tours": 1, "entree": 5, "sortie": 5, "cache_lecture": 0, "cache_ecriture": 0}},
            "journal": {}, "delais": {"lecture": {"nombre": 0, "moyenne": None}, "reponse": {"nombre": 0, "moyenne": None}, "lentes": 0}}


def brut(releve_le_ms, version=1, actif=1):
    return {"depuis": AUJOURDHUI, "jours": 7, "clients": [
        {"id": "exemple", "zone": "europe", "actif": actif, "version": version, "releve_le": releve_le_ms,
         "etat": {"demarre": True, "pannes_en_cours": []}, "jours": {AUJOURDHUI: CHIFFRES}},
    ]}


def test_rassembler_couts_ecart_et_silence():
    tarifs = Tarifs.model_validate({"modeles": {"claude-sonnet-5-5": {"entree": 3, "sortie": 15}}})
    maintenant = time.time()
    connus = {"exemple": {"entreprise": "Exemple SA", "version_en_service": 1}}
    c = rassembler(brut(maintenant * 1000 - 60_000), tarifs, connus, maintenant)["clients"][0]
    assert c["entreprise"] == "Exemple SA" and not c["ecart"] and not c["silencieux"]
    assert c["jours"][AUJOURDHUI]["cout"] == 3.0 and c["totaux"]["cout"] == 3.0 and c["totaux"]["tours"] == 10
    assert c["totaux"]["sans_tarif"] == ["inconnu-1"]  # un modèle sans tarif est dit, pas compté à zéro sans le dire
    vieux = rassembler(brut((maintenant - SILENCE_S - 60) * 1000, version=2), tarifs, connus, maintenant)["clients"][0]
    assert vieux["silencieux"] and vieux["ecart"]
    assert rassembler(brut(None), tarifs, connus, maintenant)["clients"][0]["silencieux"]
    assert not rassembler(brut(None, actif=0), tarifs, connus, maintenant)["clients"][0]["silencieux"]


class PorteReleves(FaussePorte):
    def __init__(self, **k):
        super().__init__(**k)
        self.demandes = []

    async def releves(self, jours):
        self.demandes.append(jours)
        return brut(time.time() * 1000)


@pytest.fixture
def atelier(tmp_path):
    porte = PorteReleves()
    t = TestClient(creer_atelier({"ADMIN_TOKEN": ADMIN, "DATABASE_URL": f"sqlite:///{tmp_path}/a.db"}, porte=porte))
    t.porte = porte
    nouveau_client(t)
    t.post("/atelier/clients/exemple/versions/1/activer", headers=MEGGA, json={"forcer": True})
    return t


def test_les_releves_pour_megga_seulement(atelier):
    t = atelier
    r = t.get("/atelier/releves?jours=30", headers=MEGGA)
    assert r.status_code == 200 and t.porte.demandes == [30]
    c = r.json()["clients"][0]
    assert c["id"] == "exemple" and c["version_en_service"] == 1 and not c["ecart"]
    assert t.get("/atelier/releves", headers=jeton_client(t)).status_code == 403
    for faux in ("0", "401", "abc"):
        assert t.get(f"/atelier/releves?jours={faux}", headers=MEGGA).status_code == 400


def test_porte_http_releves():
    import httpx

    from atelier.porte import Porte

    vus = []

    def repondre(r: httpx.Request):
        vus.append((str(r.url), r.headers["authorization"]))
        return httpx.Response(200, json={"clients": []})

    p = Porte("https://porte.essai", "jeton", transport=httpx.MockTransport(repondre))
    assert asyncio.run(p.releves(7)) == {"clients": []}
    assert vus == [("https://porte.essai/admin/releves?jours=7", "Bearer jeton")]
