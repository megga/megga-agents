"""Stripe (21.11.2026) : lien de paiement, événements signés, recharge prélevée sous le seuil ; sans réseau (un faux Stripe)."""

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qs

import httpx
import pytest
from fastapi.testclient import TestClient

from atelier.app import creer as creer_atelier
from atelier.stripe import _aplatir, centimes, verifier_signature
from test_alertes import PorteAlertes
from test_forfaits import CATALOGUE
from test_lot5 import ADMIN, MEGGA, jeton_client, nouveau_client
from test_releve import AUJOURDHUI

SECRET = "whsec_essai"


class FauxStripe:
    def __init__(self):
        self.appels, self.payer = [], "paid"

    def __call__(self, r: httpx.Request):
        corps = {k: v[0] for k, v in parse_qs(r.content.decode()).items()}
        self.appels.append((r.method, r.url.path, corps, r.headers.get("idempotency-key")))
        p = r.url.path
        if p == "/v1/customers":
            return httpx.Response(200, json={"id": "cus_1"})
        if p == "/v1/checkout/sessions":
            return httpx.Response(200, json={"id": "cs_1", "url": "https://checkout.stripe.com/c/pay/cs_1"})
        if p == "/v1/billing_portal/sessions":
            return httpx.Response(200, json={"url": "https://billing.stripe.com/p/session/1"})
        if p == "/v1/subscriptions/sub_1":
            return httpx.Response(200, json={"id": "sub_1", "default_payment_method": "pm_1"})
        if p == "/v1/invoices":
            return httpx.Response(200, json={"id": "in_1", "status": "draft"})
        if p == "/v1/invoiceitems" or p.endswith("/finalize"):
            return httpx.Response(200, json={"id": "ii_1"})
        if p.endswith("/pay"):
            if self.payer == "refus":
                return httpx.Response(402, json={"error": {"message": "Your card was declined."}})
            return httpx.Response(200, json={"id": "in_1", "status": self.payer})
        return httpx.Response(404, json={"error": {"message": "inconnu"}})


def signer(corps: bytes, t: int | None = None) -> str:
    t = t or int(time.time())
    return f"t={t},v1=" + hmac.new(SECRET.encode(), f"{t}.".encode() + corps, hashlib.sha256).hexdigest()


def evenement(t, genre: str, objet: dict):
    corps = json.dumps({"id": "evt_1", "type": genre, "data": {"object": objet}}).encode()
    return t.post("/stripe", content=corps, headers={"stripe-signature": signer(corps)})


@pytest.fixture
def atelier(tmp_path):
    faux = FauxStripe()
    t = TestClient(creer_atelier({"ADMIN_TOKEN": ADMIN, "DATABASE_URL": f"sqlite:///{tmp_path}/a.db", "STRIPE_CLE": "sk_test_essai",
                                  "STRIPE_SIGNATURE": SECRET}, porte=PorteAlertes(), transport_stripe=httpx.MockTransport(faux)))
    t.stripe = faux
    nouveau_client(t)
    t.post("/atelier/clients/exemple/versions/1/activer", headers=MEGGA, json={"forcer": True})
    t.put("/atelier/forfaits", headers=MEGGA, json=CATALOGUE)
    t.put("/atelier/clients/exemple/abonnement", headers=MEGGA, json={"forfait": "essentiel", "statut": "essai", "debut": AUJOURDHUI,
                                                                      "rythme": "annuel", "seuil_recharge": 250})
    return t


def test_signature():
    corps = b'{"a":1}'
    verifier_signature(corps, signer(corps), SECRET)
    for mauvais in ("", "t=1", signer(b"autre")):
        with pytest.raises(ValueError):
            verifier_signature(corps, mauvais, SECRET)
    with pytest.raises(ValueError):  # trop vieux : un rejeu ne passe pas
        verifier_signature(corps, signer(corps, int(time.time()) - 600), SECRET)


def test_formulaire_et_centimes():
    assert _aplatir({"a": {"b": [{"c": 1}]}, "d": True, "e": None}) == [("a[b][0][c]", "1"), ("d", "true")]
    assert centimes(232.5, "CHF") == 23250 and centimes(100, "JPY") == 100


