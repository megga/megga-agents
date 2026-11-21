"""Lot E1 : l'agent d'accueil des entreprises écrit l'agent du client à partir de ce qu'il raconte."""

import json
import uuid
from dataclasses import dataclass, field

import pytest
from agno.models.base import Model
from agno.models.response import ModelResponse
from fastapi.testclient import TestClient

from atelier import accueil, regles
from atelier.app import creer
from noyau.agent import PRESENTATION, consignes
from noyau.config import Config
from test_lot5 import ADMIN, MEGGA, FaussePorte, jeton_client

IDENTITE = {"id": "boulangerie-du-lac", "entreprise": "Boulangerie du Lac", "zone": "europe", "numero_id": "100000000000077"}


@dataclass
class ModeleScenario(Model):
    """Un modèle sans réseau qui joue un scénario : à chaque appel, la réponse suivante (des appels d'outils ou un texte)."""

    id: str = "scenario"
    name: str = "Scénario"
    provider: str = "essai"
    etapes: list = field(default_factory=list)
    vus: list = field(default_factory=list)

    def _repondre(self, messages):
        self.vus.append(messages)
        etape = self.etapes.pop(0) if self.etapes else "D'accord."
        if isinstance(etape, str):
            return ModelResponse(role="assistant", content=etape)
        appels = [{"id": f"appel-{uuid.uuid4().hex[:8]}", "type": "function",
                   "function": {"name": nom, "arguments": json.dumps(args, ensure_ascii=False)}} for nom, args in etape]
        return ModelResponse(role="assistant", content="", tool_calls=appels)

    def invoke(self, messages=None, **kw):
        return self._repondre(messages or [])

    async def ainvoke(self, messages=None, **kw):
        return self._repondre(messages or [])

    def invoke_stream(self, *a, **kw):
        yield self.invoke(*a, **kw)

    async def ainvoke_stream(self, *a, **kw):
        yield await self.ainvoke(*a, **kw)

    def _parse_provider_response(self, response, **kw):
        return response

    def _parse_provider_response_delta(self, response):
        return response


@pytest.fixture
def atelier(tmp_path):
    modele = ModeleScenario()
    t = TestClient(creer({"ADMIN_TOKEN": ADMIN, "DATABASE_URL": f"sqlite:///{tmp_path}/a.db", "ESSAIS_DIR": str(tmp_path / "essais")},
                         porte=FaussePorte(), principal_essai=modele))
    t.modele = modele
    r = t.post("/atelier/clients", headers=MEGGA, json={"gabarit": "generaliste", "client": IDENTITE, "nom_agent": "Lea"})
    assert r.status_code == 201, r.text
    t.client = jeton_client(t, IDENTITE["id"])
    return t


def tour(t, texte, fil="fil-1", entetes=None):
    corps = {"threadId": fil, "runId": uuid.uuid4().hex, "state": {}, "tools": [], "context": [], "forwardedProps": {},
             "messages": [{"id": uuid.uuid4().hex, "role": "user", "content": texte}]}
    r = t.post(f"/atelier/clients/{IDENTITE['id']}/accueil", headers=entetes or t.client, json=corps)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/event-stream")
    return r.text


