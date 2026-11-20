"""Les paramètres que le courtier règle dans la gestion de son site (Four Seasons, nouvelle gestion, 19.11.2026).

La configuration d'un client est la version en service dans l'atelier. Greg règle aussi quelques paramètres lui-même,
dans sa gestion (GET /api/gestion/alix/reglages, gestion/alix-reglages.mjs du site) : ils se posent par-dessus cette
version, relus avant chaque tour (au plus toutes les 30 secondes), et servent dès le message suivant, sans redémarrer.

Un réglage absent laisse celui de la version. Une configuration qui ne se valide pas, ou une gestion qui ne répond pas,
laisse l'agent tel qu'il est : jamais de panne pour un réglage.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable

from pydantic import ValidationError

from noyau.config import Config

from .gestion import Gestion, GestionErreur

log = logging.getLogger(__name__)

CHEMIN = "/alix/reglages"
INTERVALLE = 30.0
# Une gestion qui ne connaît pas encore la route (404) : on ne la redemande qu'au bout de dix minutes.
SANS_ROUTE = 600.0
DELAI = 4.0


def appliquer(base: Config, reglages: dict) -> Config:
    """La version en service avec les réglages de la gestion par-dessus ; lève ValidationError si le résultat ne tient pas."""
    d = base.model_dump()
    r = reglages or {}
    for cle, chemin in (("voix_modele", ("voix", "modele")), ("voix_vitesse", ("voix", "vitesse")), ("voix_stabilite", ("voix", "stabilite")),
                        ("modele", ("modeles", "principal")), ("secours", ("modeles", "secours"))):
        if cle in r:
            d[chemin[0]][chemin[1]] = r[cle]
    if "reactions" in r:
        d["reactions"] = bool(r["reactions"])
    if "bonjour" in r:
        d["bonjour"] = r["bonjour"]
    roles = d.get("roles") or {}
    if "humeur" in r and roles.get("gestionnaire"):
        roles["gestionnaire"]["humeur"] = r["humeur"]
    # Les appels (noyau/appels.py) : seulement pour un client qui les a ; la durée se règle en minutes.
    appels = d.get("appels")
    if appels is not None:
        for cle, champ in (("appels", "accepter"), ("appels_qui", "qui")):
            if cle in r:
                appels[champ] = r[cle]
        if "appels_duree" in r:
            appels["duree_max"] = int(r["appels_duree"]) * 60
    accueil = r.get("accueil")
    if isinstance(accueil, dict) and roles.get("visiteur"):
        roles["visiteur"]["accueil"] = {**(roles["visiteur"].get("accueil") or {}),
                                        **{k: v for k, v in accueil.items() if k in ("fr", "en") and isinstance(v, str) and v.strip()}}
    return Config.model_validate(d)


def appliquer_au_mieux(base: Config, reglages: dict) -> tuple[Config, list[str]]:
    """Tous les réglages si possible ; sinon chacun de ceux qui tiennent, un à un, et la liste des refusés : un réglage
    faux n'emporte pas les autres."""
    try:
        return appliquer(base, reglages), []
    except (ValidationError, ValueError, KeyError, TypeError):
        pass
    gardes, refuses = {}, []
    for cle, valeur in reglages.items():
        try:
            appliquer(base, {**gardes, cle: valeur})
            gardes[cle] = valeur
        except (ValidationError, ValueError, KeyError, TypeError):
            refuses.append(cle)
    return appliquer(base, gardes), refuses


class ReglagesDeLaGestion:
    """Relit les réglages du courtier et les fait servir (`servir`, une Config) quand ils changent."""

    def __init__(self, gestion: Gestion, comptes: str | list[str], base: Config, servir: Callable[[Config], None],
                 intervalle: float = INTERVALLE, horloge: Callable[[], float] = time.monotonic):
        self.gestion = gestion
        # Les comptes des gestionnaires : les réglages se lisent au nom d'un administrateur ; un compte refusé (403)
        # cède la place au suivant, et celui qui répond est gardé.
        self.comptes = [comptes] if isinstance(comptes, str) else list(dict.fromkeys(comptes))
        self.compte = self.comptes[0] if self.comptes else ""
        self.base = base
        self.servir = servir
        self.intervalle = intervalle
        self.horloge = horloge
        self.vus: dict | None = None
        self._prochain = 0.0
        self._verrou = asyncio.Lock()

    async def rafraichir(self, forcer: bool = False) -> None:
        """`forcer` : relus même s'ils l'ont été il y a moins de trente secondes (au décrochage d'un appel, noyau/appels.py :
        Greg coupe les appels d'un clic, le suivant le sait)."""
        if (not forcer and self.horloge() < self._prochain) or self._verrou.locked():
            return
        async with self._verrou:
            self._prochain = self.horloge() + self.intervalle
            r = None
            for compte in [self.compte, *(c for c in self.comptes if c != self.compte)]:
                try:
                    r = await self.gestion.appel(compte, "GET", CHEMIN, delai=DELAI)
                    self.compte = compte
                    break
                except GestionErreur as e:
                    if e.statut in (401, 403):
                        continue
                    if e.statut == 404:
                        self._prochain = self.horloge() + SANS_ROUTE
                    else:
                        log.warning("réglages de la gestion illisibles (%s) : %s", e.statut, e.message[:200])
                    return
            if r is None:  # aucun compte n'est administrateur : une seule ligne au journal, puis dix minutes de silence
                self._prochain = self.horloge() + SANS_ROUTE
                log.warning("réglages de la gestion : aucun compte de gestionnaire n'y a droit")
                return
            reglages = r.get("reglages") if isinstance(r.get("reglages"), dict) else {}
            reglages = {k: v for k, v in reglages.items() if k != "modifie"}
            if reglages == self.vus:
                return
            nouvelle, refuses = appliquer_au_mieux(self.base, reglages)
            if refuses:
                log.error("réglages de la gestion refusés : %s", ", ".join(refuses))
            self.vus = reglages  # pas de nouvel essai tant qu'ils ne changent pas
            self.servir(nouvelle)
            log.info("réglages de la gestion servis : %s", ", ".join(sorted(reglages)) or "aucun (version en service)")
