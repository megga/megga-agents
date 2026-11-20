"""Les forfaits des clients payants (20.11.2026), décisions de Julien : l'unité vendue est la conversation, l'enveloppe
vide se recharge seule sous un seuil, Stripe tiendra les paiements, et le prix vise trois fois notre coût.

Une conversation, c'est une personne servie sur une journée (UTC) : le relevé la compte déjà (« personnes » de chaque
jour). L'enveloppe d'un mois, c'est les conversations du forfait, plus celles des recharges achetées pendant le mois.
Le mois d'un abonnement court d'une date anniversaire à la suivante, quel que soit son rythme de paiement : un forfait
annuel garde une enveloppe par mois.

Le catalogue est un réglage de l'atelier (clé « forfaits ») ; l'abonnement de chaque client et ses recharges ont leurs
tables. Tant que Stripe n'est pas branché, MEGGA les règle à la main ; aucune conversation n'est lue, seulement des chiffres.
"""

from __future__ import annotations

import calendar
import json
import time
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import Column, Float, Integer, String, delete, insert, select, update

from noyau.stockage import _table

CLE = "forfaits"
STATUTS = ("essai", "actif", "retard", "parti")
# Les statuts qui paient leur forfait : un client en retard doit encore son mois.
PAYANTS = ("actif", "retard")
# Proche de l'enveloppe vide sans seuil réglé : moins de 10 % restants.
PROCHE_PART = 0.10


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Recharge(Strict):
    """Le paquet qu'achète une recharge."""

    conversations: int = Field(gt=0, le=1_000_000)
    prix: float = Field(ge=0)


class Forfait(Strict):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,39}$")
    nom: str = Field(min_length=1, max_length=60)
    prix_mensuel: float = Field(ge=0)
    conversations: int = Field(ge=0, le=10_000_000)  # par mois
    remise_annuelle: float = Field(default=0, ge=0, le=50)  # en %, sur le prix mensuel payé à l'année
    recharge: Recharge | None = None


class Catalogue(Strict):
    devise: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    # Le prix visé, en multiple de notre coût : il ne fixe aucun prix, il sert de repère à l'écran.
    multiplicateur: float = Field(default=3, gt=0, le=50)
    forfaits: list[Forfait] = Field(default=[], max_length=20)

    @model_validator(mode="after")
    def ids_uniques(self):
        ids = [f.id for f in self.forfaits]
        if len(ids) != len(set(ids)):
            raise ValueError("deux forfaits ont le même identifiant")
        return self


class Abonnement(Strict):
    forfait: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,39}$")
    rythme: Literal["mensuel", "annuel"] = "mensuel"
    statut: Literal["essai", "actif", "retard", "parti"] = "essai"
    debut: str  # AAAA-MM-JJ, le premier jour du premier mois
    # Sous ce nombre de conversations restantes, une recharge part seule (Stripe) ; vide : jamais.
    seuil_recharge: int | None = Field(default=None, ge=0, le=1_000_000)

    @field_validator("debut")
    @classmethod
    def date_iso(cls, v: str) -> str:
        try:
            date.fromisoformat(v)
        except ValueError as e:
            raise ValueError("debut : une date AAAA-MM-JJ") from e
        return v


def lire_catalogue(reglages) -> Catalogue:
    return Catalogue.model_validate(reglages.lire(CLE) or {})


def debut_du_mois(debut: date, jour: date) -> date:
    """Le début du mois d'abonnement qui contient `jour` : la dernière date anniversaire de `debut` (le 31 tombe au dernier
    jour d'un mois plus court). Avant le début, le début."""
    if jour <= debut:
        return debut
    annee, mois = jour.year, jour.month
    for _ in range(2):
        d = date(annee, mois, min(debut.day, calendar.monthrange(annee, mois)[1]))
        if d <= jour:
            return max(d, debut)
        annee, mois = (annee - 1, 12) if mois == 1 else (annee, mois - 1)
    return debut


def prix_du_mois(f: Forfait, rythme: str) -> float:
    return round(f.prix_mensuel * (1 - f.remise_annuelle / 100), 2) if rythme == "annuel" else f.prix_mensuel