def test_une_conversation_ecrit_l_agent_du_client(atelier):
    t = atelier
    t.modele.etapes = [
        [("noter", {"sujet": "activite", "texte": "Boulangerie artisanale \u2014 pain au levain et viennoiseries"}),
         ("noter", {"sujet": "horaires", "texte": "Du mardi au dimanche, 7h-19h"})],
        "Merci ! Qu'est-ce que vos clients vous demandent le plus ?",
        [("noter", {"sujet": "demandes", "texte": "Commander un gâteau pour le week-end"}),
         ("noter", {"sujet": "ton", "texte": "chaleureux, tutoie volontiers"}),
         ("chercher_modele", {"recherche": "customer service bakery"})],
        "Je vous propose le modèle généraliste. Il vous convient ?",
        [("choisir_modele", {"modele": "generaliste"}), ("nommer_agent", {"prenom": "Rose"})],
        [("preparer_agent", {})],
        "Rose est prête : écrivez-lui comme un client.",
    ]
    flux = tour(t, "Je tiens une boulangerie au bord du lac.")
    assert "RUN_STARTED" in flux and "Qu'est-ce que vos clients" in flux
    assert '"RAW"' not in flux and "scenario" not in flux  # rien d'Agno ne sort : ni le modèle, ni ses identifiants
    flux = tour(t, "Surtout des commandes de gâteaux, et un ton chaleureux.")
    assert "Il vous convient" in flux
    flux = tour(t, "Oui, et elle s'appellera Rose.")
    assert "Rose est pr" in flux and "preparer_agent" in flux

    etat = t.get(f"/atelier/clients/{IDENTITE['id']}/accueil", headers=t.client).json()
    assert etat["modele"] == "generaliste" and etat["prenom"] == "Rose" and etat["version"] == 2
    assert etat["notes"]["activite"] == "Boulangerie artisanale, pain au levain et viennoiseries"  # tiret long retiré
    assert "Opening hours: Du mardi au dimanche, 7h-19h" in etat["presentation"]

    config = t.get(f"/atelier/clients/{IDENTITE['id']}/versions/2", headers=t.client).json()["config"]
    assert config["nom_agent"] == "Rose" and config["ton"] == "chaleureux, tutoie volontiers"
    assert config["presentation"] == etat["presentation"]
    assert config["whatsapp"]["numero_id"] == IDENTITE["numero_id"]  # ce que MEGGA règle ne bouge pas
    # La présentation part dans les consignes de l'agent du client, après celles du modèle.
    textes = consignes(Config.model_validate(config))
    i = next(i for i, c in enumerate(textes) if c.startswith(PRESENTATION))
    assert textes[i].endswith(etat["presentation"]) and "never" in textes[i]
    assert textes.index(config["consignes"]) > i  # les consignes de MEGGA viennent après, et gardent le dernier mot
    # Le client essaie et met en service le brouillon, comme tout autre.
    assert t.post(f"/atelier/clients/{IDENTITE['id']}/versions/2/essai", headers=t.client, json={"message": "Bonjour"}).status_code == 200
    assert t.post(f"/atelier/clients/{IDENTITE['id']}/versions/2/activer", headers=t.client).status_code == 200


def test_l_accueil_refuse_ce_qui_manque_et_ce_qui_ne_va_pas(atelier):
    t = atelier
    t.modele.etapes = [
        [("preparer_agent", {}), ("noter", {"sujet": "salaire", "texte": "x"}), ("choisir_modele", {"modele": "plombier"}),
         ("nommer_agent", {"prenom": "R2-D2 \u00b7 robot"})],
        "Il me manque encore quelques informations.",
    ]
    flux = tour(t, "Fais vite.")
    assert "il manque encore : activite, modele, prenom" in flux
    assert "sujet : activite" in flux and "modèle inconnu" in flux and "un prénom de 1 à 40 lettres" in flux
    etat = t.get(f"/atelier/clients/{IDENTITE['id']}/accueil", headers=t.client).json()
    assert etat == {**accueil.vide(), "presentation": ""}  # rien n'est écrit
    assert t.get(f"/atelier/clients/{IDENTITE['id']}/versions", headers=t.client).json()["versions"][0]["version"] == 1


def test_chacun_son_accueil(atelier, tmp_path):
    t = atelier
    autre = {"id": "garage-du-port", "entreprise": "Garage du Port", "zone": "europe", "numero_id": "100000000000078"}
    assert t.post("/atelier/clients", headers=MEGGA, json={"gabarit": "generaliste", "client": autre, "nom_agent": "Max"}).status_code == 201
    jeton_autre = jeton_client(t, "garage-du-port")
    assert t.get(f"/atelier/clients/{IDENTITE['id']}/accueil", headers=jeton_autre).status_code == 404
    r = t.post(f"/atelier/clients/{IDENTITE['id']}/accueil", headers=jeton_autre, json={"threadId": "f", "runId": "r", "messages": []})
    assert r.status_code == 404
    assert t.post(f"/atelier/clients/{IDENTITE['id']}/accueil", headers=t.client, json={"rien": 1}).status_code == 400
    assert t.get(f"/atelier/clients/{IDENTITE['id']}/accueil").status_code == 401
    # MEGGA peut suivre l'accueil d'un client.
    assert t.get(f"/atelier/clients/{IDENTITE['id']}/accueil", headers=MEGGA).status_code == 200


