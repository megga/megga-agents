"""La voix de l'agent, chez ElevenLabs : transcrire un vocal reçu, dire une réponse.

Repris d'Alix (voix.js, vocal.js), sans ce qui était propre à un client.
  ELEVENLABS_API_KEY  la clé de MEGGA (ou celle du client)
Le fichier rendu en Ogg/Opus part comme un vocal WhatsApp.
"""

from __future__ import annotations

import re

import httpx

from .config import Voix

FORMAT = "opus_48000_64"
MAX_DIT = 1200  # au-delà, une réponse se lit mieux qu'elle ne s'écoute

_LIEN = re.compile(r"https?://\S+|www\.\S+|\b[a-z0-9-]+\.(?:ch|com|fr|es|ae|net|org)/\S*", re.I)
_COURRIEL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
# Un téléphone commence par + ou 0 : un prix (« 4 200 000 CHF ») se dit.
_NUMERO = re.compile(r"(?:\+|\b0)\d[\d .-]{7,}\d")
_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿️]")
_FR = re.compile(r"[àâçéèêëîïôûùüÿœ]|\b(le|la|les|des|du|est|vous|je|nous|une|pour|avec|dans|sur|pas|bonjour|merci|c'est|j'ai)\b", re.I)
_EN = re.compile(r"\b(the|and|you|your|is|are|for|with|this|that|hello|thanks|it's|i'm|have|will)\b", re.I)


def a_ecrire(texte: str) -> bool:
    """Ce qui doit aussi partir par écrit après un vocal : ce qui se copie ou se clique."""
    t = str(texte or "")
    return any(r.search(t) for r in (_LIEN, _COURRIEL, _NUMERO))


def a_dire(texte: str) -> str:
    """Le texte prononcé : sans liens, sans mise en forme, sans émojis."""
    t = _LIEN.sub("", str(texte or ""))
    t = re.sub(r"[*_~`#>]", "", t)
    t = _EMOJI.sub("", t)
    t = re.sub(r"[ \t]+", " ", t)
    return re.sub(r"\s*\n\s*", "\n", t).strip()


def d_un_tenant(texte: str) -> str:
    """D'un seul souffle : un retour à la ligne ou des points de suspension font hacher la voix."""
    t = re.sub(r"\s*(?:\.{3}|\u2026)\s*$", ".", str(texte or ""))
    t = re.sub(r"\s*(?:\.{3}|\u2026)\s*", " ", t)
    t = re.sub(r"\s+[-\u2013\u2014]\s+", ", ", t)
    t = re.sub(r"\s*\n+\s*", " ", t)
    t = re.sub(r",\s*([.!?])", r"\1", t)
    t = re.sub(r",\s*,", ",", t)
    return re.sub(r"[ \t]{2,}", " ", t).strip()


def se_prete(texte: str) -> bool:
    dit = a_dire(texte)
    return bool(dit) and len(dit) <= MAX_DIT


def langue(texte: str) -> str:
    t = str(texte or "")
    return "en" if len(_EN.findall(t)) > len(_FR.findall(t)) else "fr"


def voix_pour(reglages: Voix, texte: str) -> str | None:
    """La voix de la langue de la réponse ; sinon la voix par défaut ; sinon aucune."""
    return reglages.par_langue.get(langue(texte)) or reglages.voix


class Voie:
    """ElevenLabs : la transcription et la synthèse, avec la même clé."""

    def __init__(self, cle: str, reglages: Voix, client: httpx.AsyncClient | None = None):
        self._cle = cle
        self.reglages = reglages
        self._client = client or httpx.AsyncClient(timeout=60)

    @property
    def parle(self) -> bool:
        return bool(self._cle and (self.reglages.voix or self.reglages.par_langue))

    @property
    def ecoute(self) -> bool:
        return bool(self._cle)

    async def transcrire(self, audio: bytes, type_audio: str = "audio/ogg") -> str:
        r = await self._client.post(
            f"{self.reglages.serveur}/v1/speech-to-text",
            headers={"xi-api-key": self._cle},
            data={"model_id": self.reglages.transcription},
            files={"file": ("vocal.ogg", audio, type_audio)},
        )
        if r.status_code >= 400:
            raise RuntimeError(f"ElevenLabs transcription {r.status_code} {r.text[:200]}")
        return re.sub(r"\s+", " ", str(r.json().get("text") or "")).strip()[:4000]

    async def dire(self, texte: str) -> tuple[bytes, bool]:
        """Rend (audio, ogg) ; ogg : un vocal WhatsApp, sinon un audio ordinaire."""
        voix = voix_pour(self.reglages, texte)
        if not voix:
            raise RuntimeError("aucune voix réglée")
        r = await self._client.post(
            f"{self.reglages.serveur}/v1/text-to-speech/{voix}",
            params={"output_format": FORMAT},
            headers={"xi-api-key": self._cle},
            json={
                "text": d_un_tenant(a_dire(texte)),
                "model_id": self.reglages.modele,
                "voice_settings": {"stability": self.reglages.stabilite, "similarity_boost": 0.75, "speed": self.reglages.vitesse},
            },
        )
        if r.status_code >= 400:
            raise RuntimeError(f"ElevenLabs voix {r.status_code} {r.text[:200]}")
        audio = r.content
        if len(audio) < 100:
            raise RuntimeError("audio vide")
        return audio, audio[:4] == b"OggS"