class Abonnements:
    """L'abonnement de chaque client (megga_abonnements) et ses recharges (megga_recharges)."""

    def __init__(self, url: str):
        self._e, self._a = _table(
            url,
            "megga_abonnements",
            Column("client", String(63), primary_key=True),
            Column("valeur", String(2000), nullable=False),
            # Les identifiants Stripe du client, quand le paiement sera branché.
            Column("stripe", String(500), nullable=True),
            Column("maj_le", Float, nullable=False),
        )
        _, self._r = _table(
            url,
            "megga_recharges",
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("client", String(63), nullable=False, index=True),
            Column("quand", Float, nullable=False),
            Column("conversations", Integer, nullable=False),
            Column("prix", Float, nullable=False),
            Column("source", String(20), nullable=False),
        )

    def tous(self) -> dict[str, Abonnement]:
        with self._e.connect() as c:
            lignes = c.execute(select(self._a.c.client, self._a.c.valeur)).all()
        return {l.client: Abonnement.model_validate(json.loads(l.valeur)) for l in lignes}

    def regler(self, client: str, a: Abonnement) -> None:
        t, v = self._a, json.dumps(a.model_dump(), ensure_ascii=False)
        with self._e.begin() as c:
            if c.execute(select(t.c.client).where(t.c.client == client)).first():
                c.execute(update(t).where(t.c.client == client).values(valeur=v, maj_le=time.time()))
            else:
                c.execute(insert(t).values(client=client, valeur=v, maj_le=time.time()))

    def retirer(self, client: str) -> bool:
        with self._e.begin() as c:
            return c.execute(delete(self._a).where(self._a.c.client == client)).rowcount > 0

    def recharger(self, client: str, conversations: int, prix: float, source: str, quand: float | None = None) -> dict:
        r = {"client": client, "quand": quand or time.time(), "conversations": conversations, "prix": prix, "source": source}
        with self._e.begin() as c:
            c.execute(insert(self._r).values(**r))
        return r

    def recharges(self, depuis: float) -> list[dict]:
        with self._e.connect() as c:
            return [dict(l) for l in c.execute(select(self._r).where(self._r.c.quand >= depuis).order_by(self._r.c.quand)).mappings()]


def vue(catalogue: Catalogue, abonnements: dict[str, Abonnement], recharges: list[dict], releve: dict, aujourdhui: date) -> dict:
    """Les clients payants : pour chacun, son mois en cours (enveloppe, conversations, revenu, coût, marge) ; puis les totaux.

    `releve` : le relevé rassemblé (atelier/releves.py) sur au moins 31 jours ; `recharges` : celles des 31 derniers jours.
    La marge ne se calcule que si le catalogue et les tarifs sont dans la même devise.
    """
    forfaits = {f.id: f for f in catalogue.forfaits}
    par_client = {c["id"]: c for c in releve.get("clients") or []}
    meme_devise = releve.get("devise") == catalogue.devise
    lignes = []
    for client, a in sorted(abonnements.items()):
        f = forfaits.get(a.forfait)
        c = par_client.get(client) or {}
        debut = debut_du_mois(date.fromisoformat(a.debut), aujourdhui)
        depuis = debut.isoformat()
        jours = {j: v for j, v in (c.get("jours") or {}).items() if j >= depuis}
        consommees = sum(int(v.get("personnes") or 0) for v in jours.values())
        cout = round(sum(float(v.get("cout") or 0) for v in jours.values()), 4)
        debut_s = _epoch(debut)
        achats = [r for r in recharges if r["client"] == client and r["quand"] >= debut_s]
        enveloppe = (f.conversations if f else 0) + sum(r["conversations"] for r in achats)
        # Un abonnement qui n'a pas commencé n'encaisse rien ce mois-ci.
        paie = a.statut in PAYANTS and date.fromisoformat(a.debut) <= aujourdhui
        revenu = round((prix_du_mois(f, a.rythme) if f and paie else 0) + sum(r["prix"] for r in achats), 2)
        reste = enveloppe - consommees
        seuil = a.seuil_recharge if a.seuil_recharge is not None else enveloppe * PROCHE_PART
        lignes.append({
            "client": client,
            "entreprise": c.get("entreprise"),
            "abonnement": a.model_dump(),
            "forfait_inconnu": f is None,
            "mois": {"debut": depuis},
            "enveloppe": enveloppe,
            "consommees": consommees,
            "reste": reste,
            "proche": a.statut != "parti" and enveloppe > 0 and reste <= seuil,
            "recharges": {"nombre": len(achats), "conversations": sum(r["conversations"] for r in achats),
                          "prix": round(sum(r["prix"] for r in achats), 2)},
            "revenu": revenu,
            "cout": cout,
            "marge": round(revenu - cout, 2) if meme_devise else None,
        })
    compte = {s: sum(1 for l in lignes if l["abonnement"]["statut"] == s) for s in STATUTS}
    revenu = round(sum(l["revenu"] for l in lignes), 2)
    # Le coût de tous les abonnés, essais compris : un essai coûte sans rapporter, la marge le dit.
    cout = round(sum(l["cout"] for l in lignes), 4)
    return {
        "devise": catalogue.devise,
        "devise_couts": releve.get("devise"),
        "catalogue": catalogue.model_dump(),
        "clients": lignes,
        "totaux": {**compte, "revenu": revenu, "cout": cout, "marge": round(revenu - cout, 2) if meme_devise else None,
                   "proches": sum(1 for l in lignes if l["proche"])},
    }


def _epoch(d: date) -> float:
    """Minuit UTC du jour : les jours du relevé sont en UTC."""
    return float(calendar.timegm(d.timetuple()))
