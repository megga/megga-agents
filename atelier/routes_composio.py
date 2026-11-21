"""Les routes des connecteurs de Composio d'un client (noyau/composio.py), montées par atelier/app.py.

  GET    /clients/{id}/composio/comptes   les comptes que le client a connectés (boîte d'outils, état), sans jeton
  POST   /clients/{id}/composio/lien      MEGGA : {auth_config, retour?} un lien de Composio pour connecter un compte

Le client est un utilisateur du projet Composio de MEGGA, sous son identifiant. Les outils que son agent reçoit se
règlent dans sa configuration (Config.composio, réglage de MEGGA), pas ici.
"""

from __future__ import annotations

import logging
import re

import httpx
from fastapi import APIRouter, Body, Depends

from noyau import composio

from .regles import Refus

log = logging.getLogger("megga.atelier")
RETOUR = re.compile(r"^https://\S{4,500}$")


def monter(r: APIRouter, *, identite, megga, bd, client_de, cle: str | None, transport=None) -> None:
    def cle_composio() -> str:
        if not cle:
            raise Refus(503, "Composio non réglé (COMPOSIO_API_KEY)")
        return cle

    def erreur(e: Exception) -> Refus:
        if isinstance(e, composio.ComposioErreur) and e.statut in (400, 404, 409):
            return Refus(400, "refusé par Composio", {"texte": e.texte[:300]})
        log.warning("Composio injoignable : %s", e)
        return Refus(502, "Composio injoignable")

    @r.get("/clients/{ident}/composio/comptes")
    async def comptes(ident: str, qui=Depends(identite)):
        await bd(client_de, qui, ident)
        try:
            return {"client": ident, "comptes": await composio.comptes(cle_composio(), ident, transport=transport)}
        except (composio.ComposioErreur, httpx.HTTPError) as e:
            raise erreur(e) from e

    @r.post("/clients/{ident}/composio/lien", status_code=201)
    async def lien(ident: str, qui=Depends(identite), corps: dict = Body(...)):
        """Le lien à envoyer au client : il y connecte lui-même son compte, MEGGA ne voit jamais ses identifiants."""
        megga(qui)
        await bd(client_de, qui, ident)
        auth_config, retour = corps.get("auth_config"), corps.get("retour")
        if not isinstance(auth_config, str) or not composio.AUTH_CONFIG.fullmatch(auth_config):
            raise Refus(400, "auth_config : l'identifiant d'une configuration d'authentification Composio (ac_...)")
        if retour is not None and (not isinstance(retour, str) or not RETOUR.fullmatch(retour)):
            raise Refus(400, "retour : une adresse https")
        try:
            return {"client": ident, **await composio.lien(cle_composio(), ident, auth_config, retour, transport=transport)}
        except (composio.ComposioErreur, httpx.HTTPError) as e:
            raise erreur(e) from e