def test_la_recherche_de_modele_et_la_presentation():
    trouves = [m["id"] for m in accueil.chercher("agence immobilière, real estate", "europe")]
    assert "immobilier" in trouves
    assert accueil.chercher("zzzz", "europe")[0]["id"] == "generaliste"
    sante = [m for m in accueil.chercher("healthcare clinical evidence", "etats-unis")]
    assert all(m["id"] not in ("healthcare-clinical-evidence-agent",) for m in sante)
    long = accueil.presentation({s: "x" * 600 for s in accueil.SUJETS})
    assert len(long) <= accueil.PRESENTATION_MAX and long.startswith("Business: ")
    assert len(accueil.cle("x" * 63)) <= 40


def test_le_client_regle_lui_meme_sa_presentation(atelier):
    t = atelier
    assert "presentation" in regles.CHAMPS_CLIENT
    r = t.post(f"/atelier/clients/{IDENTITE['id']}/versions", headers=t.client,
               json={"changements": {"presentation": "Business: boulangerie"}})
    assert r.status_code == 201, r.text
    r = t.post(f"/atelier/clients/{IDENTITE['id']}/versions", headers=t.client,
               json={"changements": {"presentation": "un tiret \u2014 long"}})
    assert r.status_code == 422 and "presentation" in r.text


def test_une_presentation_vide_n_est_pas_ecrite():
    """Une image d'avant ce champ lit toujours une configuration sans présentation (Config refuse les champs inconnus)."""
    from test_lot5 import conf_exemple

    conf = Config.model_validate(conf_exemple())
    assert "presentation" not in conf.model_dump(mode="json")
    avec = Config.model_validate({**conf_exemple(), "presentation": "Business: boulangerie"})
    assert avec.model_dump(mode="json")["presentation"] == "Business: boulangerie"
    assert Config.model_validate(conf.model_dump(mode="json")) == conf


def test_seul_le_texte_du_tour_passe(atelier):
    """Ni image, ni document, ni adresse (Agno irait les chercher depuis l'atelier), ni outils ou contexte de la console."""
    t = atelier
    t.modele.etapes = ["Bien noté \u2014 merci \u00b7 à bientôt"]
    corps = {"threadId": "f", "runId": "r", "state": {"x": 1}, "context": [{"description": "d", "value": "v"}],
             "tools": [{"name": "piege", "description": "d", "parameters": {}}], "forwardedProps": {},
             "messages": [{"id": "1", "role": "user", "content": [
                 {"type": "text", "text": "Voici ma carte"},
                 {"type": "document", "source": {"type": "url", "value": "http://169.254.169.254/x", "mimeType": "text/plain"}}]}]}
    r = t.post(f"/atelier/clients/{IDENTITE['id']}/accueil", headers=t.client, json=corps)
    assert r.status_code == 200, r.text
    vus = t.modele.vus[-1]
    assert not any("169.254" in str(getattr(m, "content", "")) or getattr(m, "files", None) or getattr(m, "images", None)
                   for m in vus)
    assert "Voici ma carte" in str([getattr(m, "content", "") for m in vus])
    assert "piege" not in r.text and "\u2014" not in r.text and "\\u2014" not in r.text and "Bien not" in r.text
    for mauvais in ({"threadId": "f", "runId": "r", "messages": [{"id": "1", "role": "user", "content": "x" * 4001}]},
                    {"threadId": "f", "runId": "r", "messages": []}):
        assert t.post(f"/atelier/clients/{IDENTITE['id']}/accueil", headers=t.client, json=mauvais).status_code == 400


def test_une_panne_du_modele_ne_dit_rien_de_technique(atelier):
    t = atelier

    def panne(*a, **k):
        raise RuntimeError("http://10.0.0.7:5432 refused")

    t.modele.invoke = t.modele.ainvoke = panne
    flux = tour(t, "Bonjour")
    assert "RUN_ERROR" in flux and "10.0.0.7" not in flux and "Un souci est survenu" in flux


def test_pas_de_presentation_hors_cloudflare(atelier):
    """Une installation chez le client peut servir une image d'avant ce champ : l'accueil ne la prépare pas, et une version
    qui en porte une n'y est pas mise en service."""
    from test_lot5 import conf_exemple

    t = atelier
    conf = {**conf_exemple(id="cabinet-geneve", entreprise="Cabinet Genève", zone="suisse"), "presentation": "Business: x"}
    r = t.post("/atelier/clients", headers=MEGGA, json={"config": conf})
    assert r.status_code == 201, r.text
    r = t.post("/atelier/clients/cabinet-geneve/versions/1/activer", headers=MEGGA, json={"forcer": True})
    assert r.status_code == 409 and "hors Cloudflare" in r.text, r.text

