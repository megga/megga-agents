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

    async def appel(self, compte: str, methode: str, chemin: str, corps=None, fichiers=None, params=None,
                    brut: tuple[bytes, str] | None = None) -> dict:
        """Un appel à la gestion au nom de ce compte ; une panne ou un refus devient une GestionErreur (statut 0 : sans réponse).

        `fichiers` : un formulaire multipart ; `brut` : (octets, type) envoyés tels quels (un PDF)."""
        if not compte:
            raise GestionErreur(403, "aucun compte de gestion pour cette personne")
        if not chemin.startswith("/") or ".." in chemin:
            raise GestionErreur(400, "chemin de gestion")
        entetes = {"authorization": f"Bearer {self._cle}", "x-gestion-compte": compte}
        options: dict = {"params": params}
        if brut is not None:
            options["content"], entetes["content-type"] = brut
        elif fichiers is not None:
            options["files"], options["data"] = fichiers, corps
        elif corps is not None:
            options["json"] = corps
        try:
            async with httpx.AsyncClient(transport=self._transport, timeout=self._delai) as c:
                r = await c.request(methode, f"{self._url}/api/gestion{chemin}", headers=entetes, **options)
        except httpx.HTTPError as e:
            raise GestionErreur(0, f"la gestion ne répond pas ({type(e).__name__})") from e
        try:
            donnees = r.json()
        except ValueError:
            donnees = {}
        if r.status_code >= 400:
            raise GestionErreur(r.status_code, str((donnees or {}).get("erreur") or f"la gestion répond {r.status_code}")[:300])
        return donnees if isinstance(donnees, dict) else {"donnees": donnees}

    async def octets(self, compte: str, chemin: str, maximum: int = 15_000_000) -> bytes:
        """Un fichier du site lu sous la gestion (une photo : /gestion/images/<fichier>)."""
        if not chemin.startswith("/gestion/") or ".." in chemin:
            raise GestionErreur(400, "chemin de fichier")
        try:
            async with httpx.AsyncClient(transport=self._transport, timeout=self._delai) as c:
                r = await c.get(f"{self._url}{chemin}", headers={"authorization": f"Bearer {self._cle}", "x-gestion-compte": compte})
        except httpx.HTTPError as e:
            raise GestionErreur(0, f"la gestion ne répond pas ({type(e).__name__})") from e
        if r.status_code >= 400 or len(r.content) > maximum:
            raise GestionErreur(r.status_code, "fichier absent ou trop lourd")
        return r.content

    def lien_signe(self, dossier: str, fichier: str, duree: int = 3600, maintenant: float | None = None) -> str:
        """Un lien temporaire vers une photo ou une vidéo du site (que Meta va chercher lui-même), signé de la clé."""
        import hashlib
        import hmac
        import time

        prefixe = {"images": "photo", "videos": "video"}[dossier]
        fin = int((time.time() if maintenant is None else maintenant) + duree)
        signature = hmac.new(self._cle.encode(), f"{prefixe}:{fichier}:{fin}".encode(), hashlib.sha256).hexdigest()
        return f"{self._url}/{dossier}/{fichier}?jeton={fin}.{signature}"

    def site_du_bien(self, identifiant: str) -> str:
        """L'adresse du site d'un bien : celui de son préfixe (« marbella-… ») s'il en a un, sinon le site principal."""
        for prefixe, url in self.reglage.sites.items():
            if str(identifiant).startswith(f"{prefixe}-"):
                return url.rstrip("/")
        return self._url
