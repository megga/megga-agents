"""L'envoi des alertes (20.11.2026) : les destinations, l'envoi, et l'évaluation de toutes les règles.

Trois genres de destination :
  courriel   une adresse ; le message part par la porte (POST /admin/courriel, Cloudflare Email Service)
  slack      l'adresse d'un webhook entrant de Slack (https://hooks.slack.com/services/…)
  web        une adresse https ; le corps est signé (x-megga-signature : sha256 du HMAC de « horodatage.corps »)
L'adresse d'un webhook est un secret : elle n'est plus jamais rendue en entier, la clé de signature est montrée une fois.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import ipaddress
import json
import re
import secrets
import socket
import time
from typing import Literal
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .alertes import ID, Etats, Regle, decider, gravite, message, mesurer

DESTINATIONS_MAX = 10
ESSAIS_ENVOI = 3  # un envoi en échec est repris aux évaluations suivantes, trois fois au plus
COURRIEL = re.compile(r"^[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9-]{1,63}(\.[A-Za-z0-9-]{1,63})+$")
SLACK = re.compile(r"^https://hooks\.slack\.com/services/[A-Za-z0-9/_-]{10,200}$")


def adresse_web_permise(url: str) -> bool:
    """Une adresse https sur un nom d'hôte public : ni adresse IP, ni nom local, ni port à part."""
    try:
        u = urlsplit(url)
    except ValueError:
        return False
    hote = (u.hostname or "").lower()
    if u.scheme != "https" or not hote or u.port not in (None, 443) or u.username or u.password or len(url) > 500:
        return False
    try:
        ipaddress.ip_address(hote)
        return False
    except ValueError:
        pass
    return "." in hote and not hote.endswith((".local", ".internal", ".localhost")) and hote != "localhost"


async def hote_public(hote: str) -> bool:
    """Le nom résout-il seulement vers des adresses publiques ? Un nom qui pointe vers le réseau interne est refusé."""
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(hote, 443, type=socket.SOCK_STREAM)
    except OSError:
        return False
    return bool(infos) and all(ipaddress.ip_address(i[4][0]).is_global for i in infos)


class Destination(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=ID)
    genre: Literal["courriel", "slack", "web"]
    adresse: str = Field(min_length=3, max_length=500)
    secret: str | None = None  # web : la clé de signature, tirée par l'atelier

    @model_validator(mode="after")
    def _adresse(self):
        ok = {"courriel": COURRIEL.fullmatch, "slack": SLACK.fullmatch, "web": adresse_web_permise}[self.genre](self.adresse)
        if not ok:
            raise ValueError({"courriel": "adresse de courriel invalide",
                              "slack": "adresse attendue : https://hooks.slack.com/services/…",
                              "web": "adresse https sur un nom d'hôte public attendue"}[self.genre])
        return self


def montrer(d: Destination) -> dict:
    """Une destination telle qu'elle se lit : l'adresse d'un webhook est masquée, la clé jamais rendue."""
    adresse = d.adresse if d.genre == "courriel" else f"https://{urlsplit(d.adresse).hostname}/…{d.adresse[-4:]}"
    return {"id": d.id, "genre": d.genre, "adresse": adresse}


def nouvelle_destination(brut: dict, existantes: list[Destination]) -> Destination:
    if len(existantes) >= DESTINATIONS_MAX:
        raise ValueError(f"{DESTINATIONS_MAX} destinations au plus")
    d = Destination.model_validate({**brut, "secret": None})
    if any(e.id == d.id for e in existantes):
        raise ValueError("une destination porte déjà cet identifiant")
    return d.model_copy(update={"secret": secrets.token_urlsafe(32)}) if d.genre == "web" else d


def signature(secret: str, horodatage: str, corps: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), horodatage.encode() + b"." + corps, hashlib.sha256).hexdigest()


