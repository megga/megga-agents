"""Les alertes envoyées (20.11.2026) : règles à seuils sur le relevé chiffré, destinations, envoi au changement d'état.

Rien n'y passe d'une conversation : un message ne porte que des chiffres et le nom de l'entreprise.
"""

import asyncio
import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from atelier.alertes import PROPOSEES, Regle, decider, gravite, message, mesurer, regles_de
from atelier import avertir
from atelier.app import creer as creer_atelier
from atelier.avertir import Destination, adresse_web_permise, signature
from noyau.garde import Debit
from noyau.tour import Conversations
from test_lot3 import Agent, Contacts, Exp, conf, entrant, tourner
from test_lot5 import ADMIN, MEGGA, FaussePorte, jeton_client, nouveau_client
from test_releve import AUJOURDHUI, CHIFFRES

SLACK = "https://hooks.slack.com/services/T000/B000/abcdefghijkl"
MAINTENANT = time.time()


def client(**autres):
    c = {"id": "exemple", "entreprise": "Exemple SA", "actif": True, "silencieux": False, "ecart": False,
         "releve_le": MAINTENANT - 60, "etat": {"pannes_en_cours": []},
         "jours": {AUJOURDHUI: {**CHIFFRES, "cout": 3.0}}}
    return {**c, **autres}


# Les règles, la gravité et la décision


def test_les_proposees_sont_valides():
    assert [r.id for r in regles_de(None)] == [p["id"] for p in PROPOSEES]
    assert regles_de([]) == []


def test_les_seuils_vont_dans_le_bon_sens():
    Regle(id="a1", nom="x", mesure="taux_echec", comparaison=">", alerte=10, avertissement=5)
    Regle(id="a2", nom="x", mesure="tours", comparaison="<", alerte=1, avertissement=5)
    for mauvais in ({"comparaison": ">", "avertissement": 20}, {"comparaison": "<", "avertissement": 0}):
        with pytest.raises(ValueError):
            Regle(id="a3", nom="x", mesure="tours", alerte=10, **mauvais)
    with pytest.raises(ValueError):
        Regle(id="a4", nom="x", mesure="conversations", alerte=1)  # aucune mesure ne lit une conversation


def test_mesurer():
    c = client()
    assert mesurer(c, "taux_echec", 1, MAINTENANT) == 10.0
    assert mesurer(c, "cout", 1, MAINTENANT) == 3.0 and mesurer(c, "tours", 7, MAINTENANT) == 10
    assert mesurer(client(silencieux=True), "silencieux", 1, MAINTENANT) == 1
    assert mesurer(client(etat={"pannes_en_cours": [{"quoi": "x"}]}), "pannes_en_cours", 1, MAINTENANT) == 1
    sans_tour = client(jours={AUJOURDHUI: {**CHIFFRES, "tours": 0, "tours_en_echec": 0}})
    assert mesurer(sans_tour, "taux_echec", 1, MAINTENANT) is None
    assert mesurer(client(releve_le=None), "tours", 1, MAINTENANT) is None
    journal = {"envoi_echec": {"nombre": 2}, "envoi_refuse": {"nombre": 1}, "secret_masque": {"nombre": 1}}
    c = client(jours={AUJOURDHUI: {**CHIFFRES, "journal": journal}})
    assert mesurer(c, "envois_en_echec", 1, MAINTENANT) == 3 and mesurer(c, "secrets_masques", 1, MAINTENANT) == 1
    vieux = time.strftime("%Y-%m-%d", time.gmtime(MAINTENANT - 3 * 86400))
    c = client(jours={vieux: {**CHIFFRES}})
    assert mesurer(c, "tours", 1, MAINTENANT) == 0 and mesurer(c, "tours", 4, MAINTENANT) == 10


