"""Les connecteurs de Composio : les outils d'un client dans ses propres comptes (Gmail, Agenda, HubSpot, Notion...).

Composio (https://composio.dev, SDK sous licence MIT) tient plus de mille boîtes d'outils et les connexions des
comptes. MEGGA a un seul projet Composio (sa clé, COMPOSIO_API_KEY) ; chaque client y est un utilisateur, sous son
identifiant (Config.id). On l'appelle ici en HTTP, sans son SDK, qui tirerait OpenAI et d'autres dépendances.

  - MEGGA choisit les outils d'un client un par un (Config.composio.outils, par leur slug : GMAIL_SEND_EMAIL) ;
    aucun autre outil de Composio n'est donné à l'agent ;
  - le client connecte ses comptes par un lien de Composio, que MEGGA crée dans l'atelier
    (POST /clients/{id}/composio/lien) ;
  - l'agent les reçoit par le groupe d'outils « connecteurs » (Config.outils, ou Role.outils).

Un outil de Composio agit dans un compte réel : sans approbations (lot 9.1), MEGGA ne donne que ceux qu'on peut
laisser faire à l'agent sans relecture.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator

log = logging.getLogger("megga.composio")

API = "https://backend.composio.dev/api/v3.1"
SLUG = re.compile(r"^[A-Z][A-Z0-9_]{2,99}$")
AUTH_CONFIG = re.compile(r"^ac_[A-Za-z0-9_-]{4,60}$")
DELAI = 30.0  # secondes, pour un outil comme pour la liste
RESULTAT_MAX = 20000  # caractères rendus au modèle ; au-delà, tronqué
# Ce que l'agent lit quand il a des connecteurs : ils agissent dans les vrais comptes de l'entreprise.
CONSIGNES = (
    "Some of your tools act in the company's real accounts (email, calendar, CRM, documents). Use a tool that sends, "
    "creates, changes or deletes something only when the person has clearly asked for it, and say an action is done "
    "only when the tool has confirmed it. If a tool fails, say so plainly."
)


class ReglageComposio(BaseModel):
    """Les outils de Composio d'un client, choisis un par un par MEGGA (noyau/config.py, Config.composio)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    outils: tuple[str, ...] = Field(min_length=1, max_length=40)

    @field_validator("outils")
    @classmethod
    def slugs(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        if faux := [s for s in v if not SLUG.fullmatch(s)]:
            raise ValueError(f"des noms d'outils Composio en majuscules (GMAIL_SEND_EMAIL) : {', '.join(faux)}")
        if len(set(v)) != len(v):
            raise ValueError("un outil Composio en double")
        return v


class ComposioErreur(Exception):
    def __init__(self, statut: int | None, texte: str):
        super().__init__(f"Composio {statut} : {texte[:200]}")
        self.statut, self.texte = statut, texte


def _entetes(cle: str) -> dict[str, str]:
    return {"x-api-key": cle, "content-type": "application/json"}


def _reponse(r: httpx.Response) -> dict:
    if r.status_code >= 400:
        raise ComposioErreur(r.status_code, r.text)
    try:
        return r.json()
    except ValueError as e:
        raise ComposioErreur(r.status_code, "réponse illisible") from e


def _resultat(corps: dict) -> str:
    """Ce que le modèle lit d'un outil exécuté : les données, ou l'erreur dite en clair."""
    if not corps.get("successful"):
        return f"Échec de l'outil : {corps.get('error') or 'erreur inconnue'}. Rien n'a été fait, ne dis pas le contraire."
    texte = json.dumps(corps.get("data") or {}, ensure_ascii=False)
    return texte if len(texte) <= RESULTAT_MAX else texte[:RESULTAT_MAX] + " [tronqué]"


class Composio:
    """Les outils de Composio d'un client, pour Agno. `transport` : un faux réseau (essais)."""

    def __init__(self, cle: str, utilisateur: str, reglage: ReglageComposio, transport: Any = None):
        self.cle, self.utilisateur, self.reglage, self.transport = cle, utilisateur, reglage, transport
        self._schemas: list[dict] | None = None

    def schemas(self) -> list[dict]:
        """Les outils choisis, tels que Composio les décrit (une fois par processus ; refait après un échec)."""
        if self._schemas is None:
            with httpx.Client(transport=self.transport, timeout=DELAI) as c:
                corps = _reponse(c.get(f"{API}/tools", headers=_entetes(self.cle),
                                       params={"tool_slugs": ",".join(self.reglage.outils), "limit": len(self.reglage.outils)}))
            trouves = {o["slug"]: o for o in corps.get("items") or [] if o.get("slug") in self.reglage.outils}
            if manquants := [s for s in self.reglage.outils if s not in trouves]:
                log.warning("outils Composio introuvables : %s", ", ".join(manquants))
            self._schemas = [trouves[s] for s in self.reglage.outils if s in trouves]
        return self._schemas

    async def executer(self, slug: str, version: str | None, arguments: dict) -> str:
        corps = {"user_id": self.utilisateur, "arguments": arguments}
        if version:
            corps["version"] = version
        try:
            async with httpx.AsyncClient(transport=self.transport, timeout=DELAI) as c:
                lu = _reponse(await c.post(f"{API}/tools/execute/{slug}", headers=_entetes(self.cle), json=corps))
        except (ComposioErreur, httpx.HTTPError) as e:
            log.warning("outil Composio %s en échec : %s", slug, e)
            return "Échec de l'outil : le service est injoignable. Rien n'a été fait, ne dis pas le contraire."
        return _resultat(lu)

    def outils(self) -> list:
        """Les outils pour Agno, un par outil choisi ; aucun si Composio ne répond pas (l'agent sert sans eux)."""
        from agno.tools.function import Function

        try:
            schemas = self.schemas()
        except (ComposioErreur, httpx.HTTPError) as e:
            log.warning("outils Composio indisponibles : %s", e)
            return []
        return [Function(name=s["slug"].lower(), description=(s.get("description") or s.get("name") or s["slug"])[:1000],
                         parameters=s.get("input_parameters") or {"type": "object", "properties": {}},
                         entrypoint=self._appel(s["slug"], s.get("version")), skip_entrypoint_processing=True)
                for s in schemas]

    def _appel(self, slug: str, version: str | None):
        async def appel(**arguments) -> str:
            return await self.executer(slug, version, arguments)

        appel.__name__ = slug.lower()
        return appel


async def lien(cle: str, utilisateur: str, auth_config: str, retour: str | None = None, transport: Any = None) -> dict:
    """Un lien de Composio par lequel le client connecte un de ses comptes (une configuration d'authentification
    du projet de MEGGA, `ac_...`). Rend l'adresse à ouvrir et sa date d'expiration."""
    corps = {"auth_config_id": auth_config, "user_id": utilisateur}
    if retour:
        corps["callback_url"] = retour
    async with httpx.AsyncClient(transport=transport, timeout=DELAI) as c:
        lu = _reponse(await c.post(f"{API}/connected_accounts/link", headers=_entetes(cle), json=corps))
    return {"lien": lu["redirect_url"], "expire": lu.get("expires_at"), "compte": lu.get("connected_account_id")}


async def comptes(cle: str, utilisateur: str, transport: Any = None) -> list[dict]:
    """Les comptes que le client a connectés : leur boîte d'outils et leur état, sans aucun jeton."""
    async with httpx.AsyncClient(transport=transport, timeout=DELAI) as c:
        lu = _reponse(await c.get(f"{API}/connected_accounts", headers=_entetes(cle), params={"user_ids": utilisateur}))
    return [{"id": a.get("id"), "boite": (a.get("toolkit") or {}).get("slug"), "etat": a.get("status"),
             "cree": a.get("created_at")} for a in lu.get("items") or []]
