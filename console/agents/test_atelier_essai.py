"""L'atelier d'essai local : le vrai atelier sur une porte simulée, ses six clients fictifs, son jeton.

Les essais ne dépendent pas de leur ordre : celui de la relance ne recharge pas le module, et ceux qui lisent l'app
prennent celle que la fixture a construite.
"""

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent))

JETON = "jeton-essai"
ENTETE = {"Authorization": f"Bearer {JETON}"}
CLIENTS = ["agence-essai", "boulangerie-essai", "chalet-essai", "fleuriste-essai", "garage-essai", "librairie-essai"]


def environnement(monkeypatch, dossier: Path) -> None:
    monkeypatch.setenv("ATELIER_DONNEES", str(dossier))
    monkeypatch.setenv("ATELIER_JETON", JETON)
    for k in ("ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY"):
        monkeypatch.delenv(k, raising=False)


@pytest.fixture(scope="module")
def essai(tmp_path_factory):
    """Un atelier d'essai pour les lectures de ce fichier (le peupler prend une seconde) : son module, son app, un client."""
    with pytest.MonkeyPatch.context() as m:
        environnement(m, tmp_path_factory.mktemp("atelier"))
        import atelier_essai

        module = importlib.reload(atelier_essai)  # son app, construite à l'import, dans ce dossier-ci
        app = module.app
        yield SimpleNamespace(module=module, app=app, t=TestClient(app, headers=ENTETE))


def clients(t: TestClient) -> dict[str, dict]:
    r = t.get("/atelier/clients")
    assert r.status_code == 200, r.text
    return {c["id"]: c for c in r.json()["clients"]}


def test_jeton_exige(essai):
    nu = TestClient(essai.app)
    assert nu.get("/atelier/clients").status_code == 401
    assert nu.get("/atelier/clients", headers={"Authorization": "Bearer faux"}).status_code == 401


def test_clients_fictifs(essai):
    c = clients(essai.t)
    assert sorted(c) == CLIENTS
    assert c["agence-essai"]["ecart"] is True and c["agence-essai"]["version_en_service"] == 2
    assert c["agence-essai"]["annuaire"]["version"] == 1
    assert c["boulangerie-essai"]["ecart"] is False
    assert (c["boulangerie-essai"]["entreprise"], c["boulangerie-essai"]["nom_agent"]) == ("Boulangerie des Essais", "Lou")
    assert c["garage-essai"]["annuaire"]["conteneur"]["demarre"] is False
    assert c["fleuriste-essai"]["annuaire"]["conteneur"]["demarre"] is False
    assert (c["librairie-essai"]["version_en_service"], c["librairie-essai"]["derniere_version"]) == (None, 1)


def test_conteneur_injoignable(essai):
    """Le suivi du fleuriste ne répond pas ; ses alertes, si : la panne gardée par la porte et « conteneur injoignable »."""
    t = essai.t
    assert t.get("/atelier/clients/fleuriste-essai/suivi?jours=7").status_code == 502
    assert t.get("/atelier/clients/fleuriste-essai/conversations").status_code == 502
    r = t.get("/atelier/clients/fleuriste-essai/alertes?jours=7")
    assert r.status_code == 200
    genres = {a["genre"]: a for a in r.json()["alertes"]}
    assert "conteneur_injoignable" in genres and genres["conteneur_transmission"]["resolue"] is None


def test_jamais_mis_en_service(essai):
    """La porte ne connaît pas la librairie (un brouillon seulement) : 404 au suivi ; l'atelier croirait son conteneur
    injoignable, ce que la console ne lit donc pas."""
    t = essai.t
    assert t.get("/atelier/clients/librairie-essai/suivi?jours=7").status_code == 404
    alertes = t.get("/atelier/clients/librairie-essai/alertes?jours=7").json()["alertes"]
    assert [a["genre"] for a in alertes] == ["conteneur_injoignable"]
    assert [v["etat"] for v in t.get("/atelier/clients/librairie-essai/versions").json()["versions"]] == ["brouillon"]


def test_vocaux_comme_le_moteur(essai):
    """Le moteur ne note pas vocal_dit : chaque vocal dit est un voix_caracteres (noyau/autour.py)."""
    journal = essai.t.get("/atelier/clients/boulangerie-essai/suivi?jours=7").json()["activite"]["journal"]
    assert "vocal_dit" not in journal
    assert journal["voix_caracteres"]["nombre"] > 0 and journal["voix_caracteres"]["quantite"] > journal["voix_caracteres"]["nombre"]


