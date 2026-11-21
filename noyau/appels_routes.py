"""Les routes des appels WhatsApp (noyau/appels.py), posées par noyau/app.py : la clé APPELS_CLE pour le début et les
outils, la signature d'ElevenLabs pour la fin."""

from __future__ import annotations

import json

from fastapi import Request
from fastapi.responses import JSONResponse

from .appels import Appels


CORPS_MAX = 64 * 1024  # début et outils ; la fin (le texte d'un appel de trente minutes) jusqu'à 2 Mio
FIN_MAX = 2 * 1024 * 1024


def routes(app, appels: Appels, licence_echue) -> None:
    """Les trois routes ; `licence_echue` : f() -> vrai quand l'agent ne sert plus."""
    async def lire(requete: Request, maximum: int) -> bytes | None:
        corps = bytearray()
        async for morceau in requete.stream():
            corps += morceau
            if len(corps) > maximum:
                return None
        return bytes(corps)

    async def entree(requete: Request) -> tuple[dict | None, JSONResponse | None]:
        if licence_echue():
            return None, JSONResponse({"erreur": "licence échue"}, status_code=503)
        if not appels.cle_valide(requete.headers.get("authorization")):
            return None, JSONResponse({"erreur": "clé refusée"}, status_code=401)
        corps = await lire(requete, CORPS_MAX)
        if corps is None:
            return None, JSONResponse({"erreur": "requête trop grosse"}, status_code=413)
        try:
            d = json.loads(corps or b"{}")
        except ValueError:
            return None, JSONResponse({"erreur": "corps : du JSON"}, status_code=400)
        if not isinstance(d, dict):
            return None, JSONResponse({"erreur": "corps : un objet JSON"}, status_code=400)
        return d, None

    @app.post("/appels/debut")
    async def appel_debut(requete: Request):
        d, refus = await entree(requete)
        if refus is not None:
            return refus
        if not appels.agent_connu(d.get("agent_id")):
            return JSONResponse({"erreur": "agent"}, status_code=403)
        return JSONResponse(await appels.debut(d), headers={"cache-control": "no-store"})

    @app.post("/appels/outils/{nom}")
    async def appel_outil(nom: str, requete: Request):
        d, refus = await entree(requete)
        if refus is not None:
            return refus
        if nom not in appels.outils:
            return JSONResponse({"erreur": "outil inconnu"}, status_code=404)
        return JSONResponse(await appels.outil(nom, d), headers={"cache-control": "no-store"})

    @app.post("/appels/fin")
    async def appel_fin(requete: Request):
        if licence_echue():
            return JSONResponse({"erreur": "licence échue"}, status_code=503)
        corps = await lire(requete, FIN_MAX)
        if corps is None:
            return JSONResponse({"erreur": "requête trop grosse"}, status_code=413)
        statut, reponse = await appels.fin(corps, requete.headers.get("elevenlabs-signature"))
        return JSONResponse(reponse, status_code=statut)
