"""La réponse au fil de l'eau (noyau/flux.py) : par l'entrée API, le texte part par morceaux, masqué, les outils
s'annoncent, et l'événement « fin » porte la réponse qui fait foi."""

import asyncio
import json
from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest
from agno.agent import Agent
from agno.models.base import Model
from agno.models.response import ModelResponse

from noyau import flux, stockage
from noyau.tour import EXCUSE
from test_app import Sortie, attendre
from test_lot6_api import agent_api, nouvelle_cle

SECRET = "sk-abcdefghijklmnopqrstuvwxyz0123"
FLUX = {"accept": "text/event-stream"}


@pytest.fixture
def sqlite(tmp_path):
    return f"sqlite:///{tmp_path}/client.db"


@dataclass
class Ev:
    event: str
    content: str | None = None
    tool: object = None


class AgentEnFlux:
    """Un agent qui répond comme Agno en flux : outils, morceaux de texte, puis la sortie finale."""

    def __init__(self, morceaux, outils=(), erreur=None):
        self.morceaux, self.outils, self.erreur = list(morceaux), list(outils), erreur
        self.appels = []

    def arun(self, texte, user_id=None, session_id=None, stream=False, **options):
        self.appels.append((texte, user_id, stream, options.get("stream_events"), options.get("yield_run_output")))
        if not stream:
            async def bloc():
                return Sortie("".join(self.morceaux), "COMPLETED")
            return bloc()

        async def evenements():
            for nom in self.outils:
                yield Ev("ToolCallStarted", tool=SimpleNamespace(tool_name=nom))
                yield Ev("ToolCallCompleted", tool=SimpleNamespace(tool_name=nom))
            for m in self.morceaux:
                yield Ev("RunContent", content=m)
            if self.erreur:
                raise self.erreur
            yield Sortie("".join(self.morceaux), "COMPLETED")
        return evenements()


def lire(texte: str) -> list[tuple[str, dict]]:
    """Les événements d'un flux SSE, sans les commentaires d'attente."""
    evenements = []
    for bloc in texte.strip().split("\n\n"):
        if bloc.startswith(":"):
            continue
        lignes = dict(ligne.split(": ", 1) for ligne in bloc.split("\n"))
        evenements.append((lignes["event"], json.loads(lignes["data"])))
    return evenements


def tout_passer(morceaux) -> tuple[list[str], str]:
    """Les morceaux dans un masque : (ce qui est parti à chaque morceau, ce qui part à la fin)."""
    m = flux.Masque()
    return [m.ajouter(x) for x in morceaux], m.finir()


# Le masque


def test_un_secret_coupe_ne_part_jamais_en_clair():
    texte = f"Votre clé est {SECRET}, gardez-la."
    for i in range(1, len(texte)):  # le secret coupé à chaque position possible
        parties, fin = tout_passer([texte[:i], texte[i:]])
        sorti = "".join(parties) + fin
        assert "sk-" not in sorti and "abcdefghij" not in sorti, i
        assert sorti == "Votre clé est [masqué], gardez-la."


def test_une_adresse_de_base_coupee_en_trois():
    parties, fin = tout_passer(["La base : postgres://ali", "x:motdepasse@hote", ":5432/base fin"])
    assert "motdepasse" not in "".join(parties) + fin
    assert "".join(parties) + fin == "La base : [masqué] fin"


def test_le_flux_masque_comme_la_reponse_entiere():
    """Coupé n'importe où, le flux masque exactement comme garde.masquer_secrets sur le texte entier : le chemin d'une
    adresse d'annonce reste lisible, un jeton et une clé sont masqués (aucune règle de garde ne passe un blanc)."""
    from noyau.garde import masquer_secrets

    jeton = "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0"
    texte = (f"Voici l'annonce https://site.ch/property/dubai-high-floor-2-br-apartment-1234567890abcdef1234567890abcdef12?ref={jeton} "
             f"et votre clé {SECRET}, jeton {jeton}.")
    attendu = masquer_secrets(texte)
    assert "dubai-high-floor" in attendu and jeton not in attendu and "sk-" not in attendu
    for i in range(1, len(texte)):
        parties, fin = tout_passer([texte[:i], texte[i:]])
        assert "".join(parties) + fin == attendu, i


