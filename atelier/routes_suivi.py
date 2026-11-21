"""Les routes du suivi d'un client, montées par atelier/app.py : ses chiffres, ses alertes, et ses conversations pour lui
seul (MEGGA suit la santé et les chiffres, jamais ce qui se dit).

  GET  /clients/{id}/suivi[?jours=]                   l'activité de la période ; pour MEGGA, avec les coûts
  GET  /clients/{id}/conversations[?limite=]          le client seul
  GET  /clients/{id}/conversations/{personne}         le client seul
  GET  /clients/{id}/alertes[?jours=]                 pannes, écart de version, alertes du conteneur
"""

from __future__ import annotations

import json
import time

from fastapi import APIRouter, Depends, Request

from noyau import pilotage as pilotages
from noyau.suivi import PERSONNE

from . import regles
from .couts import couts
from .pilotage import Pilotage
from .porte import PorteErreur
from .regles import Refus

def jours_de(valeur: str | None) -> int:
    try:
        jours = int(valeur or 7)
    except ValueError:
        raise Refus(400, "jours : un nombre de 1 à 365") from None
    if not 1 <= jours <= 365:
        raise Refus(400, "jours : un nombre de 1 à 365")
    return jours

def limite_de(valeur: str | None) -> int | None:
    if valeur is None:
        return None
    if not valeur.isdigit() or not 1 <= int(valeur) <= 200:
        raise Refus(400, "limite : un nombre de 1 à 200")
    return int(valeur)

def raison(e: PorteErreur) -> str:
    """Ce qui a empêché la lecture, dit simplement."""
    if e.statut == 0:
        return "la porte n'a pas répondu"
    if e.statut == 401:
        return "le conteneur refuse la lecture (jeton interne : le jeton d'administration a-t-il changé ?)"
    try:
        erreur = json.loads(e.texte).get("erreur")
    except (ValueError, AttributeError):
        erreur = None
    if erreur == "conteneur injoignable":
        return "le conteneur du client ne répond pas"
    if erreur == "suivi indisponible" or "suivi indisponible" in e.texte:
        return "le conteneur répond, mais sa base n'est pas branchée"
    return f"réponse inattendue du conteneur ({e.statut})"

