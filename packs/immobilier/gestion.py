"""La gestion du site d'une agence (son API /api/gestion/…), appelée au nom d'un compte de gestionnaire.

Repris d'Alix FSP (gestion.js) : la clé partagée avec le site (secret GESTION_CLE) et le compte du
gestionnaire (secret GESTIONNAIRES, noyau/roles.py), en en-tête. Les outils des packs (annonces, photos,
fiches…) passent tous par ici. Rien d'une agence en particulier : l'adresse et les sites viennent de sa
configuration (Config.gestion).
"""

from __future__ import annotations

import httpx

from noyau.config import Gestion as ReglageGestion


class GestionErreur(Exception):
    def __init__(self, statut: int, message: str):
        super().__init__(message)
        self.statut = statut
        self.message = message


class Gestion:
    def __init__(self, reglage: ReglageGestion, cle: str, transport: httpx.AsyncBaseTransport | None = None, delai: float = 60):
        if not cle:
            raise ValueError("GESTION_CLE manquante")
        self.reglage = reglage
        self._url = reglage.url.rstrip("/")
        self._cle = cle
        self._transport = transport
        self._delai = delai

    async def appel(self, compte: str, methode: str, chemin: str, corps=None, fichiers=None) -> dict:
        """Un appel à la gestion au nom de ce compte ; une panne ou un refus devient une GestionErreur (statut 0 : sans réponse)."""
        if not compte:
            raise GestionErreur(403, "aucun compte de gestion pour cette personne")
        if not chemin.startswith("/") or ".." in chemin:
            raise GestionErreur(400, "chemin de gestion")
        entetes = {"authorization": f"Bearer {self._cle}", "x-gestion-compte": compte}
        try:
            async with httpx.AsyncClient(transport=self._transport, timeout=self._delai) as c:
                r = await c.request(methode, f"{self._url}/api/gestion{chemin}", headers=entetes,
                                    json=corps if fichiers is None else None, data=corps if fichiers is not None else None,
                                    files=fichiers)
        except httpx.HTTPError as e:
            raise GestionErreur(0, f"la gestion ne répond pas ({type(e).__name__})") from e
        try:
            donnees = r.json()
        except ValueError:
            donnees = {}
        if r.status_code >= 400:
            raise GestionErreur(r.status_code, str((donnees or {}).get("erreur") or f"la gestion répond {r.status_code}")[:300])
        return donnees if isinstance(donnees, dict) else {"donnees": donnees}

    def site_du_bien(self, identifiant: str) -> str:
        """L'adresse du site d'un bien : celui de son préfixe (« marbella-… ») s'il en a un, sinon le site principal."""
        for prefixe, url in self.reglage.sites.items():
            if str(identifiant).startswith(f"{prefixe}-"):
                return url.rstrip("/")
        return self._url
