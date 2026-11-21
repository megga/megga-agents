"""Les routes des clés d'API d'un client (l'entrée par API de ses logiciels), montées par atelier/app.py.

  GET    /clients/{id}/cles               les clés, sans leur valeur
  POST   /clients/{id}/cles               {logiciel, par_minute} : la clé, montrée une seule fois
  DELETE /clients/{id}/cles/{cle}         la retire
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Body, Depends

from noyau import api as entree_api

from . import regles
from .porte import PorteErreur
from .regles import Refus
from .routes_suivi import raison

log = logging.getLogger("megga.atelier")


def monter(r: APIRouter, *, identite, bd, client_de, zone_de, porte) -> None:
    def cles_par_porte(qui, ident: str) -> None:
        c = client_de(qui, ident)
        if zone_de(ident) not in regles.ZONES_PORTE:
            raise Refus(409, "hors Cloudflare, les clés se créent chez le client : python -m noyau.cles creer <logiciel> (docs/api.md)")
        if porte is None:
            raise Refus(503, "porte non réglée (PORTE_URL)")
        if c.get("current_version") is None:
            raise Refus(409, "mettez d'abord une version de l'agent en service : ses clés se gardent dans sa base")

    async def appel_cles(ident: str, methode: str = "GET", chemin: str = "", corps: dict | None = None) -> dict:
        try:
            return await porte.cles(ident, methode, chemin, corps)
        except PorteErreur as e:
            if e.statut in (400, 404, 409):
                raise Refus(e.statut, "clé refusée par le conteneur", {"texte": e.texte}) from e
            raise Refus(502 if e.statut else 504, f"clés indisponibles : {raison(e)}", {"statut": e.statut, "texte": e.texte}) from e

    @r.get("/clients/{ident}/cles")
    async def lister_cles(ident: str, qui=Depends(identite)):
        await bd(cles_par_porte, qui, ident)
        return {"client": ident, **await appel_cles(ident)}

    @r.post("/clients/{ident}/cles", status_code=201)
    async def creer_cle(ident: str, qui=Depends(identite), corps: dict = Body(...)):
        """Une clé pour un logiciel du client : montrée ici une seule fois ; seule son empreinte part au conteneur."""
        logiciel = corps.get("logiciel")
        if not isinstance(logiciel, str) or not entree_api.LOGICIEL.fullmatch(logiciel):
            raise Refus(400, "logiciel : un nom court, en minuscules (lettres, chiffres, tirets, 20 au plus)")
        try:
            debit = entree_api.par_minute(corps.get("par_minute"))
        except ValueError as e:
            raise Refus(400, str(e)) from e
        if qui.role == "client" and debit > entree_api.PAR_MINUTE:
            # Le débit protège la facture des modèles : au-delà du débit par défaut, c'est à MEGGA de le régler.
            raise Refus(403, f"par_minute : au plus {entree_api.PAR_MINUTE} ; davantage se demande à MEGGA")
        await bd(cles_par_porte, qui, ident)
        if qui.role == "client":
            en_service = [c for c in (await appel_cles(ident)).get("cles", []) if not c.get("retiree")]
            if len(en_service) >= entree_api.CLES_CLIENT_MAX:
                raise Refus(409, f"{entree_api.CLES_CLIENT_MAX} clés en service au plus : retirez-en une, ou demandez à MEGGA")
        cle_id, cle, empreinte = entree_api.nouvelle_cle()
        await appel_cles(ident, "POST", corps={"id": cle_id, "logiciel": logiciel, "empreinte": empreinte, "par_minute": debit})
        log.info("clé %s créée pour %s (%s, %s)", cle_id, ident, logiciel, qui.role)
        return {"client": ident, "id": cle_id, "logiciel": logiciel, "par_minute": debit, "cle": cle}

    @r.delete("/clients/{ident}/cles/{cle_id}")
    async def retirer_cle(ident: str, cle_id: str, qui=Depends(identite)):
        if not entree_api.IDENT_CLE.fullmatch(cle_id):
            raise Refus(400, "identifiant de clé")
        await bd(cles_par_porte, qui, ident)
        r = await appel_cles(ident, "DELETE", f"/{cle_id}")
        log.info("clé %s de %s retirée (%s)", cle_id, ident, qui.role)
        return {"client": ident, **r}

