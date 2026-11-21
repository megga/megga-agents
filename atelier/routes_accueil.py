"""Les routes de l'agent d'accueil des entreprises (atelier/accueil.py), montées par atelier/app.py.

  GET   /clients/{id}/accueil       ce que l'agent d'accueil a noté : notes, modèle, prénom, dernier brouillon, et la
                                    présentation qu'il en tire (la console les montre en cartes et dans « Réglages »)
  POST  /clients/{id}/accueil       un tour de la conversation, en AG-UI (RunAgentInput) : la réponse au fil de l'eau

MEGGA ou le client lui-même. Un tour coûte des jetons de modèle comme un essai : borné par client et par jour.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from collections import defaultdict

from fastapi import APIRouter, Body, Depends
from fastapi.responses import StreamingResponse
from pydantic import ValidationError


from . import accueil, regles
from .regles import Refus

log = logging.getLogger("megga.atelier")
TOURS_PAR_JOUR = 200
MODELE = "claude-sonnet-5-5"
MESSAGE_MAX = 4000  # comme l'essai
CORPS_MAX = 200_000  # ce que la console envoie d'un tour (historique AG-UI compris), en caractères JSON
# Ni tiret long ni point médian dans ce qui part, caractère par caractère : le flux arrive en morceaux.
ARTEFACTS = str.maketrans({"\u2014": ",", "\u2013": "-", "\u00b7": ","})


def texte_du_tour(corps: dict) -> str:
    """Le seul texte que l'agent d'accueil reçoit : celui du dernier message de la personne. Pas d'image, de document ni
    d'adresse (Agno irait les chercher lui-même, depuis l'atelier), ni outils, contexte ou état venus de la console :
    l'historique, lui, est dans la session d'Agno."""
    messages = corps.get("messages") if isinstance(corps.get("messages"), list) else []
    dernier = next((m for m in reversed(messages) if isinstance(m, dict) and m.get("role") == "user"), None)
    contenu = (dernier or {}).get("content")
    if isinstance(contenu, list):  # des parties : seulement le texte
        contenu = "\n".join(p.get("text", "") for p in contenu if isinstance(p, dict) and p.get("type") == "text")
    if not isinstance(contenu, str) or not contenu.strip() or len(contenu) > MESSAGE_MAX:
        raise Refus(400, f"message : un texte de 1 à {MESSAGE_MAX} caractères")
    return contenu


def monter(r: APIRouter, *, identite, bd, client_de, versions, reglages, zone_en_service, cles: dict, db_agno,
           principal=None) -> None:
    tours_du_jour: dict[tuple[str, str], int] = {}  # en mémoire : l'atelier est un seul processus
    verrous: dict[str, threading.Lock] = defaultdict(threading.Lock)  # l'état d'un client : une écriture à la fois

    def etat_de(ident: str) -> dict:
        return {**accueil.vide(), **(reglages.lire(accueil.cle(ident)) or {})}

    def preparer(qui, ident: str, etat: dict) -> dict:
        """Le brouillon tiré de l'état : une nouvelle version, d'après la dernière, aux règles de POST /gabarit."""
        base = versions.derniere(ident)
        if base is None:
            raise Refus(404, "aucune version de base")
        if base["config"].get("zone") not in regles.ZONES_PORTE:
            raise Refus(409, "l'accueil prépare seulement les agents servis par Cloudflare (Europe, États-Unis) pour l'instant")
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
        from ag_ui.core import EventType, RunAgentInput, RunErrorEvent, UserMessage
        from ag_ui.encoder import EventEncoder
        from agno.agent import Agent
        from agno.os.interfaces.agui.router import run_entity

        from noyau.agent import modele

        c = await bd(client_de, qui, ident)
        if len(json.dumps(corps, ensure_ascii=False)) > CORPS_MAX:
            raise Refus(413, "un tour trop long")
        try:
            recu = RunAgentInput.model_validate(corps)
        except ValidationError as e:
            raise Refus(400, "un tour AG-UI (RunAgentInput) est attendu") from e
        texte = texte_du_tour(corps)
        jour = time.strftime("%Y-%m-%d")
        n = tours_du_jour.get((ident, jour), 0)
        if n >= TOURS_PAR_JOUR:
            raise Refus(429, f"{TOURS_PAR_JOUR} messages par jour au plus avec l'accueil : la suite demain")
        tours_du_jour[(ident, jour)] = n + 1
        zone = await bd(zone_en_service, ident) or ((await bd(versions.derniere, ident) or {}).get("config") or {}).get("zone")
        outils = accueil.outils(lambda: etat_de(ident), lambda e: reglages.ecrire(accueil.cle(ident), e), zone,
                                lambda e: preparer(qui, ident, e), verrous[ident])
        entreprise = c.get("description") or ident
        # Le fil d'un client ne peut jamais être celui d'un autre : son identifiant le préfixe, quoi qu'envoie la console.
        # Rien d'autre que le texte ne passe (texte_du_tour).
        entree = RunAgentInput(thread_id=f"{ident}:{recu.thread_id}"[:200], run_id=recu.run_id, state=None, tools=[],
                               context=[], forwarded_props={},
                               messages=[UserMessage(id=uuid.uuid4().hex, role="user", content=texte)])
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
                if evenement.type == EventType.RAW:  # les détails d'Agno (modèle, identifiants) restent côté MEGGA
                    continue
                if evenement.type == EventType.RUN_ERROR:  # l'erreur technique reste dans le journal de l'atelier
                    log.warning("accueil de %s en échec : %s", ident, str(evenement.message)[:300])
                    evenement = RunErrorEvent(message="Un souci est survenu. Réessayez dans un instant.")
                if evenement.type == EventType.TEXT_MESSAGE_CONTENT:
                    evenement = evenement.model_copy(update={"delta": evenement.delta.translate(ARTEFACTS)})
                yield encodeur.encode(evenement)

        return StreamingResponse(flux(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

