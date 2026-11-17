"""Le serveur d'agents de l'essai local de la console (lot 8.1).

Il tient la place de l'atelier tant que celui-ci ne sait ni servir plusieurs agents par compte,
ni répondre en AG-UI (docs/superpowers/specs/2026-11-17-console-socle-design.md). Il ne modifie
pas le moteur : il lit les consignes des gabarits (`atelier.gabarits`) et du noyau
(`noyau.agent.consignes`), et fait répondre un agent Agno par l'interface AG-UI d'Agno.

Lancement : `AGENTS_JETON=… .venv/bin/python -m uvicorn serveur:app --app-dir console/agents --host 127.0.0.1 --port 8100`
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path

from ag_ui.core import RunAgentInput
from ag_ui.encoder import EventEncoder
from agno.agent import Agent
from agno.db.sqlite import SqliteDb
from agno.models.base import Model
from agno.models.response import ModelResponse
from agno.os.interfaces.agui.router import run_entity
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from atelier import gabarits
from atelier.regles import Refus
from noyau.agent import consignes, modele
from noyau.config import Config

journal = logging.getLogger("megga.console.agents")

# Les huit métiers du lot 10 (atelier/gabarits/ sur la branche megga/lot-10-modeles).
METIERS = ("generaliste", "immobilier", "sante", "hotellerie", "juridique", "commerce", "fiduciaire", "garage")
# L'agent de l'essai n'a aucun outil (ni rappels, ni catalogue, ni transfert) : qu'il ne promette rien de ce qu'il ne fait pas.
ESSAI = (
    "Dans cet essai, tu n'as aucun outil : ne promets ni rappel, ni réservation, ni rendez-vous ferme. "
    "Recueille la demande et propose de la transmettre à l'équipe."
)
IDENT = re.compile(r"^[A-Za-z0-9_-]{6,64}$")

DOSSIER = Path(os.environ.get("AGENTS_DONNEES") or Path(__file__).resolve().parent.parent / ".donnees")
DOSSIER.mkdir(parents=True, exist_ok=True)
REGISTRE = DOSSIER / "agents.json"


@dataclass
class ModeleEssai(Model):
    """Un modèle qui répond sans réseau quand aucune clé n'est posée (essais et CI)."""

    id: str = "essai"
    name: str = "Essai"
    provider: str = "essai"
    vus: list = field(default_factory=list)

    def _repondre(self, messages):
        des_gens = [m for m in (messages or []) if getattr(m, "role", "") == "user"]
        texte = str(getattr(des_gens[-1], "content", "") or "") if des_gens else ""
        if texte == "ESSAI-PANNE":  # les essais de bout en bout simulent ainsi une panne du modèle
            raise RuntimeError("panne simulée du modèle d'essai")
        reponse = f"Bien reçu\u00a0: «\u00a0{texte}\u00a0». Je transmets à l'équipe."
        # Il compte les messages de la conversation qu'il voit : les essais vérifient ainsi qu'il s'en souvient.
        if len(des_gens) > 1:
            reponse += f" C'est votre {len(des_gens)}e message."
        return ModelResponse(role="assistant", content=reponse)

    def invoke(self, messages=None, **kw):
        return self._repondre(messages)

    async def ainvoke(self, messages=None, **kw):
        return self._repondre(messages)

    def invoke_stream(self, messages=None, **kw):
        yield self._repondre(messages)

    async def ainvoke_stream(self, messages=None, **kw):
        yield self._repondre(messages)

    def _parse_provider_response(self, response, **kw):
        return response

    def _parse_provider_response_delta(self, response):
        return response


class Inscription(BaseModel):
    prenom: str = Field(min_length=1, max_length=20)
    metier: str
    entreprise: str = Field(min_length=1, max_length=120)


# Les inscriptions arrivent en parallèle (FastAPI les sert dans plusieurs fils) : une à la fois.
VERROU = threading.Lock()


def lire_registre() -> dict:
    try:
        return json.loads(REGISTRE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def ecrire_registre(r: dict) -> None:
    """Écrit à côté, puis remplace : le registre n'est jamais lu à moitié écrit."""
    provisoire = REGISTRE.with_suffix(".json.tmp")
    provisoire.write_text(json.dumps(r, ensure_ascii=False, indent=1))
    os.replace(provisoire, REGISTRE)


def reglages(metier: str) -> dict:
    """Les réglages du gabarit ; un métier que cette image ne connaît pas encore prend ceux du généraliste."""
    try:
        return gabarits.reglages_pour(metier, {})
    except Refus:
        journal.warning("le métier %s n'est pas dans cette image (lot 10 non fusionné) : consignes du généraliste", metier)
        return gabarits.reglages_pour("generaliste", {})


def construire(ident: str, fiche: dict) -> Agent:
    r = reglages(fiche["metier"])
    config = Config.model_validate({
        "id": "essai-" + re.sub(r"[^a-z0-9-]", "", ident.lower())[:40],
        "nom_agent": fiche["prenom"],
        "entreprise": fiche["entreprise"],
        "zone": "europe",
        "metier": r["metier"] if r["metier"] in ("general", "immobilier") else "general",
        "ton": r.get("ton", "chaleureux et professionnel"),
        "consignes": r.get("consignes", ""),
    })
    cle = os.environ.get("ANTHROPIC_API_KEY")
    m = modele(config.modeles.principal, {"ANTHROPIC_API_KEY": cle}) if cle else ModeleEssai()
    return Agent(
        id=ident,
        name=fiche["prenom"],
        model=m,
        instructions=[*consignes(config), ESSAI],
        db=SqliteDb(db_file=str(DOSSIER / "sessions.sqlite")),
        add_history_to_context=True,
        num_history_runs=12,
        markdown=False,
        telemetry=False,
    )


def jeton(requete: Request) -> None:
    attendu = os.environ.get("AGENTS_JETON", "")
    recu = (requete.headers.get("authorization") or "").removeprefix("Bearer ").strip()
    if not attendu or not hmac.compare_digest(recu, attendu):
        raise HTTPException(401, "jeton refusé")


app = FastAPI(title="Agents de l'essai local de la console MEGGA", docs_url=None, redoc_url=None, openapi_url=None)
encodeur = EventEncoder()


@app.get("/sante")
def sante():
    return {"ok": True}


@app.put("/agents/{ident}", dependencies=[Depends(jeton)])
def inscrire(ident: str, corps: Inscription):
    if not IDENT.match(ident):
        raise HTTPException(400, "identifiant invalide")
    if corps.metier not in METIERS:
        raise HTTPException(400, "métier inconnu")
    with VERROU:
        r = lire_registre()
        r[ident] = corps.model_dump()
        ecrire_registre(r)
    return {"id": ident, "en_service": True}


@app.post("/agents/{ident}/agui", dependencies=[Depends(jeton)])
async def repondre(ident: str, entree: RunAgentInput):
    fiche = lire_registre().get(ident)
    if fiche is None:
        raise HTTPException(404, "agent inconnu")
    agent = construire(ident, fiche)

    async def flux():
        async for evenement in run_entity(agent, entree, user_id=ident):
            yield encodeur.encode(evenement)

    return StreamingResponse(flux(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