def test_lien_puis_paiement(atelier):
    t = atelier
    r = t.post("/atelier/clients/exemple/stripe/lien", headers=MEGGA)
    assert r.status_code == 200 and r.json()["url"].startswith("https://checkout.stripe.com/")
    session = next(c for m, p, c, _ in t.stripe.appels if p == "/v1/checkout/sessions")
    assert session["mode"] == "subscription" and session["line_items[0][price_data][recurring][interval]"] == "year"
    assert session["line_items[0][price_data][unit_amount]"] == "278400"  # 232 × 12
    assert session["subscription_data[metadata][client]"] == "exemple" and session["line_items[0][price_data][currency]"] == "usd"
    # Le paiement : Stripe envoie l'événement, l'abonnement est relié et passe actif.
    assert evenement(t, "checkout.session.completed", {"mode": "subscription", "customer": "cus_1", "subscription": "sub_1",
                                                       "metadata": {"client": "exemple"}}).json() == {"recu": True}
    c = t.get("/atelier/abonnements", headers=MEGGA).json()["clients"][0]
    assert c["abonnement"]["statut"] == "actif" and c["stripe"] == {"relie": True, "recharge_en_cours": False}
    # Un paiement refusé : en retard ; puis payé : actif ; résilié : parti.
    evenement(t, "invoice.payment_failed", {"customer": "cus_1", "metadata": {}})
    assert t.get("/atelier/abonnements", headers=MEGGA).json()["clients"][0]["abonnement"]["statut"] == "retard"
    evenement(t, "invoice.paid", {"customer": "cus_1", "metadata": {}})
    assert t.get("/atelier/abonnements", headers=MEGGA).json()["clients"][0]["abonnement"]["statut"] == "actif"
    assert t.post("/atelier/clients/exemple/stripe/portail", headers=MEGGA).json()["url"].startswith("https://billing.stripe.com/")
    evenement(t, "customer.subscription.deleted", {"customer": "cus_1", "metadata": {}})
    c = t.get("/atelier/abonnements", headers=MEGGA).json()["clients"][0]
    assert c["abonnement"]["statut"] == "parti" and not c["stripe"]["relie"]


def test_evenement_non_signe_refuse(atelier):
    corps = json.dumps({"type": "checkout.session.completed", "data": {"object": {}}}).encode()
    assert atelier.post("/stripe", content=corps, headers={"stripe-signature": "t=1,v1=00"}).status_code == 400
    assert atelier.post("/stripe", content=corps).status_code == 400


def test_recharge_sous_le_seuil(atelier):
    t = atelier
    t.post("/atelier/clients/exemple/stripe/lien", headers=MEGGA)
    evenement(t, "checkout.session.completed", {"mode": "subscription", "customer": "cus_1", "subscription": "sub_1",
                                               "metadata": {"client": "exemple"}})
    # 200 conversations dans le forfait, 4 consommées aujourd'hui : reste 196, sous le seuil de 250.
    r = t.post("/atelier/recharges/evaluer", headers=MEGGA).json()
    assert r == {"branche": True, "recharges": [{"client": "exemple", "resultat": "paid"}]}
    facture = next(c for m, p, c, _ in t.stripe.appels if p == "/v1/invoices")
    assert facture["metadata[type]"] == "recharge" and facture["default_payment_method"] == "pm_1"
    ligne = next(c for m, p, c, _ in t.stripe.appels if p == "/v1/invoiceitems")
    assert ligne["amount"] == "12000" and ligne["invoice"] == "in_1"
    assert all(idem and idem.startswith("recharge-exemple-") for m, p, c, idem in t.stripe.appels if p.startswith("/v1/invoice"))
    c = t.get("/atelier/abonnements", headers=MEGGA).json()["clients"][0]
    assert c["enveloppe"] == 300 and c["recharges"]["nombre"] == 1
    # L'événement de la même facture ne la recompte pas.
    evenement(t, "invoice.paid", {"id": "in_1", "customer": "cus_1", "currency": "usd", "amount_paid": 12000,
                                  "metadata": {"type": "recharge", "client": "exemple", "conversations": "100"}})
    assert t.get("/atelier/abonnements", headers=MEGGA).json()["clients"][0]["enveloppe"] == 300
    # Encore sous le seuil, mais une tentative par heure au plus : rien de plus.
    assert t.post("/atelier/recharges/evaluer", headers=MEGGA).json()["recharges"] == []


def test_recharge_refusee_puis_plafond(atelier):
    t = atelier
    t.stripe.payer = "refus"
    t.post("/atelier/clients/exemple/stripe/lien", headers=MEGGA)
    evenement(t, "checkout.session.completed", {"mode": "subscription", "customer": "cus_1", "subscription": "sub_1",
                                               "metadata": {"client": "exemple"}})
    assert t.post("/atelier/recharges/evaluer", headers=MEGGA).json()["recharges"] == [{"client": "exemple", "resultat": "refusée"}]
    assert t.get("/atelier/abonnements", headers=MEGGA).json()["clients"][0]["enveloppe"] == 200  # rien de compté


def test_sans_stripe_et_droits(tmp_path):
    t = TestClient(creer_atelier({"ADMIN_TOKEN": ADMIN, "DATABASE_URL": f"sqlite:///{tmp_path}/a.db"}, porte=PorteAlertes()))
    nouveau_client(t)
    t.put("/atelier/forfaits", headers=MEGGA, json=CATALOGUE)
    t.put("/atelier/clients/exemple/abonnement", headers=MEGGA, json={"forfait": "essentiel", "debut": AUJOURDHUI})
    assert t.post("/atelier/clients/exemple/stripe/lien", headers=MEGGA).status_code == 503
    assert t.post("/atelier/recharges/evaluer", headers=MEGGA).json() == {"branche": False, "recharges": []}
    assert t.post("/stripe", content=b"{}").status_code == 503
    assert t.post("/atelier/clients/exemple/stripe/lien", headers=jeton_client(t)).status_code == 403
