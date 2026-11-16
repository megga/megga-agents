"""Les leads et les connecteurs d'un client (lot 9.4).

Les leads (groupe d'outils « leads ») : quand une personne a un vrai besoin, l'agent en fait une fiche structurée
(`enregistrer_lead` : besoin, budget, délai, lieu, nom, score de 1 à 5), gardée dans la base du client
(stockage.Leads) et envoyée, en arrière-plan, au webhook https du client (Config.leads : son CRM, un tableur,
Zapier), signée par LEADS_SECRET (« x-megga-signature: sha256=… », le HMAC du corps) s'il est posé. Un envoi en
échec est retenté une fois ; il reste lisible dans la console. Les ventes sont le cas d'usage qui croît le plus
(Zapier 2026) : un lead noté sur-le-champ, à toute heure, ne se perd plus.

Les connecteurs (groupe « connecteurs ») : les serveurs MCP du client (Config.mcp), le standard des connecteurs
(Linux Foundation) ; Agno s'y connecte au début d'un tour et laisse de côté un serveur injoignable. Chaque serveur ne
propose que les outils qu'on a nommés, préfixés de son nom (« crm_creer_contact »), et ses actions passent par les
approbations du lot 9.1 comme les autres (une règle par nom préfixé).
"""

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import hmac
import json
import logging

import httpx
from agno.run import RunContext

log = logging.getLogger("megga")

CONSIGNE_LEADS = ("Quand une personne a un vrai besoin (achat, vente, location, devis, rendez-vous), enregistre-le "
                  "(enregistrer_lead) dès que tu le connais, avec un score de 1 (curieux) à 5 (prêt à décider) ; "
                  "complète-le plus tard s'il le faut. Ne le présente pas comme une formalité.")
ESSAIS_ENVOI = 2
PAUSE_ENVOI = 2.0  # secondes entre deux essais


def signature(secret: str, corps: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), corps, hashlib.sha256).hexdigest()


def _court(v, n: int) -> str:
    return " ".join(str(v or "").split())[:n]


class Leads:
    """Les leads d'un client : `magasin` (stockage.Leads), `webhook` (son adresse ou None), `secret` (LEADS_SECRET)."""

    def __init__(self, magasin, webhook: str | None = None, secret: str = "", client: str = "", agent: str = "",
                 transport: httpx.AsyncBaseTransport | None = None):
        self.magasin, self.webhook, self.secret = magasin, webhook, secret
        self.client, self.agent, self._transport = client, agent, transport
        self._taches: set[asyncio.Task] = set()

    def outils(self) -> list:
        leads = self

        async def enregistrer_lead(besoin: str, score: int, run_context: RunContext, budget: str = "", delai: str = "",
                                   lieu: str = "", nom: str = "") -> str:
            """Enregistre la fiche d'une personne qui a un vrai besoin, pour l'équipe commerciale.

            Args:
                besoin: ce qu'elle cherche, en une phrase (« un 4 pièces à Nyon, à acheter »).
                score: de 1 (curieux) à 5 (prêt à décider).
                budget: son budget, s'il est connu.
                delai: quand, s'il est connu (« d'ici l'été »).
                lieu: où, s'il est connu.
                nom: son nom, s'il l'a donné.
            """
            personne = getattr(run_context, "user_id", None) or ""
            try:
                score = int(score)
            except (TypeError, ValueError):
                score = 0
            if not 1 <= score <= 5:
                return "score : un nombre de 1 à 5."
            if not _court(besoin, 500):
                return "besoin : ce que la personne cherche, en une phrase."
            fiche = {"besoin": _court(besoin, 500), "score": score, "budget": _court(budget, 80), "delai": _court(delai, 80),
                     "lieu": _court(lieu, 120), "nom": _court(nom, 120)}
            ident = await asyncio.to_thread(leads.magasin.noter, personne, fiche)
            if leads.webhook:
                t = asyncio.get_running_loop().create_task(leads.envoyer(ident, personne, fiche))
                leads._taches.add(t)
                t.add_done_callback(leads._taches.discard)
                return f"Lead {ident} enregistré et transmis à l'équipe commerciale."
            return f"Lead {ident} enregistré pour l'équipe."

        return [enregistrer_lead]

    async def envoyer(self, ident: int, personne: str, fiche: dict) -> bool:
        """La fiche au webhook du client, signée ; retentée une fois. Rend vrai si elle est partie."""
        corps = json.dumps({"client": self.client, "agent": self.agent, "lead": {
            "id": ident, **fiche, "contact": personne, "quand": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}},
            ensure_ascii=False).encode()
        entetes = {"content-type": "application/json", "user-agent": "megga-agents"}
        if self.secret:
            entetes["x-megga-signature"] = signature(self.secret, corps)
        erreur = ""
        for essai in range(ESSAIS_ENVOI):
            try:
                async with httpx.AsyncClient(timeout=10, transport=self._transport) as c:
                    r = await c.post(self.webhook, content=corps, headers=entetes)
                if 200 <= r.status_code < 300:
                    await asyncio.to_thread(self.magasin.marquer, ident, "envoye")
                    return True
                erreur = f"statut {r.status_code}"
            except httpx.HTTPError as e:
                erreur = type(e).__name__
            if essai + 1 < ESSAIS_ENVOI:
                await asyncio.sleep(PAUSE_ENVOI)
        log.warning("lead %s non transmis au webhook : %s", ident, erreur)
        await asyncio.to_thread(self.magasin.marquer, ident, "echec", erreur)
        return False


def outils_mcp(serveurs, env: dict) -> list:
    """Les serveurs MCP du client, prêts pour Agno (qui s'y connecte au début d'un tour). Un serveur dont le jeton n'est
    pas posé est laissé de côté, et le journal le dit."""
    if not serveurs:
        return []
    from agno.tools.mcp import MCPTools
    from agno.tools.mcp.params import StreamableHTTPClientParams

    boites = []
    for s in serveurs:
        entetes = {}
        if s.jeton:
            jeton = env.get(f"MCP_JETON_{s.jeton}")
            if not jeton:
                log.warning("serveur MCP %s sans son jeton (MCP_JETON_%s) : laissé de côté", s.nom, s.jeton)
                continue
            entetes["Authorization"] = f"Bearer {jeton}"
        boites.append(MCPTools(server_params=StreamableHTTPClientParams(url=s.url, headers=entetes, timeout=15),
                               transport="streamable-http", include_tools=list(s.outils) or None,
                               tool_name_prefix=s.nom, timeout_seconds=15))  # Agno ajoute « _ » : « crm_creer_contact »
    return boites
