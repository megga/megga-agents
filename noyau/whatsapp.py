"""WhatsApp par l'API Cloud de Meta : signature, lecture des messages reçus, envoi.

Repris d'Alix (meta.js) : texte, vocaux (reçus et envoyés), modèles approuvés,
réactions, accusé de lecture. Les autres médias viendront avec les packs.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import time
from dataclasses import dataclass

import httpx

# Après un blocage levé, Meta remet d'un coup les messages reçus entre-temps :
# un message plus vieux que ce délai n'appelle pas de réponse automatique.
FRAICHEUR_S = 15 * 60
IGNORES = {"system", "request_welcome", "reaction"}
LIMITE_TEXTE = 4096
# Au-delà de 24 heures après le dernier message de la personne, Meta n'accepte
# plus qu'un modèle approuvé.
FENETRE_S = 24 * 3600
MEDIA_MAX = 16_000_000


def chiffres(n) -> str:
    return re.sub(r"\D", "", str(n or ""))


def signature_valide(corps: bytes, entete: str | None, secret: str | None) -> bool:
    """Meta signe le corps brut en HMAC-SHA256 : « X-Hub-Signature-256: sha256=<hex> »."""
    algo, _, h = str(entete or "").partition("=")
    if algo != "sha256" or not re.fullmatch(r"[0-9a-fA-F]{64}", h) or not secret:
        return False
    attendu = hmac.new(secret.encode(), corps, hashlib.sha256).hexdigest()
    return hmac.compare_digest(attendu, h.lower())


@dataclass(frozen=True)
class Entrant:
    id: str
    de: str
    texte: str
    envoye: float  # secondes depuis 1970
    genre: str
    vocal: str = ""  # l'identifiant chez Meta d'un message vocal

    def frais(self, maintenant: float | None = None) -> bool:
        return not self.envoye or (maintenant or time.time()) - self.envoye <= FRAICHEUR_S


def lire_entrants(evenement: dict, numero_id: str) -> list[Entrant]:
    """Les messages reçus au numéro du client, et seulement à lui."""
    sortie: list[Entrant] = []
    if not isinstance(evenement, dict) or evenement.get("object") != "whatsapp_business_account":
        return sortie
    for e in evenement.get("entry") or []:
        for c in e.get("changes") or []:
            v = c.get("value") or {}
            if c.get("field") != "messages" or (v.get("metadata") or {}).get("phone_number_id") != numero_id:
                continue
            for m in v.get("messages") or []:
                lu = _lire(m)
                if lu:
                    sortie.append(lu)
    return sortie


def _lire(m: dict) -> Entrant | None:
    if not isinstance(m, dict) or not m.get("from") or m.get("type") in IGNORES:
        return None
    candidats = [
        (m.get("text") or {}).get("body"),
        (m.get("button") or {}).get("text"),
        ((m.get("interactive") or {}).get("button_reply") or {}).get("title"),
        ((m.get("interactive") or {}).get("list_reply") or {}).get("title"),
        (m.get("image") or {}).get("caption"),
        (m.get("document") or {}).get("caption"),
    ]
    texte = next((t for t in candidats if isinstance(t, str) and t.strip()), "")
    return Entrant(
        id=str(m.get("id") or ""),
        de=f"+{chiffres(m.get('from'))}",
        texte=texte.strip()[:4000],
        envoye=float(m.get("timestamp") or 0),
        genre=str(m.get("type") or ""),
        vocal=str((m.get("audio") or {}).get("id") or "") if m.get("type") == "audio" else "",
    )


def fenetre_ouverte(dernier_entrant: float | None, maintenant: float | None = None) -> bool:
    """Un message libre est-il permis ? Seulement dans les 24 heures du dernier message reçu."""
    return bool(dernier_entrant) and (maintenant or time.time()) - dernier_entrant < FENETRE_S


class Expediteur:
    """Envoie au nom du numéro du client, avec le jeton de l'app Meta."""

    def __init__(self, jeton: str, numero_id: str, version_graph: str, client: httpx.AsyncClient | None = None):
        self._auth = {"authorization": f"Bearer {jeton}"}
        self._graph = f"https://graph.facebook.com/{version_graph}"
        self._numero = numero_id
        self._client = client or httpx.AsyncClient(timeout=30)

    async def _envoyer(self, message: dict) -> dict:
        r = await self._client.post(
            f"{self._graph}/{self._numero}/messages",
            headers=self._auth,
            json={"messaging_product": "whatsapp", **message},
        )
        if r.status_code >= 400:
            raise RuntimeError(f"Meta {r.status_code} {r.text[:300]}")
        return r.json() if r.content else {}

    async def texte(self, vers: str, texte: str) -> dict:
        return await self._envoyer({
            "recipient_type": "individual",
            "to": chiffres(vers),
            "type": "text",
            "text": {"preview_url": False, "body": str(texte)[:LIMITE_TEXTE]},
        })

    async def modele(self, vers: str, nom: str, langue: str, variables: list[str]) -> dict:
        """Un modèle approuvé par Meta, seul permis hors des 24 heures."""
        return await self._envoyer({
            "recipient_type": "individual",
            "to": chiffres(vers),
            "type": "template",
            "template": {
                "name": nom,
                "language": {"code": langue},
                "components": [{"type": "body", "parameters": [{"type": "text", "text": str(v)} for v in variables]}],
            },
        })

    async def reaction(self, vers: str, message_id: str, emoji: str) -> dict:
        """Une réaction sur un message reçu ; un émoji vide la retire."""
        return await self._envoyer({
            "recipient_type": "individual",
            "to": chiffres(vers),
            "type": "reaction",
            "reaction": {"message_id": message_id, "emoji": emoji},
        })

    async def lu(self, message_id: str) -> dict:
        """Les coches bleues, et « en train d'écrire » jusqu'à la réponse (25 s au plus)."""
        return await self._envoyer({"status": "read", "message_id": message_id, "typing_indicator": {"type": "text"}})

    async def vocal(self, vers: str, audio: bytes, ogg: bool) -> dict:
        """Dépose le fichier chez Meta, puis l'envoie : en vocal s'il est en Ogg/Opus."""
        genre = "audio/ogg" if ogg else "audio/mpeg"
        r = await self._client.post(
            f"{self._graph}/{self._numero}/media",
            headers=self._auth,
            data={"messaging_product": "whatsapp", "type": genre},
            files={"file": ("reponse.ogg" if ogg else "reponse.mp3", audio, genre)},
        )
        if r.status_code >= 400:
            raise RuntimeError(f"Meta dépôt {r.status_code} {r.text[:200]}")
        media = r.json()["id"]
        return await self._envoyer({
            "recipient_type": "individual",
            "to": chiffres(vers),
            "type": "audio",
            "audio": {"id": media, "voice": True} if ogg else {"id": media},
        })

    async def telecharger(self, media_id: str, maximum: int = MEDIA_MAX) -> bytes:
        """Un média reçu : Meta donne d'abord une adresse temporaire, qui demande aussi le jeton."""
        r = await self._client.get(f"{self._graph}/{media_id}", headers=self._auth)
        if r.status_code >= 400:
            raise RuntimeError(f"Meta média {r.status_code}")
        info = r.json()
        if not info.get("url") or int(info.get("file_size") or 0) > maximum:
            raise RuntimeError("média absent ou trop lourd")
        f = await self._client.get(info["url"], headers=self._auth)
        if f.status_code >= 400:
            raise RuntimeError(f"Meta fichier {f.status_code}")
        return f.content[:maximum]
