import json
import time
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from noyau import config as configuration
from noyau import stockage
from noyau.app import outils_du_client
from packs.immobilier import Catalogue
from packs.immobilier import catalogue as module_catalogue
from packs.immobilier.outils import outils

DEMO = Path("packs/immobilier/demo/megga-estates.json")


@pytest.fixture
def demo():
    return Catalogue("demo:megga-estates")


def test_demo_valide_fictive_et_sans_four_seasons(demo):
    brut = json.loads(DEMO.read_text(encoding="utf-8"))
    assert brut["fictif"] is True and len(demo.biens()) == len(brut["biens"]) == 12
    texte = DEMO.read_text(encoding="utf-8").lower()
    for interdit in ("four seasons", "fsp", "greg", "cologny", "vandœuvres", "vandoeuvres", "marbella", "dubaï", "dubai", "\u2014", "\u2013", "\u00b7"):
        assert interdit not in texte, interdit
    assert all("fictif" in b.description for b in demo.biens())


def test_recherche(demo):
    assert {b.ref for b in demo.chercher(transaction="location")} == {"ME-106", "ME-107", "ME-110", "ME-112"}
    assert [b.ref for b in demo.chercher(communes=["lutry"], transaction="vente")] == ["ME-101"]
    assert "ME-103" in {b.ref for b in demo.chercher(budget_max=1_000_000, types=["chalet"])}  # prix sur demande gardé
    assert {b.ref for b in demo.chercher(transaction="vente", budget_max=2_000_000, chambres_min=3)} == {"ME-103", "ME-104"}
    assert {b.ref for b in demo.chercher(mots="vue lac piscine")} == {"ME-101", "ME-108"}
    assert [b.ref for b in demo.chercher(communes=["Saint Moritz", "saint-moritz"])] == ["ME-110"]


def test_outils(demo):
    chercher, voir = outils(demo)
    r = chercher(transaction="vente", communes="Lausanne, Lutry")
    assert r.startswith("2 bien(s)") and "ME-101" in r and "ME-102" in r and "CHF 6’850’000" in r
    assert "prix sur demande" in voir("me-103")
    assert voir("ZZZ") == "Aucun bien avec cette référence."
    assert chercher(communes="Atlantide") == "Aucun bien ne correspond à ces critères."
    with pytest.raises(ValueError):
        chercher(transaction="achat")
    assert "5 premiers" in chercher()


def test_flux_https_relu_et_garde_en_cas_de_panne():
    appels = {"n": 0}

    def repondre(r):
        appels["n"] += 1
        if appels["n"] == 1:
            return httpx.Response(200, json=[{"ref": "A1", "titre": "Bien A", "transaction": "vente", "commune": "Sion", "prix": 1},
                                             {"ref": "", "titre": "invalide", "transaction": "vente", "commune": "X"}])
        return httpx.Response(500)

    c = Catalogue("https://agence.exemple/biens.json", client=httpx.Client(transport=httpx.MockTransport(repondre)))
    assert [b.ref for b in c.biens()] == ["A1"]  # le bien invalide est écarté
    c._lu = time.time() - module_catalogue.RAFRAICHIR_S - 1
    assert [b.ref for b in c.biens()] == ["A1"]  # panne : la dernière version reste


def test_sources_refusees():
    for s in ("http://non-chiffre", "demo:../../etc", "fichier.json"):
        with pytest.raises(Exception):
            Catalogue(s)


def test_configuration_du_pack(tmp_path):
    d = configuration.lire("clients/megga-estates.yaml").model_dump()
    assert d["outils"] == ("immobilier",) and d["catalogue"] == "demo:megga-estates"
    for mauvais in ({"outils": ["inconnu"]}, {"catalogue": "http://x"}):
        with pytest.raises(ValidationError):
            configuration.lire({**d, **mauvais})
    conf = configuration.lire(d)
    noms = [f.__name__ for f in outils_du_client(conf, stockage.Rappels(f"sqlite:///{tmp_path}/r.db"))]
    assert noms == ["rappeler", "mes_rappels", "annuler_rappel", "chercher_biens", "voir_bien"]
    sans = configuration.lire({**d, "catalogue": None})
    with pytest.raises(RuntimeError):
        outils_du_client(sans, stockage.Rappels(f"sqlite:///{tmp_path}/r.db"))