async def envoyer(d: Destination, m: dict, porte, transport: httpx.AsyncBaseTransport | None = None) -> str | None:
    """Envoie un message ; rend None s'il est parti, sinon la raison, en quelques mots."""
    try:
        if d.genre == "courriel":
            if porte is None:
                return "porte non réglée"
            await porte.courriel(d.adresse, m["sujet"], m["texte"])
            return None
        if d.genre == "slack":
            # Les trois caractères de commande de Slack : un nom ne peut ni mentionner ni lier.
            texte = m["texte"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            corps = json.dumps({"text": texte}, ensure_ascii=False).encode()
            entetes = {"content-type": "application/json"}
        else:
            if not await hote_public(urlsplit(d.adresse).hostname or ""):
                return "adresse privée refusée"
            corps = json.dumps(m["donnees"], ensure_ascii=False).encode()
            horodatage = str(int(time.time()))
            entetes = {"content-type": "application/json", "x-megga-horodatage": horodatage,
                       "x-megga-signature": signature(d.secret or "", horodatage, corps)}
        async with httpx.AsyncClient(transport=transport, timeout=10, follow_redirects=False) as c:
            r = await c.post(d.adresse, content=corps, headers=entetes)
        return None if 200 <= r.status_code < 300 else f"réponse {r.status_code}"
    except Exception as e:  # noqa: BLE001 : une destination en panne n'arrête pas les autres
        return f"échec ({getattr(e, 'statut', None) or type(e).__name__})"


async def evaluer(regles: list[Regle], destinations: list[Destination], rassemble: dict, etats: Etats, porte,
                  bd, maintenant: float, transport: httpx.AsyncBaseTransport | None = None) -> dict:
    """Évalue chaque règle sur chaque client actif, range les états, envoie ce qui doit partir.

    `bd` : l'appel à la base hors de la boucle (atelier/app.py)."""
    par_id = {d.id: d for d in destinations}
    avant = await bd(etats.tous)
    await bd(etats.oublier, {r.id for r in regles})
    devise = rassemble.get("devise") or ""
    envois, evaluees, vus = [], 0, set()
    for client in rassemble.get("clients") or []:
        if not client.get("actif"):
            continue
        for r in regles:
            if r.clients and client["id"] not in r.clients:
                continue
            evaluees += 1
            vus.add((r.id, client["id"]))
            ancien = avant.get((r.id, client["id"]))
            valeur = mesurer(client, r.mesure, r.fenetre_jours, maintenant)
            etat, genre = decider(r, ancien, gravite(r, valeur), maintenant)
            nouvel = {"etat": etat, "valeur": valeur,
                      "depuis": ancien["depuis"] if ancien and ancien["etat"] == etat else maintenant,
                      "envoye_le": (ancien or {}).get("envoye_le") if ancien and ancien["etat"] == etat else None,
                      "en_attente": None}
            cibles = r.destinations
            attente = (ancien or {}).get("en_attente")
            if genre is None and attente and attente.get("etat") == etat and attente.get("essais", 0) < ESSAIS_ENVOI:
                genre, cibles = attente["genre"], attente["destinations"]  # reprise d'un envoi en échec
            if genre and cibles and not r.en_pause:
                m = message(r, genre, etat, client, valeur, devise)
                echecs = {}
                for ident in cibles:
                    d = par_id.get(ident)
                    raison = "destination inconnue" if d is None else await envoyer(d, m, porte, transport)
                    if raison:
                        echecs[ident] = raison
                parties = [i for i in cibles if i not in echecs]
                if parties:
                    nouvel["envoye_le"] = maintenant
                if echecs:
                    essais = (attente or {}).get("essais", 0) + 1 if attente and attente.get("etat") == etat else 1
                    nouvel["en_attente"] = {"genre": genre, "etat": etat, "destinations": sorted(echecs), "essais": essais}
                envois.append({"regle": r.id, "client": client["id"], "etat": etat, "envoi": genre,
                               "parties": parties, "echecs": echecs})
            await bd(etats.ecrire, r.id, client["id"], nouvel, ancien is not None)
    partis = [k for k in avant if k not in vus and k[0] in {r.id for r in regles}]
    if partis:
        await bd(etats.retirer, partis)
    return {"evaluees": evaluees, "envois": envois}
