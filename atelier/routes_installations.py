"""Les routes des installations hors Cloudflare (chez le client, zone suisse), montées par atelier/app.py.

  GET    /installations                           MEGGA : les installations et leur dernier relevé
  GET    /clients/{id}/installation               l'installation, ses derniers ordres et le journal du pilotage
  PUT    /clients/{id}/installation               MEGGA : {cle_publique} remise par l'installation
  DELETE /clients/{id}/installation               MEGGA : révoque sa clé
  POST   /clients/{id}/installation/image         MEGGA : {version, image} une version d'image proposée
"""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends

from noyau import pilotage as pilotages

from . import regles
from .regles import Refus


def monter(r: APIRouter, *, identite, megga, bd, client_de, zone_de, canal, versions, verrous) -> None:
    def hors_porte(qui, ident: str) -> dict:
        """Le client, s'il tourne hors Cloudflare (chez lui, zone suisse) : son installation se pilote."""
        c = client_de(qui, ident)
        if zone_de(ident) in regles.ZONES_PORTE:
            raise Refus(409, "ce client est servi par la porte de Cloudflare : il n'a pas d'installation à piloter")
        return c

    @r.get("/installations")
    def installations(qui=Depends(identite)):
        megga(qui)
        # cle_pilotage : l'atelier a sa clé et peut signer des ordres (scripts/pilotage.py poser).
        return {"installations": canal.toutes({c["component_id"]: c.get("current_version") for c in versions.clients()}),
                "cle_pilotage": canal.cle is not None}

    @r.get("/clients/{ident}/installation")
    def installation(ident: str, qui=Depends(identite)):
        c = hors_porte(qui, ident)
        return {"client": ident, "version_en_service": c.get("current_version"), **canal.vue(ident, c.get("current_version"))}

    @r.put("/clients/{ident}/installation")
    def enregistrer_installation(ident: str, qui=Depends(identite), corps: dict = Body(...)):
        """La mise en service d'une installation : MEGGA enregistre la clé publique qu'elle lui a remise."""
        megga(qui)
        hors_porte(qui, ident)
        try:
            empreinte = canal.enregistrer(ident, corps.get("cle_publique"))
        except pilotages.PilotageRefuse as e:
            raise Refus(400, str(e)) from e
        return {"client": ident, "cle": empreinte}

    @r.delete("/clients/{ident}/installation")
    def revoquer_installation(ident: str, qui=Depends(identite)):
        megga(qui)
        hors_porte(qui, ident)
        return {"client": ident, "revoquee": canal.revoquer(ident)}

    @r.post("/clients/{ident}/installation/image", status_code=201)
    async def proposer_image(ident: str, qui=Depends(identite), corps: dict = Body(...)):
        """Une version d'image pour l'installation : son pilote la vérifie et l'installe (MISES_A_JOUR=oui), sinon la propose."""
        megga(qui)
        await bd(hors_porte, qui, ident)
        contenu = {"version": corps.get("version"), "image": corps.get("image")}
        if not (isinstance(contenu["version"], str) and pilotages.VERSION_IMAGE.fullmatch(contenu["version"])):
            raise Refus(400, "version : celle de l'image, par exemple 0.2.0")
        if not (isinstance(contenu["image"], str) and pilotages.IMAGE.fullmatch(contenu["image"])):
            raise Refus(400, "image : ghcr.io/megga/megga-agents@sha256:<empreinte>, l'image signée par MEGGA")
        if canal.cle is None:
            raise Refus(503, "clé de pilotage absente : l'atelier ne peut pas signer d'ordre (scripts/pilotage.py poser)")
        async with verrous[ident]:
            ordre = await bd(canal.deposer, ident, "image", contenu, qui.role)
        return {"client": ident, "ordre": ordre["numero"], **contenu}

