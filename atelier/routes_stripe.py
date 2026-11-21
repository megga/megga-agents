"""Les routes de Stripe (21.11.2026), montées par atelier/app.py.

  POST /atelier/clients/{id}/stripe/lien     MEGGA : le lien de paiement de l'abonnement du client (Checkout)
  POST /atelier/clients/{id}/stripe/portail  MEGGA : le portail du client (sa carte, ses factures, la résiliation)
  POST /atelier/recharges/evaluer            MEGGA : prélève une recharge pour chaque client sous son seuil ; la porte
                                             l'appelle toutes les 5 minutes, après les alertes
  POST /stripe                               Stripe : ses événements, signés (paiement, échec, résiliation, recharge)

Le statut d'un abonnement suit Stripe : payé, actif ; échec de paiement, en retard ; résilié, parti. Une recharge n'est
comptée qu'une fois sa facture payée (l'événement), une seule fois par facture. Garde-fous : une tentative par heure et par
client, RECHARGES_MAX tentatives par mois d'abonnement, rien sans un seuil choisi ni une carte enregistrée.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from .forfaits import Abonnements, lire_catalogue, prix_du_mois, vue
from .regles import Refus
from .stripe import SANS_CENTIMES, Stripe, StripeErreur, verifier_signature

log = logging.getLogger("megga.atelier")

RECHARGES_MAX = 5  # tentatives de recharge automatique par client et par mois d'abonnement
ECART_S = 3600  # entre deux tentatives pour un même client
EN_COURS_S = 24 * 3600  # une recharge sans réponse de Stripe au-delà est oubliée
TAILLE_EVENEMENT = 256 * 1024
JOURS_DU_MOIS = 31


def montant(centimes: int, devise: str) -> float:
    return float(centimes) if devise.upper() in SANS_CENTIMES else round(centimes / 100, 2)


def traiter(evenement: dict, abonnements: Abonnements) -> str:
    """Un événement de Stripe appliqué aux abonnements ; rend ce qui a été fait (pour le journal), sans rien de privé."""
    genre = evenement.get("type") or ""
    o = (evenement.get("data") or {}).get("object") or {}
    meta = o.get("metadata") or {}
    client = meta.get("client") if meta.get("client") in abonnements.tous() else abonnements.par_client_stripe(o.get("customer") or "")
    if client is None:
        return "client inconnu"
    s = abonnements.stripe(client)
    recharge = meta.get("type") == "recharge"
    if genre == "checkout.session.completed" and o.get("mode") == "subscription":
        abonnements.ecrire_stripe(client, {**s, "client": o.get("customer"), "abonnement": o.get("subscription")})
        # Actif seulement une fois payé : un paiement encore en attente passe par invoice.paid.
        if o.get("payment_status") in ("paid", "no_payment_required"):
            abonnements.statut(client, "actif")
        return "abonnement relié"
    if genre == "invoice.paid" and recharge:
        if int(o.get("amount_paid") or 0) <= 0:  # une facture à zéro n'achète rien (un brouillon resté vide)
            return "recharge à zéro ignorée"
        devise = (o.get("currency") or "usd").upper()
        abonnements.recharger(client, int(meta.get("conversations") or 0), montant(int(o.get("amount_paid") or 0), devise),
                              "stripe", reference=o.get("id"))
        if (s.get("recharge_en_cours") or {}).get("facture") == o.get("id"):
            abonnements.ecrire_stripe(client, {**s, "recharge_en_cours": None})
        return "recharge payée"
    if genre == "invoice.payment_failed" and recharge:
        abonnements.ecrire_stripe(client, {**s, "recharge_en_cours": None,
                                           "recharge_echec": {"quand": time.time(), "facture": o.get("id")}})
        return "recharge refusée"
    if genre == "invoice.paid":
        abonnements.statut(client, "actif")
        return "mois payé"
    if genre == "invoice.payment_failed":
        abonnements.statut(client, "retard")
        return "paiement refusé"
    if genre == "customer.subscription.updated":
        etat = o.get("status")
        if etat in ("past_due", "unpaid"):
            abonnements.statut(client, "retard")
        elif etat == "active":
            abonnements.statut(client, "actif")
        return f"abonnement {etat}"
    if genre == "customer.subscription.deleted":
        abonnements.ecrire_stripe(client, {**s, "abonnement": None})
        abonnements.statut(client, "parti")
        return "abonnement résilié"
    return "ignoré"


def monter(app, r: APIRouter, *, identite, megga, bd, reglages, abonnements: Abonnements, client_de, rassembler_tout,
           stripe: Stripe | None, secret: str | None) -> None:
    verrou = asyncio.Lock()

    def branche() -> Stripe:
        if stripe is None:
            raise Refus(503, "Stripe n'est pas branché (STRIPE_CLE)")
        return stripe

    async def client_stripe(ident: str, entreprise: str | None) -> dict:
        s = await bd(abonnements.stripe, ident)
        if not s.get("client"):
            s = {**s, "client": await branche().client(ident, entreprise)}
            await bd(abonnements.ecrire_stripe, ident, s)
        return s

    def erreur(e: StripeErreur) -> Refus:
        return Refus(502, f"Stripe : {e.message}")

    @r.post("/clients/{ident}/stripe/lien")
    async def lien(ident: str, qui=Depends(identite)):
        megga(qui)
        c = await bd(client_de, qui, ident)
        a = (await bd(abonnements.tous)).get(ident)
        if a is None:
            raise Refus(409, "aucun abonnement : choisissez d'abord un forfait")
        if (await bd(abonnements.stripe, ident)).get("abonnement"):
            # Un second lien créerait un second abonnement, payé deux fois : le portail change la carte ou résilie.
            raise Refus(409, "déjà abonné par Stripe : passez par le portail du client")
        catalogue = await bd(lire_catalogue, reglages)
        f = next((x for x in catalogue.forfaits if x.id == a.forfait), None)
        if f is None:
            raise Refus(409, "forfait retiré")
        annuel = a.rythme == "annuel"
        prix = round(prix_du_mois(f, a.rythme) * (12 if annuel else 1), 2)
        try:
            s = await client_stripe(ident, c.get("description"))
            url = await branche().lien_abonnement(s["client"], ident, f"{f.nom}, {'annuel' if annuel else 'mensuel'}", prix,
                                                  catalogue.devise, annuel, catalogue.retour_paiement, f.id)
        except StripeErreur as e:
            raise erreur(e) from e
        return {"client": ident, "url": url}

    @r.post("/clients/{ident}/stripe/portail")
    async def portail(ident: str, qui=Depends(identite)):
        megga(qui)
        await bd(client_de, qui, ident)
        s = await bd(abonnements.stripe, ident)
        if not s.get("client"):
            raise Refus(409, "ce client n'a pas encore payé par Stripe")
        try:
            url = await branche().portail(s["client"], (await bd(lire_catalogue, reglages)).retour_paiement)
        except StripeErreur as e:
            raise erreur(e) from e
        return {"client": ident, "url": url}

    @r.post("/recharges/evaluer")
    async def evaluer_recharges(qui=Depends(identite)):
        megga(qui)
        if stripe is None:
            return {"branche": False, "recharges": []}
        if verrou.locked():
            return {"branche": True, "recharges": [], "deja_en_cours": True}
        async with verrou:
            return {"branche": True, "recharges": await recharger_sous_le_seuil()}

    async def recharger_sous_le_seuil() -> list[dict]:
        catalogue, tous, tous_stripe = await bd(lire_catalogue, reglages), await bd(abonnements.tous), await bd(abonnements.tous_stripe)
        recharges = await bd(abonnements.recharges, time.time() - (JOURS_DU_MOIS + 1) * 86400)
        try:
            releve = await rassembler_tout(JOURS_DU_MOIS)
        except Refus:
            return []  # sans le relevé, on ne sait pas qui est sous son seuil : rien n'est prélevé
        v = vue(catalogue, tous, recharges, releve, datetime.now(timezone.utc).date(), tous_stripe)
        forfaits = {f.id: f for f in catalogue.forfaits}
        maintenant, faites = time.time(), []
        for ligne in v["clients"]:
            ident, a = ligne["client"], tous[ligne["client"]]
            s, f = tous_stripe.get(ident) or {}, forfaits.get(a.forfait)
            if (a.statut != "actif" or a.seuil_recharge is None or f is None or f.recharge is None or not s.get("abonnement")
                    or ligne["reste"] > a.seuil_recharge):
                continue
            en_cours = s.get("recharge_en_cours") or {}
            if en_cours and maintenant - en_cours.get("quand", 0) < EN_COURS_S:
                continue
            if maintenant - s.get("derniere_tentative", 0) < ECART_S:
                continue
            mois = ligne["mois"]["debut"]
            tentatives = (s.get("tentatives") or {}).get(mois, 0)
            if tentatives >= RECHARGES_MAX:
                faites.append({"client": ident, "resultat": "plafond du mois"})
                continue
            s = {**s, "derniere_tentative": maintenant, "tentatives": {mois: tentatives + 1}}
            meta = {"type": "recharge", "client": ident, "conversations": f.recharge.conversations, "mois": mois}
            try:
                moyen = await stripe.moyen_de_paiement(s["abonnement"])
                facture = await stripe.facturer_recharge(
                    s["client"], moyen, f.recharge.prix, catalogue.devise, f"Recharge de {f.recharge.conversations} conversations",
                    meta, idem=f"recharge-{ident}-{mois}-{tentatives + 1}")
                s["recharge_en_cours"] = {"facture": facture.get("id"), "quand": maintenant}
                if facture.get("status") == "paid":  # payée tout de suite : comptée, l'événement ne la recomptera pas
                    await bd(abonnements.recharger, ident, f.recharge.conversations, f.recharge.prix, "stripe",
                             None, facture.get("id"))
                    s["recharge_en_cours"] = None
                faites.append({"client": ident, "resultat": facture.get("status") or "envoyée"})
            except StripeErreur as e:
                s["recharge_echec"] = {"quand": maintenant, "message": e.message}
                faites.append({"client": ident, "resultat": "refusée"})
                log.warning("recharge de %s refusée : %s", ident, e.message)
            await bd(abonnements.ecrire_stripe, ident, s)
        return faites

    @app.post("/stripe")
    async def evenement(requete: Request):
        """Un événement de Stripe : pas de jeton, une signature (STRIPE_SIGNATURE)."""
        if not secret:
            return JSONResponse({"erreur": "Stripe n'est pas branché"}, status_code=503)
        corps = bytearray()
        async for morceau in requete.stream():
            corps += morceau
            if len(corps) > TAILLE_EVENEMENT:
                return JSONResponse({"erreur": "événement trop gros"}, status_code=413)
        try:
            verifier_signature(bytes(corps), requete.headers.get("stripe-signature", ""), secret)
            e = json.loads(bytes(corps))
        except ValueError as err:
            log.warning("événement Stripe refusé : %s", err)
            return JSONResponse({"erreur": "signature"}, status_code=400)
        fait = await bd(traiter, e, abonnements)
        log.info("Stripe %s : %s", e.get("type"), fait)
        return {"recu": True}

