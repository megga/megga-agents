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
        dernier = next((m for m in reversed(messages or []) if getattr(m, "role", "") == "user"), None)
        texte = str(getattr(dernier, "content", "") or "")
        return ModelResponse(role="assistant", content=f"Bien reçu\u00a0: «\u00a0{texte}\u00a0». Je transmets à l'équipe.")

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


def lire_registre() -> dict:
    try:
        return json.loads(REGISTRE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def ecrire_registre(r: dict) -> None:
    REGISTRE.write_text(json.dumps(r, ensure_ascii=False, indent=1))


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
        instructions=consignes(config),
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
