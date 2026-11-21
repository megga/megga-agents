"""Les routes de l'agent d'accueil des entreprises (atelier/accueil.py), montées par atelier/app.py.

  GET   /clients/{id}/accueil       ce que l'agent d'accueil a noté : notes, modèle, prénom, dernier brouillon, et la
                                    présentation qu'il en tire (la console les montre en cartes et dans « Réglages »)
  POST  /clients/{id}/accueil       un tour de la conversation, en AG-UI (RunAgentInput) : la réponse au fil de l'eau

MEGGA ou le client lui-même. Un tour coûte des jetons de modèle comme un essai : borné par client et par jour.
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Body, Depends
from fastapi.responses import StreamingResponse
from pydantic import ValidationError


from . import accueil, regles
from .regles import Refus

log = logging.getLogger("megga.atelier")
TOURS_PAR_JOUR = 200
MODELE = "claude-sonnet-5-5"


def monter(r: APIRouter, *, identite, bd, client_de, versions, reglages, zone_en_service, cles: dict, db_agno,
           principal=None) -> None:
    tours_du_jour: dict[tuple[str, str], int] = {}  # en mémoire : l'atelier est un seul processus

    def etat_de(ident: str) -> dict:
        return {**accueil.vide(), **(reglages.lire(accueil.cle(ident)) or {})}

    def preparer(qui, ident: str, etat: dict) -> dict:
        """Le brouillon tiré de l'état : une nouvelle version, d'après la dernière, aux règles de POST /gabarit."""
        base = versions.derniere(ident)
        if base is None:
            raise Refus(404, "aucune version de base")
        conf = regles.valider(regles.fusionner(base["config"], accueil.changements(etat, base["config"], qui.role)))
        regles.verifier_zone(conf, zone_en_service(ident))
        v = versions.ajouter(conf, qui.role, base["version"])
        return {"version": v["version"], "manques": regles.manques(conf)}

    @r.get("/clients/{ident}/accueil")
    async def lire(ident: str, qui=Depends(identite)):
        await bd(client_de, qui, ident)
        etat = await bd(etat_de, ident)
        return {**etat, "presentation": accueil.presentation(etat["notes"])}

    @r.post("/clients/{ident}/accueil")
    async def tour(ident: str, qui=Depends(identite), corps: dict = Body(...)):
        from ag_ui.core import RunAgentInput
        from ag_ui.encoder import EventEncoder
        from agno.agent import Agent
        from agno.os.interfaces.agui.router import run_entity

        from noyau.agent import modele

        c = await bd(client_de, qui, ident)
        try:
            entree = RunAgentInput.model_validate(corps)
        except ValidationError as e:
            raise Refus(400, "un tour AG-UI (RunAgentInput) est attendu") from e
        jour = time.strftime("%Y-%m-%d")
        n = tours_du_jour.get((ident, jour), 0)
        if n >= TOURS_PAR_JOUR:
            raise Refus(429, f"{TOURS_PAR_JOUR} messages par jour au plus avec l'accueil : la suite demain")
        tours_du_jour[(ident, jour)] = n + 1
        zone = await bd(zone_en_service, ident) or ((await bd(versions.derniere, ident) or {}).get("config") or {}).get("zone")
        outils = accueil.outils(lambda: etat_de(ident), lambda e: reglages.ecrire(accueil.cle(ident), e), zone,
                                lambda e: preparer(qui, ident, e))
        entreprise = c.get("description") or ident
        # Le fil d'un client ne peut jamais être celui d'un autre : son identifiant le préfixe, quoi qu'envoie la console.
        entree = entree.model_copy(update={"thread_id": f"{ident}:{entree.thread_id}"[:200]})
        agent = Agent(
            name="Accueil MEGGA",
            model=principal if principal is not None else modele(MODELE, cles, cache=True),
            instructions=[*accueil.CONSIGNES, f"The business is called {entreprise}."],
            tools=outils,
            db=db_agno,
            add_history_to_context=True,
            num_history_runs=30,
            markdown=False,
            telemetry=False,
        )
        encodeur = EventEncoder()

        async def flux():
            async for evenement in run_entity(agent, entree, user_id=f"accueil:{ident}"):
                yield encodeur.encode(evenement)

        return StreamingResponse(flux(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

