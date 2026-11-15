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

    async def activer(self, conf: Config, version: int) -> dict:
        """Inscrit la configuration dans l'annuaire et redémarre le conteneur du client."""
        async with self._client() as c:
            r = await c.put(f"/admin/clients/{conf.id}/config", json={"version": version, "config": conf.model_dump(mode="json")})
        if r.status_code != 200:
            raise PorteErreur(r.status_code, r.text[:200])
        return r.json()

    async def etats(self) -> dict[str, dict]:
        """L'état de chaque client dans l'annuaire (actif, version, conteneur)."""
        async with self._client() as c:
            r = await c.get("/admin/clients")
        if r.status_code != 200:
            raise PorteErreur(r.status_code, r.text[:200])
        return {e["id"]: e for e in r.json().get("clients", [])}