def test_alertes_du_garage(essai):
    t = essai.t
    alertes = t.get("/atelier/clients/garage-essai/alertes?jours=7").json()["alertes"]
    genres = [a["genre"] for a in alertes]
    assert "tour_echec" in genres and "envoi_refuse" in genres
    pannes = [a for a in alertes if a["genre"].startswith("conteneur_")]
    assert any(p["resolue"] is None for p in pannes) and any(p["resolue"] for p in pannes)
    assert t.get("/atelier/clients/boulangerie-essai/alertes?jours=30").json()["alertes"] == []


def test_installation_relevee(essai):
    t = essai.t
    r = t.get("/atelier/installations").json()
    chalet = {i["client"]: i for i in r["installations"]}["chalet-essai"]
    assert chalet["releve"] is not None and chalet["silencieuse"] is False and chalet["ecart"] is False
    assert r["cle_pilotage"] is True
    s = t.get("/atelier/clients/chalet-essai/suivi?jours=30").json()
    assert s["activite"]["tours"] > 0


def test_le_pilote_releve_au_fil_des_lectures(essai):
    t = essai.t
    chalet = lambda: {i["client"]: i for i in t.get("/atelier/installations").json()["installations"]}["chalet-essai"]
    avant = chalet()["releve"]
    essai.app.state.pilote.quand -= essai.module.RELEVE_CHAQUE + 1
    assert chalet()["releve"] > avant and chalet()["silencieuse"] is False


def test_suivi_avec_couts(essai):
    t = essai.t
    s = t.get("/atelier/clients/garage-essai/suivi?jours=7").json()
    assert s["periode_jours"] == 7 and s["activite"]["tours_en_echec"] >= 1
    assert "deepseek-v4-pro" in s["couts"]["sans_tarif"] and s["couts"]["total"] > 0
    assert list(t.get("/atelier/tarifs").json()["modeles"]) == ["claude-sonnet-5-5"]
    un, trente = (t.get(f"/atelier/clients/boulangerie-essai/suivi?jours={j}").json()["activite"]["tours"] for j in (1, 30))
    assert 0 < un < trente


def test_releves(essai):
    """Le relevé chiffré : le garage en panne, le fleuriste silencieux, les autres en bonne santé ; aucune conversation."""
    r = essai.t.get("/atelier/releves?jours=7")
    assert r.status_code == 200, r.text
    d = {c["id"]: c for c in r.json()["clients"]}
    assert set(d) == {"agence-essai", "boulangerie-essai", "fleuriste-essai", "garage-essai"}
    assert d["fleuriste-essai"]["silencieux"] and not d["boulangerie-essai"]["silencieux"]
    assert [p["quoi"] for p in d["garage-essai"]["etat"]["pannes_en_cours"]] == ["transmission"]
    assert len(d["boulangerie-essai"]["jours"]) == 7 and d["boulangerie-essai"]["totaux"]["tours"] == 7 * 14
    assert d["boulangerie-essai"]["totaux"]["cout"] > 0
    assert "+4179" not in r.text and "Martin" not in r.text


def test_essai_repond_sans_reseau(essai):
    t = essai.t
    r = t.post("/atelier/clients/boulangerie-essai/versions/1/essai", json={"message": "Avez-vous des tresses ?"})
    assert r.status_code == 200, r.text
    assert "Avez-vous des tresses ?" in r.json()["reponse"]


def test_rien_de_reel(essai, monkeypatch, tmp_path):
    for ident in clients(essai.t):
        assert not any(mot in ident for mot in ("megga", "estates", "fsp")), ident
    assert essai.module.HOTE == "127.0.0.1"
    monkeypatch.delenv("ATELIER_JETON", raising=False)
    monkeypatch.setenv("ATELIER_DONNEES", str(tmp_path))
    with pytest.raises(RuntimeError):
        essai.module.creer_app()


def test_relance_sans_doublon(monkeypatch, tmp_path):
    environnement(monkeypatch, tmp_path)
    module = importlib.import_module("atelier_essai")  # sans le recharger : l'app des autres essais reste la leur
    for _ in range(2):  # chaque relance trouve la base, l'annuaire de la porte et l'installation déjà là
        t = TestClient(module.creer_app(), headers=ENTETE)
        c = clients(t)
        assert sorted(c) == CLIENTS and c["agence-essai"]["ecart"] is True
        chalet = {i["client"]: i for i in t.get("/atelier/installations").json()["installations"]}["chalet-essai"]
        assert chalet["silencieuse"] is False and chalet["ecart"] is False
    assert len(t.get("/atelier/clients/agence-essai/versions").json()["versions"]) == 2
