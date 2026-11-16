"""Le lien avec la porte Cloudflare : l'annuaire D1 et le conteneur de chaque client.

Mettre en service une configuration, c'est l'inscrire dans l'annuaire et redémarrer
le conteneur du client, qui la relira à son réveil. La porte s'en charge, par sa
route d'administration (jeton ADMIN_TOKEN).
"""

from __future__ import annotations

import httpx

from noyau.config import Config


class PorteErreur(Exception):
    def __init__(self, statut: int, texte: str):
        super().__init__(f"porte {statut} : {texte}")
        self.statut = statut
        self.texte = texte


class Porte:
    def __init__(self, url: str, jeton: str, transport: httpx.AsyncBaseTransport | None = None):
        if not url.startswith("https://") and transport is None:
            raise ValueError("PORTE_URL : une adresse https")
        self._url = url.rstrip("/")
        self._jeton = jeton
        self._transport = transport

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._url, transport=self._transport, timeout=30,
            headers={"authorization": f"Bearer {self._jeton}"},
        )

    async def _appel(self, methode: str, chemin: str, **options) -> dict:
        """Un appel à la porte ; toute panne (refus, délai, réseau) devient une PorteErreur.

        Statut 0 : la porte n'a pas répondu, on ne sait pas si elle a agi.
        """
        try:
            async with self._client() as c:
                r = await c.request(methode, chemin, **options)
        except httpx.HTTPError as e:
            raise PorteErreur(0, f"sans réponse ({type(e).__name__})") from e
        if r.status_code != 200:
            raise PorteErreur(r.status_code, r.text[:200])
        try:
            return r.json()
        except ValueError as e:
            raise PorteErreur(r.status_code, "réponse illisible") from e

    async def activer(self, conf: Config, version: int) -> dict:
        """Inscrit la configuration dans l'annuaire et fait redémarrer le conteneur du client."""
        return await self._appel("PUT", f"/admin/clients/{conf.id}/config",
                                 json={"version": version, "config": conf.model_dump(mode="json")})

    async def suivi(self, ident: str, chemin: str = "", **params) -> dict:
        """Le suivi d'un client, lu dans son conteneur (qui se réveille s'il dormait)."""
        return await self._appel("GET", f"/admin/clients/{ident}/suivi{chemin}",
                                 params={k: v for k, v in params.items() if v is not None} or None)

    async def etats(self, ident: str | None = None) -> dict[str, dict]:
        """L'état des clients dans l'annuaire (actif, version, conteneur) ; d'un seul si `ident`."""
        params = {"id": ident} if ident else None
        d = await self._appel("GET", "/admin/clients", params=params)
        return {e["id"]: e for e in d.get("clients", [])}

    async def decider(self, ident: str, numero: int, accord: bool) -> dict:
        """Une demande d'accord d'un client (noyau/approbations.py), accordée (et faite) ou refusée."""
        return await self._appel("POST", f"/admin/clients/{ident}/approbations/{int(numero)}", json={"accord": accord})
    async def reprise(self, ident: str, numero: int, corps: dict) -> dict:
        """Une conversation confiée à l'équipe d'un client (noyau/reprises.py) : prise, répondue ou rendue."""
        return await self._appel("POST", f"/admin/clients/{ident}/reprises/{int(numero)}", json=corps)

    async def connaissances(self, ident: str, methode: str = "GET", chemin: str = "", corps: dict | None = None) -> dict:
        """La base de connaissances d'un client, gardée dans sa base : lister, ajouter un document, en retirer un."""
        return await self._appel(methode, f"/admin/clients/{ident}/connaissances{chemin}", json=corps, timeout=120)

    async def cles(self, ident: str, methode: str = "GET", chemin: str = "", corps: dict | None = None) -> dict:
        """Les clés des logiciels d'un client, gardées dans sa base : lister, ajouter (une empreinte), retirer."""
        return await self._appel(methode, f"/admin/clients/{ident}/cles{chemin}", json=corps)
