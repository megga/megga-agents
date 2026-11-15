"""WhatsApp par l'API Cloud de Meta : signature, lecture des messages reçus, envoi.

Repris d'Alix (meta.js). Au lot 1, le texte seulement ; vocaux, médias, modèles
et réactions viennent au lot 2.
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
    )


class Expediteur:
    """Envoie au nom du numéro du client, avec le jeton de l'app Meta."""

    def __init__(self, jeton: str, numero_id: str, version_graph: str, client: httpx.AsyncClient | None = None):
        self._jeton = jeton
        self._url = f"https://graph.facebook.com/{version_graph}/{numero_id}/messages"
        self._client = client or httpx.AsyncClient(timeout=30)

    async def texte(self, vers: str, texte: str) -> dict:
        r = await self._client.post(
            self._url,
            headers={"authorization": f"Bearer {self._jeton}"},
            json={
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": chiffres(vers),
                "type": "text",
                "text": {"preview_url": False, "body": str(texte)[:LIMITE_TEXTE]},
            },
        )
        if r.status_code >= 400:
            raise RuntimeError(f"Meta {r.status_code} {r.text[:300]}")
        return r.json() if r.content else {}