def test_gravite_et_decision():
    r = Regle(id="echecs", nom="Échecs", mesure="taux_echec", comparaison=">", alerte=10, avertissement=5, rappel_heures=1)
    assert [gravite(r, v) for v in (2, 6, 11, None)] == ["ok", "avertissement", "alerte", "sans_donnees"]
    assert decider(r, None, "ok", MAINTENANT) == ("ok", None)
    assert decider(r, None, "alerte", MAINTENANT) == ("alerte", "nouveau")
    avant = {"etat": "alerte", "envoye_le": MAINTENANT - 600}
    assert decider(r, avant, "alerte", MAINTENANT) == ("alerte", None)
    assert decider(r, {**avant, "envoye_le": MAINTENANT - 3700}, "alerte", MAINTENANT) == ("alerte", "rappel")
    assert decider(r, avant, "ok", MAINTENANT) == ("ok", "retabli")
    assert decider(r, avant, "sans_donnees", MAINTENANT) == ("ok", "retabli")  # sans données : compté bon
    garder = r.model_copy(update={"sans_donnees": "garder"})
    assert decider(garder, avant, "sans_donnees", MAINTENANT) == ("alerte", None)
    signaler = r.model_copy(update={"sans_donnees": "signaler"})
    assert decider(signaler, avant, "sans_donnees", MAINTENANT) == ("sans_donnees", "nouveau")
    # Aucun envoi parti (destinations en panne) : le rappel compte depuis le changement d'état.
    assert decider(r, {"etat": "alerte", "envoye_le": None, "depuis": MAINTENANT - 3700}, "alerte", MAINTENANT) == ("alerte", "rappel")
    pause = r.model_copy(update={"en_pause": True})
    assert decider(pause, None, "alerte", MAINTENANT) == ("alerte", None)


def test_le_message_n_a_que_des_chiffres():
    r = Regle(id="echecs", nom="Tours en échec", mesure="taux_echec", comparaison=">", alerte=10)
    m = message(r, "nouveau", "alerte", client(), 12.5, "USD")
    assert m["sujet"] == "Alerte : Tours en échec, Exemple SA"
    assert "12,5 %" in m["texte"] and "seuil > 10 %" in m["texte"]
    for interdit in ("—", "–", "·"):
        assert interdit not in m["texte"] + m["sujet"]
    assert set(m["donnees"]) >= {"regle", "client", "valeur", "etat", "envoi"}
    m = message(r, "nouveau", "alerte", client(entreprise="Exemple\r\nBcc: x@y.ch"), 12.5, "USD")
    assert "\n" not in m["sujet"] and "\r" not in m["sujet"]


def test_destinations():
    Destination(id="slack", genre="slack", adresse=SLACK)
    Destination(id="moi", genre="courriel", adresse="julien@example.com")
    Destination(id="web", genre="web", adresse="https://alertes.example.com/megga")
    for faux in ("http://alertes.example.com", "https://127.0.0.1/x", "https://[::1]/x", "https://localhost/x",
                 "https://intranet.local/x", "https://alertes.example.com:8443/x", "https://a:b@alertes.example.com/x"):
        assert not adresse_web_permise(faux), faux
    with pytest.raises(ValueError):
        Destination(id="slack", genre="slack", adresse="https://hooks.example.com/services/T000/B000/abc")
    assert signature("cle", "1", b"{}").startswith("sha256=")


# Les routes de l'atelier


class PorteAlertes(FaussePorte):
    def __init__(self, **k):
        super().__init__(**k)
        self.client = client()
        self.courriels = []

    async def releves(self, jours):
        c = self.client
        return {"depuis": AUJOURDHUI, "jours": jours, "clients": [
            {"id": c["id"], "zone": "europe", "actif": 1, "version": 1, "releve_le": c["releve_le"] * 1000,
             "etat": c["etat"], "jours": {d: {k: v for k, v in j.items() if k != "cout"} for d, j in c["jours"].items()}}]}

    async def courriel(self, a, sujet, texte):
        self.courriels.append((a, sujet, texte))
        return {"envoye": True}


@pytest.fixture
def atelier(tmp_path, monkeypatch):
    async def public(hote):
        return hote != "interne.example.com"

    monkeypatch.setattr(avertir, "hote_public", public)  # sans réseau dans les tests
    porte = PorteAlertes()
    envoyes, panne = [], {"slack": False}

    def repondre(r: httpx.Request):
        envoyes.append((str(r.url), json.loads(r.content), dict(r.headers)))
        return httpx.Response(500 if panne["slack"] else 200, text="ok")

    t = TestClient(creer_atelier({"ADMIN_TOKEN": ADMIN, "DATABASE_URL": f"sqlite:///{tmp_path}/a.db"}, porte=porte,
                                 transport_alertes=httpx.MockTransport(repondre)))
    t.porte, t.envoyes, t.panne = porte, envoyes, panne
    nouveau_client(t)
    t.post("/atelier/clients/exemple/versions/1/activer", headers=MEGGA, json={"forcer": True})
    return t