def test_le_texte_part_avant_la_fin():
    """Le direct : des mots entiers partent dès qu'ils sont sûrs, sans attendre la fin du tour."""
    parties, fin = tout_passer(["Bonjour, ", "je cherche ", "vos biens ", "à Nyon."])
    assert parties[0] and parties[1], parties
    assert "".join(parties) + fin == "Bonjour, je cherche vos biens à Nyon."


def test_les_tirets_longs_sont_corriges_au_fil_de_l_eau():
    parties, fin = tout_passer(["Bonjour — ", "bienvenue"])
    assert "—" not in "".join(parties) + fin


# La route


def test_la_reponse_au_fil_de_l_eau(sqlite):
    agent = AgentEnFlux(["Bonjour — ", "**bienvenue**, ", "voici ", "trois biens."], outils=["chercher_biens"])
    t, _, exp, app = agent_api(sqlite, agent=agent)
    _, entete = nouvelle_cle(sqlite)
    r = t.post("/api/messages", headers={**entete, **FLUX}, json={"personne": "patient-42", "texte": "Bonjour"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    assert r.headers["cache-control"] == "no-store"
    evenements = lire(r.text)
    assert evenements[:2] == [("outil", {"outil": "chercher_biens", "etat": "debut"}), ("outil", {"outil": "chercher_biens", "etat": "fin"})]
    assert evenements[-1] == ("fin", {"reponse": "Bonjour, *bienvenue*, voici trois biens."})
    # Les morceaux : masqués et sans tiret long ; le gras de WhatsApp n'est fait que dans la réponse de « fin »
    textes = [d["texte"] for g, d in evenements if g == "texte"]
    assert "".join(textes) == "Bonjour, **bienvenue**, voici trois biens."
    # Le tour en flux a été demandé à Agno, avec la sortie finale ; rien sur WhatsApp
    assert agent.appels == [("Bonjour", "api:dossier:patient-42", True, True, True)]
    assert exp.envois == []
    asyncio.run(attendre(app)())
    fil = stockage.Fil(sqlite).messages("api:dossier:patient-42")
    assert [(m["sens"], m["texte"]) for m in fil] == [("recu", "Bonjour"), ("envoye", "Bonjour, *bienvenue*, voici trois biens.")]


def test_aucun_secret_dans_le_flux(sqlite):
    agent = AgentEnFlux(["Votre clé : sk-abc", "defghijklmnopqrstuvwxyz0123", " voilà."])
    t, *_ = agent_api(sqlite, agent=agent)
    _, entete = nouvelle_cle(sqlite)
    r = t.post("/api/messages", headers={**entete, **FLUX}, json={"personne": "p1", "texte": "Ma clé ?"})
    assert "sk-" not in r.text and "defghij" not in r.text
    assert lire(r.text)[-1] == ("fin", {"reponse": "Votre clé : [masqué] voilà."})


def test_un_tour_en_flux_qui_echoue(sqlite):
    agent = AgentEnFlux(["Je cherche "], erreur=RuntimeError("panne du modèle, clé sk-abcdefghijklmnopqrstuvwxyz"))
    t, *_ = agent_api(sqlite, agent=agent)
    _, entete = nouvelle_cle(sqlite)
    r = t.post("/api/messages", headers={**entete, **FLUX}, json={"personne": "p1", "texte": "Bonjour"})
    assert r.status_code == 200  # le flux était ouvert : l'échec arrive en événement
    assert lire(r.text)[-1] == ("erreur", {"erreur": "l'agent n'a pas pu répondre", "statut": 503, "reponse": EXCUSE})
    assert "panne" not in r.text and "sk-" not in r.text


def test_les_refus_restent_en_json(sqlite):
    t, *_ = agent_api(sqlite, agent=AgentEnFlux(["x"]))
    r = t.post("/api/messages", headers={"authorization": "Bearer mga_faux", **FLUX}, json={"personne": "p1", "texte": "x"})
    assert r.status_code == 401 and r.json() == {"erreur": "clé refusée"}


def test_sans_accept_rien_ne_change(sqlite):
    agent = AgentEnFlux(["Bonjour ", "à vous."])
    t, *_ = agent_api(sqlite, agent=agent)
    _, entete = nouvelle_cle(sqlite)
    r = t.post("/api/messages", headers=entete, json={"personne": "p1", "texte": "Bonjour"})
    assert r.json() == {"reponse": "Bonjour à vous."}
    assert agent.appels[0][2] is False


# Avec le vrai Agno


@dataclass
class ModeleEnFlux(Model):
    """Un modèle Agno qui répond par morceaux, sans réseau."""

    id: str = "faux-flux"
    name: str = "FauxFlux"
    provider: str = "essai"
    morceaux: list = field(default_factory=lambda: ["Bonjour ", "— voici ", "**vos** ", "biens."])

    def invoke(self, messages=None, **kw):
        return ModelResponse(role="assistant", content="".join(self.morceaux))

    async def ainvoke(self, messages=None, **kw):
        return self.invoke()

    def invoke_stream(self, *a, **kw):
        for m in self.morceaux:
            yield ModelResponse(role="assistant", content=m)

    async def ainvoke_stream(self, *a, **kw):
        for m in self.morceaux:
            yield ModelResponse(role="assistant", content=m)

    def _parse_provider_response(self, response, **kw):
        return response

    def _parse_provider_response_delta(self, response):
        return response


@pytest.fixture
def atelier_en_flux(tmp_path):
    """L'atelier, avec un modèle d'essai qui répond par morceaux (dont un secret coupé en deux)."""
    from fastapi.testclient import TestClient

    from atelier.app import creer as creer_atelier
    from test_lot5 import ADMIN, CLE_PILOTAGE_TEXTE, FaussePorte

    modele = ModeleEnFlux(morceaux=["Bonjour ", "— votre clé : sk-abc", "defghijklmnopqrstuvwxyz0123 ", "**reste** secrète."])
    app = creer_atelier({"ADMIN_TOKEN": ADMIN, "DATABASE_URL": f"sqlite:///{tmp_path}/atelier.db", "ESSAIS_DIR": str(tmp_path / "essais"),
                         "PILOTAGE_CLE": CLE_PILOTAGE_TEXTE}, porte=FaussePorte(), principal_essai=modele)
    return TestClient(app)


def test_l_essai_de_l_atelier_au_fil_de_l_eau(atelier_en_flux):
    from test_lot5 import jeton_client, nouveau_client

    t = atelier_en_flux
    nouveau_client(t)
    client = jeton_client(t)
    r = t.post("/atelier/clients/exemple/versions/1/essai", headers={**client, **FLUX}, json={"message": "Bonjour", "conversation": "a"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    evenements = lire(r.text)
    # La même réponse que l'essai d'un bloc, et le secret jamais en clair, ni dans les morceaux ni à la fin
    assert evenements[-1] == ("fin", {"version": 1, "conversation": "a", "reponse": "Bonjour, votre clé : [masqué] *reste* secrète."})
    assert any(g == "texte" for g, _ in evenements[:-1])
    assert "sk-" not in r.text and "defghij" not in r.text
    # L'essai compte, comme d'un bloc
    assert t.get("/atelier/clients/exemple/versions/1", headers=client).json()["essais"] == 1


def test_l_essai_en_flux_garde_ses_refus_en_json(atelier_en_flux):
    from test_lot5 import MEGGA, nouveau_client

    t = atelier_en_flux
    nouveau_client(t)
    r = t.post("/atelier/clients/exemple/versions/1/essai", headers={**MEGGA, **FLUX}, json={"message": ""})
    assert r.status_code == 400 and "message" in r.json()["erreur"]
    assert t.post("/atelier/clients/exemple/versions/9/essai", headers={**MEGGA, **FLUX}, json={"message": "x"}).status_code == 404
    assert t.post("/atelier/clients/exemple/versions/1/essai", headers=FLUX, json={"message": "x"}).status_code == 401


def test_avec_un_vrai_agent_agno(sqlite):
    t, *_ = agent_api(sqlite, agent=Agent(model=ModeleEnFlux(), telemetry=False))
    _, entete = nouvelle_cle(sqlite)
    r = t.post("/api/messages", headers={**entete, **FLUX}, json={"personne": "p1", "texte": "Bonjour"})
    evenements = lire(r.text)
    assert evenements[-1] == ("fin", {"reponse": "Bonjour, voici *vos* biens."})
    assert any(g == "texte" for g, _ in evenements[:-1])
