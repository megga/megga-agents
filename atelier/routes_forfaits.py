"""Les routes des forfaits et des clients payants (MEGGA seulement), montées par atelier/app.py.

  GET    /forfaits                         le catalogue : devise, multiplicateur visé, forfaits
  PUT    /forfaits                         remplace le catalogue ; un forfait encore pris par un client ne se retire pas
  GET    /abonnements                      les clients payants et leur mois en cours, d'après le relevé chiffré
  PUT    /clients/{id}/abonnement          l'abonnement du client (forfait, rythme, statut, début, seuil de recharge)
  DELETE /clients/{id}/abonnement          retire un abonnement saisi par erreur (un client qui part passe « parti »)
  POST   /clients/{id}/recharges           {conversations, prix} une recharge achetée hors Stripe
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends
from pydantic import ValidationError

from . import regles as regles_atelier
from .forfaits import CLE, Abonnement, Abonnements, Catalogue, Recharge, lire_catalogue, vue
from .regles import Refus
from .releves import JOURS_LUS_MAX

# Un mois d'abonnement tient en 31 jours : le relevé et les recharges sont lus sur cette fenêtre.
JOURS_DU_MOIS = 31


def monter(r: APIRouter, *, identite, megga, bd, reglages, abonnements: Abonnements, client_de, rassembler_tout) -> None:
    assert JOURS_DU_MOIS <= JOURS_LUS_MAX

    def invalide(e: ValidationError, quoi: str) -> Refus:
        return Refus(422, f"{quoi} invalide", regles_atelier.erreurs(e))

    @r.get("/forfaits")
    def forfaits(qui=Depends(identite)):
        megga(qui)
        return lire_catalogue(reglages).model_dump()

    @r.put("/forfaits")
    def regler_forfaits(qui=Depends(identite), corps: dict = Body(...)):
        megga(qui)
        try:
            c = Catalogue.model_validate(corps)
        except ValidationError as e:
            raise invalide(e, "catalogue") from e
        gardes = {f.id for f in c.forfaits}
        pris = sorted({a.forfait for a in abonnements.tous().values()} - gardes)
        if pris:
            raise Refus(409, "forfait encore pris par un client : " + ", ".join(pris))
        reglages.ecrire(CLE, c.model_dump())
        return c.model_dump()

    @r.get("/abonnements")
    async def payants(qui=Depends(identite)):
        megga(qui)
        catalogue, tous = await bd(lire_catalogue, reglages), await bd(abonnements.tous)
        recharges = await bd(abonnements.recharges, time.time() - (JOURS_DU_MOIS + 1) * 86400)
        try:
            releve, lisible = await rassembler_tout(JOURS_DU_MOIS), True
        except Refus:  # la porte ne répond pas : les abonnements restent, sans les conversations ni les coûts
            releve, lisible = {}, False
        sortie = vue(catalogue, tous, recharges, releve, datetime.now(timezone.utc).date())
        return {**sortie, "releve_lisible": lisible}

    @r.put("/clients/{ident}/abonnement")
    def regler_abonnement(ident: str, qui=Depends(identite), corps: dict = Body(...)):
        megga(qui)
        client_de(qui, ident)
        try:
            a = Abonnement.model_validate(corps)
        except ValidationError as e:
            raise invalide(e, "abonnement") from e
        if a.forfait not in {f.id for f in lire_catalogue(reglages).forfaits}:
            raise Refus(422, f"forfait inconnu : {a.forfait}")
        abonnements.regler(ident, a)
        return {"client": ident, **a.model_dump()}

    @r.delete("/clients/{ident}/abonnement")
    def retirer_abonnement(ident: str, qui=Depends(identite)):
        megga(qui)
        client_de(qui, ident)
        if not abonnements.retirer(ident):
            raise Refus(404, "aucun abonnement")
        return {"client": ident, "retire": True}

    @r.post("/clients/{ident}/recharges", status_code=201)
    def recharger(ident: str, qui=Depends(identite), corps: dict = Body(...)):
        megga(qui)
        client_de(qui, ident)
        if ident not in abonnements.tous():
            raise Refus(409, "aucun abonnement : une recharge s'ajoute à un forfait")
        try:
            p = Recharge.model_validate(corps)
        except ValidationError as e:
            raise invalide(e, "recharge") from e
        return abonnements.recharger(ident, p.conversations, p.prix, "manuel")
