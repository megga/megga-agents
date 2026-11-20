"""Les routes des alertes envoyées (MEGGA seulement), montées par atelier/app.py.

  GET    /alertes                          les mesures, les règles, les destinations (masquées) et l'état de chaque règle
  PUT    /alertes/regles                   [règles] remplace toutes les règles
  POST   /alertes/destinations             {id, genre, adresse} ; la clé de signature d'une adresse web, montrée une fois
  DELETE /alertes/destinations/{id}        refusé tant qu'une règle l'utilise
  POST   /alertes/destinations/{id}/essai  un message d'essai
  POST   /alertes/evaluer                  évalue toutes les règles et envoie ; la porte l'appelle toutes les 5 minutes
"""

from __future__ import annotations

import asyncio
import json
import time

from fastapi import APIRouter, Body, Depends
from pydantic import ValidationError

from . import regles as regles_atelier
from .alertes import FENETRE_MAX, MESURES, Etats, regles_de, valider_regles
from .avertir import Destination, envoyer, evaluer, montrer, nouvelle_destination
from .regles import Refus

TAILLE_REGLES = 19_000  # un réglage tient en 20 000 caractères (noyau/stockage.py, Reglages)


def monter(r: APIRouter, *, identite, megga, bd, reglages, etats: Etats, porte, rassembler_tout, transport=None) -> None:
    verrou = asyncio.Lock()

    def destinations() -> list[Destination]:
        return [Destination.model_validate(d) for d in reglages.lire("alertes.destinations") or []]

    def regles():
        return regles_de(reglages.lire("alertes.regles"))

    def refus_validation(e: Exception) -> Refus:
        if isinstance(e, ValidationError):
            return Refus(422, "réglage invalide", regles_atelier.erreurs(e))
        return Refus(422, str(e))

    @r.get("/alertes")
    def lire(qui=Depends(identite)):
        megga(qui)
        tous = etats.tous()
        return {
            "mesures": {k: {"libelle": v[0], "unite": v[1]} for k, v in MESURES.items()},
            "fenetre_max": FENETRE_MAX,
            "proposees": reglages.lire("alertes.regles") is None,
            "regles": [x.model_dump() for x in regles()],
            "destinations": [montrer(d) for d in destinations()],
            "etats": [{k: v for k, v in e.items()} for e in sorted(tous.values(), key=lambda e: (e["regle"], e["client"]))],
        }

    @r.put("/alertes/regles")
    def regler(qui=Depends(identite), corps: list = Body(...)):
        megga(qui)
        try:
            liste = valider_regles(corps)
        except (ValidationError, ValueError) as e:
            raise refus_validation(e) from e
        connues = {d.id for d in destinations()}
        inconnues = sorted({i for x in liste for i in x.destinations} - connues)
        if inconnues:
            raise Refus(422, f"destinations inconnues : {', '.join(inconnues)}")
        donnees = [x.model_dump() for x in liste]
        if len(json.dumps(donnees, ensure_ascii=False)) > TAILLE_REGLES:
            raise Refus(422, "trop de règles ou de clients nommés")
        reglages.ecrire("alertes.regles", donnees)
        return {"regles": donnees}

    @r.post("/alertes/destinations", status_code=201)
    def ajouter(qui=Depends(identite), corps: dict = Body(...)):
        megga(qui)
        existantes = destinations()
        try:
            d = nouvelle_destination(corps, existantes)
        except (ValidationError, ValueError) as e:
            raise refus_validation(e) from e
        reglages.ecrire("alertes.destinations", [x.model_dump() for x in [*existantes, d]])
        return {**montrer(d), **({"secret": d.secret} if d.secret else {})}

    @r.delete("/alertes/destinations/{ident}")
    def retirer(ident: str, qui=Depends(identite)):
        megga(qui)
        existantes = destinations()
        if not any(d.id == ident for d in existantes):
            raise Refus(404, "destination inconnue")
        if any(ident in x.destinations for x in regles()):
            raise Refus(409, "une règle l'utilise encore")
        reglages.ecrire("alertes.destinations", [x.model_dump() for x in existantes if x.id != ident])
        return {"retiree": ident}

    @r.post("/alertes/destinations/{ident}/essai")
    async def essayer(ident: str, qui=Depends(identite)):
        megga(qui)
        d = next((x for x in await bd(destinations) if x.id == ident), None)
        if d is None:
            raise Refus(404, "destination inconnue")
        texte = "Essai : les alertes de la console de MEGGA arrivent ici."
        raison = await envoyer(d, {"sujet": "Essai des alertes MEGGA", "texte": texte,
                                   "donnees": {"envoi": "essai", "quand": int(time.time())}}, porte, transport)
        if raison:
            raise Refus(502, f"envoi en échec : {raison}")
        return {"envoye": True}

    @r.post("/alertes/evaluer")
    async def evaluer_tout(qui=Depends(identite)):
        megga(qui)
        if verrou.locked():
            return {"en_cours": True}
        async with verrou:
            rassemble = await rassembler_tout(FENETRE_MAX)
            return await evaluer(await bd(regles), await bd(destinations), rassemble, etats, porte, bd, time.time(), transport)