def test_alertes_pour_megga_seulement(atelier):
    t = atelier
    r = t.get("/atelier/alertes", headers=MEGGA).json()
    assert r["proposees"] and r["destinations"] == [] and "taux_echec" in r["mesures"]
    client_ = jeton_client(t)
    assert t.get("/atelier/alertes", headers=client_).status_code == 403
    assert t.post("/atelier/alertes/evaluer", headers=client_).status_code == 403
    assert t.put("/atelier/alertes/regles", headers=client_, json=[]).status_code == 403


def test_destinations_masquees_et_retrait(atelier):
    t = atelier
    r = t.post("/atelier/alertes/destinations", headers=MEGGA, json={"id": "web", "genre": "web", "adresse": "https://alertes.example.com/cle-secrete"})
    assert r.status_code == 201 and len(r.json()["secret"]) > 30  # montrée une fois
    lues = t.get("/atelier/alertes", headers=MEGGA).json()["destinations"]
    assert lues == [{"id": "web", "genre": "web", "adresse": "https://alertes.example.com/…rete"}]
    assert "secret" not in json.dumps(lues)
    assert t.post("/atelier/alertes/destinations", headers=MEGGA, json={"id": "web", "genre": "courriel", "adresse": "a@b.ch"}).status_code == 422
    assert t.post("/atelier/alertes/destinations", headers=MEGGA, json={"id": "x", "genre": "web", "adresse": "https://10.0.0.1/"}).status_code == 422
    regle = {"id": "echecs", "nom": "Échecs", "mesure": "taux_echec", "alerte": 5, "destinations": ["web"]}
    assert t.put("/atelier/alertes/regles", headers=MEGGA, json=[{**regle, "destinations": ["inconnue"]}]).status_code == 422
    assert t.put("/atelier/alertes/regles", headers=MEGGA, json=[regle]).status_code == 200
    assert t.delete("/atelier/alertes/destinations/web", headers=MEGGA).status_code == 409
    assert t.put("/atelier/alertes/regles", headers=MEGGA, json=[]).status_code == 200
    assert t.delete("/atelier/alertes/destinations/web", headers=MEGGA).status_code == 200


def test_envoi_au_changement_d_etat_puis_retabli(atelier):
    t = atelier
    t.post("/atelier/alertes/destinations", headers=MEGGA, json={"id": "slack", "genre": "slack", "adresse": SLACK})
    t.post("/atelier/alertes/destinations", headers=MEGGA, json={"id": "moi", "genre": "courriel", "adresse": "julien@example.com"})
    regle = {"id": "echecs", "nom": "Tours en échec", "mesure": "taux_echec", "comparaison": ">", "alerte": 5,
             "destinations": ["slack", "moi"]}
    assert t.put("/atelier/alertes/regles", headers=MEGGA, json=[regle]).status_code == 200

    r = t.post("/atelier/alertes/evaluer", headers=MEGGA).json()  # 10 % d'échecs : alerte
    assert r["evaluees"] == 1 and r["envois"][0]["parties"] == ["slack", "moi"]
    assert len(t.envoyes) == 1 and t.envoyes[0][1]["text"].startswith("Alerte : Tours en échec, Entreprise exemple.")
    assert t.porte.courriels[0][0] == "julien@example.com"
    assert t.post("/atelier/alertes/evaluer", headers=MEGGA).json()["envois"] == []  # toujours en alerte : rien de neuf
    etat = t.get("/atelier/alertes", headers=MEGGA).json()["etats"][0]
    assert etat["etat"] == "alerte" and etat["valeur"] == 10.0

    t.porte.client = client(jours={AUJOURDHUI: {**CHIFFRES, "tours_en_echec": 0}})
    r = t.post("/atelier/alertes/evaluer", headers=MEGGA).json()
    assert r["envois"][0]["envoi"] == "retabli" and "Rétabli" in t.envoyes[-1][1]["text"]


def test_un_envoi_en_echec_est_repris(atelier):
    t = atelier
    t.post("/atelier/alertes/destinations", headers=MEGGA, json={"id": "slack", "genre": "slack", "adresse": SLACK})
    t.put("/atelier/alertes/regles", headers=MEGGA,
          json=[{"id": "silence", "nom": "Silence", "mesure": "silencieux", "alerte": 1, "destinations": ["slack"]}])
    t.porte.client = client(releve_le=MAINTENANT - 3 * 3600)
    t.panne["slack"] = True
    r = t.post("/atelier/alertes/evaluer", headers=MEGGA).json()
    assert r["envois"][0]["echecs"] == {"slack": "réponse 500"}
    t.panne["slack"] = False
    r = t.post("/atelier/alertes/evaluer", headers=MEGGA).json()
    assert r["envois"][0]["parties"] == ["slack"] and len(t.envoyes) == 2
    assert t.post("/atelier/alertes/evaluer", headers=MEGGA).json()["envois"] == []


