"""Ce que les appels laissent (noyau/appels.py) : la table des appels pour l'Activité de la gestion, et le dernier appel dans
le Contexte de l'écrit."""

from __future__ import annotations

import asyncio
import time

from sqlalchemy import Column, Float, String, Text, insert, select, update
from sqlalchemy.exc import IntegrityError

from .rappels import date_longue
from .stockage import PERSONNE, _table

APPEL_RETENU = 48 * 3600  # le dernier appel reste dans le Contexte de l'écrit deux jours
REPRISE_S = 300  # un traitement de fin resté en cours au-delà se reprend au webhook suivant


def duree_dite(s: float) -> str:
    m = int(round(float(s or 0) / 60))
    return "moins d'une minute" if m < 1 else f"{m} minute{'s' if m > 1 else ''}"


class TableAppels:
    """Les appels, pour l'Activité de la gestion (table megga_appels) : qui, quand, combien de temps, le résumé envoyé."""

    def __init__(self, url: str):
        self._e, self._t = _table(
            url,
            "megga_appels",
            Column("conversation", String(80), primary_key=True),
            Column("personne", String(PERSONNE), nullable=False, index=True),
            Column("nom", String(80), nullable=False, default=""),
            Column("role", String(20), nullable=False, default=""),
            Column("quand", Float, nullable=False, index=True),
            Column("duree", Float, nullable=False, default=0),
            Column("resume", Text, nullable=False, default=""),
            Column("statut", String(20), nullable=False, default=""),
            Column("pris", Float, nullable=False, default=0),
        )

    def reserver(self, conversation: str, personne: str, nom: str, role: str, quand: float, duree: float,
                 maintenant: float | None = None) -> bool:
        """Note l'appel ; faux s'il l'est déjà (ElevenLabs renvoie un webhook en cas de doute), sauf un traitement en échec ou
        resté en cours plus de cinq minutes (un conteneur arrêté en route) : il se reprend."""
        maintenant = time.time() if maintenant is None else maintenant
        valeurs = dict(personne=personne, nom=nom[:80], role=role[:20], quand=quand, duree=duree, resume="", statut="en_cours",
                       pris=maintenant)
        t = self._t
        try:
            with self._e.begin() as c:
                c.execute(insert(t).values(conversation=conversation[:80], **valeurs))
            return True
        except IntegrityError:
            with self._e.begin() as c:
                repris = c.execute(update(t).where(t.c.conversation == conversation[:80], (t.c.statut == "echec") | (
                    (t.c.statut == "en_cours") & (t.c.pris < maintenant - REPRISE_S))).values(**valeurs)).rowcount
            return bool(repris)

    def finir(self, conversation: str, resume: str, statut: str) -> None:
        with self._e.begin() as c:
            c.execute(update(self._t).where(self._t.c.conversation == conversation[:80]).values(resume=resume, statut=statut[:20]))

    def depuis(self, quand: float, limite: int = 100) -> list[dict]:
        t = self._t
        with self._e.connect() as c:
            lignes = c.execute(select(t.c.personne, t.c.nom, t.c.role, t.c.quand, t.c.duree, t.c.resume, t.c.statut)
                               .where(t.c.quand >= quand).order_by(t.c.quand.desc()).limit(limite))
            return [dict(l._mapping) for l in lignes]


def contexte_appel(etats, fuseau: str):
    """Le dernier appel d'une personne, pour le Contexte de l'écrit (deux jours) : async f(personne) -> texte."""

    async def dernier(personne: str) -> str:
        if etats is None or not personne or personne.startswith("api:"):
            return ""
        a = await asyncio.to_thread(etats.lire, personne, "dernier_appel")
        if not a or time.time() - float(a.get("quand") or 0) > APPEL_RETENU:
            return ""
        return (f"Vous vous êtes parlé au téléphone le {date_longue(float(a['quand']), fuseau)} ({duree_dite(a.get('duree'))}). "
                f"Le résumé qu'elle a reçu par écrit : « {str(a.get('resume') or '')[:1200]} ». Les répliques sont dans le fil.")

    return dernier
