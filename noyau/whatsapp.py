"""WhatsApp par l'API Cloud de Meta : signature, lecture des messages reçus, envoi.

Repris d'Alix (meta.js) : texte, vocaux (reçus et envoyés), modèles approuvés,
réactions, accusé de lecture ; photos, vidéos et documents reçus (leur identifiant chez Meta) ;
images, documents, vidéos, listes, boutons, carrousels et formulaires (WhatsApp Flows) envoyés.
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
class Media:
    """Une photo, une vidéo ou un document reçu : son identifiant chez Meta, pour le télécharger plus tard."""

    id: str
    genre: str  # image, video, document
    type: str = ""  # le type MIME
    nom: str = ""
    compressee: bool = False  # une vidéo envoyée comme vidéo ; comme document, elle garde sa qualité


@dataclass(frozen=True)
class Entrant:
    id: str
    de: str
    texte: str
    envoye: float  # secondes depuis 1970
    genre: str
    vocal: str = ""  # l'identifiant chez Meta d'un message vocal
    media: Media | None = None
    choix: str = ""  # l'identifiant d'une ligne de liste ou d'un bouton choisi
    formulaire: str = ""  # un formulaire rempli (WhatsApp Flow), ses champs en JSON
    profil: str = ""  # le nom que la personne s'est donné sur WhatsApp

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
            profils = {chiffres(x.get("wa_id")): " ".join(str((x.get("profile") or {}).get("name") or "").split())[:80]
                       for x in v.get("contacts") or [] if isinstance(x, dict)}
            for m in v.get("messages") or []:
                lu = _lire(m, profils.get(chiffres((m or {}).get("from")), "") if isinstance(m, dict) else "")
                if lu:
                    sortie.append(lu)
    return sortie


def _lire(m: dict, profil: str = "") -> Entrant | None:
    if not isinstance(m, dict) or not m.get("from") or m.get("type") in IGNORES:
        return None
    genre = m.get("type")
    interactif = m.get("interactive") or {}
    candidats = [
        (m.get("text") or {}).get("body"),
        (m.get("button") or {}).get("text"),
        (interactif.get("button_reply") or {}).get("title"),
        (interactif.get("list_reply") or {}).get("title"),
        (m.get("image") or {}).get("caption"),
        (m.get("video") or {}).get("caption"),
        (m.get("document") or {}).get("caption"),
    ]
    texte = next((t for t in candidats if isinstance(t, str) and t.strip()), "")
    x = m.get(genre) if genre in ("image", "video", "document") else None
    media = None
    if isinstance(x, dict) and x.get("id"):
        type_ = str(x.get("mime_type") or "")[:80]
        # Une vidéo envoyée comme document garde sa qualité d'origine.
        video = genre == "video" or (genre == "document" and type_.startswith("video/"))
        media = Media(id=str(x["id"])[:80], genre="video" if video else genre, type=type_, nom=str(x.get("filename") or "")[:120],
                      compressee=genre == "video")
    choix = (interactif.get("list_reply") or {}).get("id") or (interactif.get("button_reply") or {}).get("id") \
        or (m.get("button") or {}).get("payload") or ""
    formulaire = (interactif.get("nfm_reply") or {}).get("response_json") if interactif.get("type") == "nfm_reply" else ""
    return Entrant(
        id=str(m.get("id") or ""),
        de=f"+{chiffres(m.get('from'))}",
        texte=texte.strip()[:4000],
        envoye=float(m.get("timestamp") or 0),
        genre=str(genre or ""),
        vocal=str((m.get("audio") or {}).get("id") or "") if genre == "audio" else "",
        media=media,
        choix=str(choix)[:200],
        formulaire=str(formulaire or "")[:8000],
        profil=profil,
    )


def decrire_media(media: Media, n: int) -> str:
    """Le média tel que l'agent le lit dans le message : son genre et son numéro, que ses outils comprennent."""
    nom = f", « {media.nom} »" if media.nom else ""
    if media.genre == "video":
        qualite = ", compressée par WhatsApp" if media.compressee else ", qualité d'origine"
        return f"[Vidéo reçue : média {n}{qualite}{nom}]"
    if media.genre == "image":
        return f"[Photo reçue : média {n}]"
    genre = "PDF" if "pdf" in (media.type + media.nom).lower() else "Document"
    return f"[{genre} reçu : média {n}{nom}]"


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

    async def texte(self, vers: str, texte: str, apercu: bool = False) -> dict:
        """`apercu` : WhatsApp montre l'aperçu du lien (la carte d'une annonce)."""
        return await self._envoyer({
            "recipient_type": "individual",
            "to": chiffres(vers),
            "type": "text",
            "text": {"preview_url": bool(apercu), "body": str(texte)[:LIMITE_TEXTE]},
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

    async def televerser(self, octets: bytes, type_: str, nom: str) -> str:
        """Dépose un fichier chez Meta ; rend son identifiant, à envoyer ensuite."""
        r = await self._client.post(
            f"{self._graph}/{self._numero}/media",
            headers=self._auth,
            data={"messaging_product": "whatsapp", "type": type_},
            files={"file": (nom, octets, type_)},
        )
        if r.status_code >= 400:
            raise RuntimeError(f"Meta dépôt {r.status_code} {r.text[:200]}")
        return r.json()["id"]

    async def _media(self, vers: str, genre: str, media_id: str = "", lien: str = "", legende: str = "", nom: str = "") -> dict:
        if bool(media_id) == bool(lien):
            raise ValueError("un média : son identifiant chez Meta, ou un lien, pas les deux")
        corps = {"id": media_id} if media_id else {"link": lien}
        if legende:
            corps["caption"] = str(legende)[:1024]
        if nom:
            corps["filename"] = str(nom)[:240]
        return await self._envoyer({"recipient_type": "individual", "to": chiffres(vers), "type": genre, genre: corps})

    async def image(self, vers: str, media_id: str = "", lien: str = "", legende: str = "") -> dict:
        return await self._media(vers, "image", media_id, lien, legende)

    async def document(self, vers: str, nom: str, media_id: str = "", lien: str = "", legende: str = "") -> dict:
        return await self._media(vers, "document", media_id, lien, legende, nom)

    async def video(self, vers: str, media_id: str = "", lien: str = "", legende: str = "") -> dict:
        return await self._media(vers, "video", media_id, lien, legende)

    async def liste(self, vers: str, corps: str, bouton: str, section: str, lignes: list[dict]) -> dict:
        """Une liste à choix (« bouton » l'ouvre), dix lignes au plus : [{id, titre, description?}]."""
        return await self._envoyer({
            "recipient_type": "individual", "to": chiffres(vers), "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {"text": str(corps)[:1024]},
                "action": {"button": str(bouton)[:20], "sections": [{"title": str(section)[:24], "rows": [
                    {"id": str(l["id"])[:200], "title": str(l["titre"])[:24], **({"description": str(l["description"])[:72]} if l.get("description") else {})}
                    for l in lignes[:10]]}]},
            },
        })

    async def boutons(self, vers: str, corps: str, boutons: list[dict]) -> dict:
        """Jusqu'à trois boutons de réponse : [{id, titre}]."""
        return await self._envoyer({
            "recipient_type": "individual", "to": chiffres(vers), "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": str(corps)[:1024]},
                "action": {"buttons": [{"type": "reply", "reply": {"id": str(b["id"])[:256], "title": str(b["titre"])[:20]}} for b in boutons[:3]]},
            },
        })

    async def carrousel(self, vers: str, corps: str, cartes: list[dict]) -> dict:
        """De 2 à 10 cartes : [{image (lien), texte (160), bouton (20), url}]."""
        return await self._envoyer({
            "recipient_type": "individual", "to": chiffres(vers), "type": "interactive",
            "interactive": {
                "type": "carousel",
                "body": {"text": str(corps)[:1024]},
                "action": {"cards": [{
                    "card_index": i, "type": "cta_url",
                    "header": {"type": "image", "image": {"link": c["image"]}},
                    "body": {"text": str(c["texte"])[:160]},
                    "action": {"name": "cta_url", "parameters": {"display_text": str(c["bouton"])[:20], "url": c["url"]}},
                } for i, c in enumerate(cartes[:10])]},
            },
        })

    async def formulaire(self, vers: str, flow_id: str, corps: str, bouton: str, jeton: str, ecran: str) -> dict:
        """Un formulaire publié (WhatsApp Flow), qu'un bouton ouvre."""
        return await self._envoyer({
            "recipient_type": "individual", "to": chiffres(vers), "type": "interactive",
            "interactive": {
                "type": "flow",
                "body": {"text": str(corps)[:1024]},
                "action": {"name": "flow", "parameters": {
                    "flow_message_version": "3", "flow_id": str(flow_id), "flow_cta": str(bouton)[:30], "flow_token": jeton,
                    "flow_action": "navigate", "flow_action_payload": {"screen": ecran}}},
            },
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


class SansWhatsApp:
    """L'expéditeur d'un agent branché seulement par API : rien ne part sur WhatsApp."""

    @staticmethod
    def _refus():
        raise RuntimeError("cet agent n'a pas de numéro WhatsApp")

    async def texte(self, vers: str, texte: str, apercu: bool = False) -> dict:
        self._refus()

    async def modele(self, vers: str, nom: str, langue: str, variables: list[str]) -> dict:
        self._refus()

    async def reaction(self, vers: str, message_id: str, emoji: str) -> dict:
        self._refus()

    async def lu(self, message_id: str) -> dict:
        self._refus()

    async def vocal(self, vers: str, audio: bytes, ogg: bool) -> dict:
        self._refus()

    async def telecharger(self, media_id: str, maximum: int = MEDIA_MAX) -> bytes:
        self._refus()

    async def televerser(self, octets: bytes, type_: str, nom: str) -> str:
        self._refus()

    async def image(self, vers: str, media_id: str = "", lien: str = "", legende: str = "") -> dict:
        self._refus()

    async def document(self, vers: str, nom: str, media_id: str = "", lien: str = "", legende: str = "") -> dict:
        self._refus()

    async def video(self, vers: str, media_id: str = "", lien: str = "", legende: str = "") -> dict:
        self._refus()

    async def liste(self, vers: str, corps: str, bouton: str, section: str, lignes: list[dict]) -> dict:
        self._refus()

    async def boutons(self, vers: str, corps: str, boutons: list[dict]) -> dict:
        self._refus()

    async def carrousel(self, vers: str, corps: str, cartes: list[dict]) -> dict:
        self._refus()

    async def formulaire(self, vers: str, flow_id: str, corps: str, bouton: str, jeton: str, ecran: str) -> dict:
        self._refus()