def debut(jours: int) -> int:
    """Le début de la période, arrondi à 5 minutes : des lectures rapprochées tombent sur la lecture
    gardée en mémoire par la porte, sans réveiller le conteneur du client."""
    return int((time.time() - jours * 86400) // 300 * 300)


def monter(r: APIRouter, *, identite, bd, client_de, zone_de, porte, versions, resume, etats_porte, canal: Pilotage,
           pilote_fenetres, lire_tarifs) -> None:
    def suivable(qui, ident: str, conversations: bool = False) -> tuple[dict, bool]:
        """Le client, et si son suivi passe par la porte (zones Europe et États-Unis) ou par le pilotage
        (hors Cloudflare : le dernier relevé de son installation, jamais ses conversations).

        Les conversations d'un client ne se lisent que par lui : MEGGA suit la santé et les chiffres, jamais ce qui se
        dit (décision de Julien, 20.11.2026, qui remplace celle du 15.11.2026)."""
        c = client_de(qui, ident)
        if conversations and qui.role == "megga":
            raise Refus(403, "les conversations d'un client ne se lisent que par lui")
        if zone_de(ident) not in regles.ZONES_PORTE:
            if conversations:
                raise Refus(409, "les conversations d'une installation hors Cloudflare ne la quittent jamais : elles se lisent chez le client")
            return c, False
        if porte is None:
            raise Refus(503, "porte non réglée (PORTE_URL)")
        return c, True

    async def lire_suivi(ident: str, chemin: str = "", **params) -> dict:
        try:
            return await porte.suivi(ident, chemin, **params)
        except PorteErreur as e:
            if e.statut in (400, 404):
                raise Refus(e.statut, "suivi refusé", {"texte": e.texte}) from e
            raise Refus(502 if e.statut else 504, f"suivi indisponible : {raison(e)}",
                        {"statut": e.statut, "texte": e.texte}) from e

    @r.get("/clients/{ident}/suivi")
    async def suivi(ident: str, requete: Request, qui=Depends(identite)):
        jours = jours_de(requete.query_params.get("jours"))
        c, par_porte = await bd(suivable, qui, ident)
        derniere = (await bd(versions.dernieres, {ident})).get(ident)
        if par_porte:
            activite = await lire_suivi(ident, depuis=debut(jours))
            sortie = {**resume(c, derniere, await etats_porte(ident)), "periode_jours": jours, "activite": activite}
        else:
            if jours not in pilote_fenetres:
                raise Refus(400, "jours : 1, 7 ou 30 pour une installation hors Cloudflare")
            try:
                activite, inst = await bd(canal.suivi, ident, jours)
            except pilotages.PilotageRefuse as e:
                raise Refus(409, f"suivi indisponible : {e}") from e
            sortie = {**resume(c, derniere, None, canal.bref(inst, c.get("current_version"))), "periode_jours": jours,
                      "activite": activite}
        if qui.role == "megga":
            try:
                sortie["couts"] = couts(activite, await bd(lire_tarifs))
            except (TypeError, ValueError, AttributeError, ArithmeticError):
                if par_porte:
                    raise
                sortie["couts"] = {"erreur": "activité illisible"}  # le relevé d'une installation, pas notre code
        return sortie

    @r.get("/clients/{ident}/conversations")
    async def conversations(ident: str, requete: Request, qui=Depends(identite)):
        limite = limite_de(requete.query_params.get("limite"))
        await bd(suivable, qui, ident, True)
        return await lire_suivi(ident, "/conversations", limite=limite)

    @r.get("/clients/{ident}/conversations/{personne}")
    async def echanges(ident: str, personne: str, requete: Request, qui=Depends(identite)):
        limite = limite_de(requete.query_params.get("limite"))
        if not PERSONNE.fullmatch(personne):
            raise Refus(400, "personne : un numéro, ou api:<logiciel>:<identifiant>")
        await bd(suivable, qui, ident, True)
        return await lire_suivi(ident, f"/conversations/{personne}", limite=limite)

    @r.get("/clients/{ident}/alertes")
    async def alertes(ident: str, requete: Request, qui=Depends(identite)):
        jours = jours_de(requete.query_params.get("jours"))
        c, par_porte = await bd(suivable, qui, ident)
        maintenant = time.time()
        depuis = debut(jours)
        if not par_porte:
            liste = await bd(canal.alertes, ident, depuis, c.get("current_version"))
            return {"periode_jours": jours, "alertes": sorted(liste, key=lambda x: x["quand"] or 0, reverse=True)}
        liste = []
        etats = await etats_porte(ident)
        if etats is None:
            liste.append({"quand": maintenant, "genre": "porte_injoignable", "detail": ""})
        else:
            a = etats.get(ident) or {}
            if a and a.get("version") != c.get("current_version"):
                liste.append({"quand": maintenant, "genre": "ecart",
                              "detail": f"l'annuaire sert la version {a.get('version')}, l'atelier la {c.get('current_version')}"})
            for panne in (a.get("conteneur") or {}).get("alertes") or []:
                if panne.get("quand", 0) / 1000 >= depuis:
                    resolue = panne.get("resolue")
                    liste.append({"quand": panne["quand"] / 1000, "genre": f"conteneur_{panne.get('quoi')}",
                                  "detail": panne.get("message", ""), "resolue": resolue / 1000 if resolue else None})
        try:
            liste += (await lire_suivi(ident, "/alertes", depuis=depuis)).get("alertes", [])
        except Refus as e:
            liste.append({"quand": maintenant, "genre": "conteneur_injoignable", "detail": e.message})
        return {"periode_jours": jours, "alertes": sorted(liste, key=lambda x: x["quand"], reverse=True)}