def test_sans_destination_rien_ne_part(atelier):
    t = atelier
    r = t.post("/atelier/alertes/evaluer", headers=MEGGA).json()  # les règles proposées, sans destination
    assert r["evaluees"] == len(PROPOSEES) and r["envois"] == [] and t.envoyes == []
    etats = {e["regle"]: e["etat"] for e in t.get("/atelier/alertes", headers=MEGGA).json()["etats"]}
    assert etats["echecs"] == "avertissement"  # 10 % : au-dessus de 5, pas au-dessus de 10


def test_essai_d_une_destination(atelier):
    t = atelier
    t.post("/atelier/alertes/destinations", headers=MEGGA, json={"id": "web", "genre": "web", "adresse": "https://alertes.example.com/x"})
    assert t.post("/atelier/alertes/destinations/web/essai", headers=MEGGA).json() == {"envoye": True}
    url, corps, entetes = t.envoyes[0]
    assert corps["envoi"] == "essai" and entetes["x-megga-signature"].startswith("sha256=")
    assert t.post("/atelier/alertes/destinations/inconnue/essai", headers=MEGGA).status_code == 404


# Les signaux de sécurité, comptés par le noyau


class Journal:
    def __init__(self):
        self.genres = []

    def noter(self, genre, quantite=1, detail="", quand=None):
        self.genres.append(genre)


def test_signaux_de_securite():
    journal = Journal()
    c = Conversations(conf(), Agent("Voici la clé sk-abcdefghijklmnopqrstuvwxyz"), Exp(), contacts=Contacts(time.time()),
                      journal=journal, attente=0.01)
    asyncio.run(tourner(c, entrant("Bonjour", "w1")))
    assert "secret_masque" in journal.genres

    journal = Journal()
    c = Conversations(conf(), Agent(), Exp(), contacts=Contacts(time.time()), journal=journal, attente=0.01,
                      debit=Debit(maximum=1, fenetre=600))
    asyncio.run(tourner(c, entrant("Un", "w1")))
    asyncio.run(tourner(c, entrant("Deux", "w2")))
    assert journal.genres.count("debit_depasse") == 1 and "secret_masque" not in journal.genres


def test_slack_echappe_et_adresse_privee_refusee(atelier):
    t = atelier
    t.post("/atelier/alertes/destinations", headers=MEGGA, json={"id": "slack", "genre": "slack", "adresse": SLACK})
    t.post("/atelier/alertes/destinations", headers=MEGGA, json={"id": "web", "genre": "web", "adresse": "https://interne.example.com/x"})
    t.put("/atelier/alertes/regles", headers=MEGGA,
          json=[{"id": "echecs", "nom": "Échecs <!channel>", "mesure": "taux_echec", "alerte": 5, "destinations": ["slack", "web"]}])
    r = t.post("/atelier/alertes/evaluer", headers=MEGGA).json()
    assert r["envois"][0]["echecs"] == {"web": "adresse privée refusée"}
    assert "<!channel>" not in t.envoyes[0][1]["text"] and "&lt;!channel&gt;" in t.envoyes[0][1]["text"]


def test_un_client_inactif_repart_de_zero(atelier):
    t = atelier
    t.post("/atelier/alertes/destinations", headers=MEGGA, json={"id": "slack", "genre": "slack", "adresse": SLACK})
    t.put("/atelier/alertes/regles", headers=MEGGA,
          json=[{"id": "echecs", "nom": "Échecs", "mesure": "taux_echec", "alerte": 5, "destinations": ["slack"]}])
    t.post("/atelier/alertes/evaluer", headers=MEGGA)
    assert len(t.get("/atelier/alertes", headers=MEGGA).json()["etats"]) == 1
    actif = PorteAlertes.releves

    async def inactif(self, jours):
        d = await actif(self, jours)
        d["clients"][0]["actif"] = 0
        return d

    PorteAlertes.releves = inactif
    try:
        t.post("/atelier/alertes/evaluer", headers=MEGGA)
    finally:
        PorteAlertes.releves = actif
    assert t.get("/atelier/alertes", headers=MEGGA).json()["etats"] == []
    t.post("/atelier/alertes/evaluer", headers=MEGGA)  # de retour : l'alerte repart
    assert len(t.envoyes) == 2
