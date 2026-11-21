"""Stripe, pour les forfaits des clients payants (21.11.2026, décision de Julien) : le lien de paiement d'un abonnement, le
portail où le client gère sa carte, les recharges prélevées sous le seuil, et la vérification des événements que Stripe
envoie. Rien d'autre ne part chez Stripe que l'entreprise du client, son identifiant, le forfait et les montants.

L'API est appelée directement (formulaires encodés, https://docs.stripe.com/api), sans le SDK : quelques appels suffisent.
La clé (STRIPE_CLE) et le secret de signature des événements (STRIPE_SIGNATURE) se posent dans l'objet de l'atelier par la
porte (PUT /admin/atelier/secrets) ; Julien les pose lui-même. Sans clé, les routes de Stripe répondent 503.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any
from urllib.parse import urlencode

import httpx

API = "https://api.stripe.com/v1"
# Un événement plus vieux est refusé : un rejeu ne passe pas (la tolérance de Stripe).
TOLERANCE_S = 300
# Les devises sans centimes chez Stripe (https://docs.stripe.com/currencies#zero-decimal), parmi celles qu'on peut vendre.
SANS_CENTIMES = frozenset({"JPY", "KRW", "VND", "CLP", "XOF", "XAF"})


class StripeErreur(Exception):
    def __init__(self, statut: int, message: str):
        super().__init__(message)
        self.statut = statut
        self.message = message


def centimes(montant: float, devise: str) -> int:
    """Le montant dans la plus petite unité de la devise, comme Stripe l'attend."""
    return int(round(montant)) if devise.upper() in SANS_CENTIMES else int(round(montant * 100))


def _aplatir(donnees: dict, prefixe: str = "") -> list[tuple[str, str]]:
    """Un dictionnaire en champs de formulaire à la manière de Stripe : a[b][0][c]=v."""
    sortie: list[tuple[str, str]] = []
    for k, v in donnees.items():
        cle = f"{prefixe}[{k}]" if prefixe else str(k)
        if v is None:
            continue
        if isinstance(v, dict):
            sortie += _aplatir(v, cle)
        elif isinstance(v, (list, tuple)):
            for i, x in enumerate(v):
                sortie += _aplatir(x, f"{cle}[{i}]") if isinstance(x, dict) else [(f"{cle}[{i}]", str(x))]
        elif isinstance(v, bool):
            sortie.append((cle, "true" if v else "false"))
        else:
            sortie.append((cle, str(v)))
    return sortie


def verifier_signature(corps: bytes, entete: str, secret: str, maintenant: float | None = None) -> None:
    """L'en-tête Stripe-Signature (t=…,v1=…) : un HMAC-SHA256 de « t.corps » avec le secret de signature, récent.
    Lève ValueError si la signature manque, ne correspond pas, ou est trop vieille."""
    morceaux = [p.split("=", 1) for p in (entete or "").split(",") if "=" in p]
    t = next((v for k, v in morceaux if k == "t"), "")
    signatures = [v for k, v in morceaux if k == "v1"]
    if not t.isdigit() or not signatures:
        raise ValueError("signature absente")
    if abs((maintenant or time.time()) - int(t)) > TOLERANCE_S:
        raise ValueError("événement trop vieux")
    attendue = hmac.new(secret.encode(), t.encode() + b"." + corps, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(attendue, s) for s in signatures):
        raise ValueError("signature fausse")


class Stripe:
    def __init__(self, cle: str, transport: httpx.AsyncBaseTransport | None = None):
        self._cle = cle
        self._transport = transport

    async def _appel(self, methode: str, chemin: str, donnees: dict | None = None, idem: str | None = None) -> dict:
        entetes = {"authorization": f"Bearer {self._cle}"}
        if idem:
            entetes["idempotency-key"] = idem  # rejoué, Stripe rend la même réponse sans refaire l'opération
        champs = _aplatir(donnees or {})
        if methode == "POST":
            entetes["content-type"] = "application/x-www-form-urlencoded"
        async with httpx.AsyncClient(transport=self._transport, timeout=30) as c:
            r = await c.request(methode, API + chemin, headers=entetes, content=urlencode(champs) if methode == "POST" else None,
                                params=champs if methode == "GET" else None)
        try:
            corps = r.json()
        except ValueError:
            corps = {}
        if r.status_code >= 400:
            erreur = (corps.get("error") or {}) if isinstance(corps, dict) else {}
            raise StripeErreur(r.status_code, str(erreur.get("message") or f"Stripe {r.status_code}")[:200])
        return corps

    async def client(self, ident: str, entreprise: str | None) -> str:
        c = await self._appel("POST", "/customers", {"name": entreprise or ident, "metadata": {"client": ident}}, idem=f"client-{ident}")
        return c["id"]

    async def lien_abonnement(self, client_stripe: str, ident: str, nom: str, montant: float, devise: str, annuel: bool,
                              retour: str, forfait: str) -> str:
        """Le lien de paiement d'un abonnement (Checkout) : le forfait, son prix, son rythme ; le client y saisit sa carte."""
        session = await self._appel("POST", "/checkout/sessions", {
            "mode": "subscription",
            "customer": client_stripe,
            "line_items": [{"quantity": 1, "price_data": {
                "currency": devise.lower(), "unit_amount": centimes(montant, devise),
                "recurring": {"interval": "year" if annuel else "month"},
                "product_data": {"name": nom},
            }}],
            "subscription_data": {"metadata": {"client": ident, "forfait": forfait}},
            "metadata": {"client": ident, "forfait": forfait},
            "success_url": retour,
            "cancel_url": retour,
        })
        return session["url"]

    async def portail(self, client_stripe: str, retour: str) -> str:
        """Le portail du client : sa carte, ses factures, la résiliation."""
        return (await self._appel("POST", "/billing_portal/sessions", {"customer": client_stripe, "return_url": retour}))["url"]

    async def moyen_de_paiement(self, abonnement: str) -> str | None:
        """La carte de l'abonnement, celle que la recharge prélève."""
        a = await self._appel("GET", f"/subscriptions/{abonnement}")
        pm = a.get("default_payment_method")
        return pm.get("id") if isinstance(pm, dict) else pm

    async def facturer_recharge(self, client_stripe: str, moyen: str | None, montant: float, devise: str, description: str,
                                metadata: dict[str, Any], idem: str) -> dict:
        """Une facture d'un paquet de recharge, prélevée tout de suite sur la carte de l'abonnement. Chaque étape porte sa
        clé d'idempotence : rejouée après une coupure, elle ne crée ni ne prélève une seconde fois."""
        facture = await self._appel("POST", "/invoices", {
            "customer": client_stripe, "collection_method": "charge_automatically", "auto_advance": True,
            "pending_invoice_items_behavior": "exclude", "currency": devise.lower(), "description": description,
            "default_payment_method": moyen, "metadata": metadata,
        }, idem=f"{idem}-facture")
        await self._appel("POST", "/invoiceitems", {
            "customer": client_stripe, "invoice": facture["id"], "amount": centimes(montant, devise), "currency": devise.lower(),
            "description": description,
        }, idem=f"{idem}-ligne")
        await self._appel("POST", f"/invoices/{facture['id']}/finalize", {"auto_advance": True}, idem=f"{idem}-finale")
        return await self._appel("POST", f"/invoices/{facture['id']}/pay", {}, idem=f"{idem}-paiement")
