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
_ES = re.compile(r"[¿¡ñ]|\b(el|los|las|una|está|estás|hola|gracias|cómo|muy|buenos|buenas|tengo|quiero|puedo|usted|también|pero|dónde|donde)\b", re.I)
# Les langues qu'ElevenLabs reçoit imposées (Voix.imposer_langue, M6).
LANGUES_IMPOSEES = ("fr", "en", "es")
# Les indications de jeu d'ElevenLabs, entre crochets : « [softly] Je comprends. »
_BALISE = re.compile(r"\[([^\]\n]{1,40})\]\s*")
BALISES_MAX = 1


def a_ecrire(texte: str, references: str | None = None) -> bool:
    """Ce qui doit aussi partir par écrit après un vocal : ce qui se copie ou se clique, et une référence (Oral.references)."""
    t = str(texte or "")
    return any(r.search(t) for r in (_LIEN, _COURRIEL, _NUMERO)) or bool(references and re.search(references, t))


def sans_balises(texte: str) -> str:
    return re.sub(r"[ \t]{2,}", " ", _BALISE.sub("", str(texte or ""))).strip()


def balises_permises(texte: str, permises) -> str:
    """Seulement les indications permises (Voix.balises), une au plus ; les autres crochets partent."""
    permises, n = {b.lower() for b in permises}, 0

    def garder(m):
        nonlocal n
        b = m.group(1).strip().lower()
        if b in permises and n < BALISES_MAX:
            n += 1
            return f"[{b}] "
        return ""

    return re.sub(r"[ \t]{2,}", " ", _BALISE.sub(garder, str(texte or ""))).strip()


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
    """fr, en ou es, d'après des mots et des lettres qui ne trompent pas ; fr dans le doute."""
    t = str(texte or "")
    fr, en, es = len(_FR.findall(t)), len(_EN.findall(t)), len(_ES.findall(t))
    if es > fr and es > en:
        return "es"
    return "en" if en > fr else "fr"


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
        """Rend (audio, ogg) ; ogg : un vocal WhatsApp, sinon un audio ordinaire. La langue de la réponse est imposée
        (Voix.imposer_langue) ; si le modèle la refuse (400, 422), le texte est relu sans."""
        voix = voix_pour(self.reglages, texte)
        if not voix:
            raise RuntimeError("aucune voix réglée")
        dit = balises_permises(a_dire(texte), self.reglages.balises) if self.reglages.balises else a_dire(sans_balises(texte))
        corps = {
            "text": d_un_tenant(dit),
            "model_id": self.reglages.modele,
            "voice_settings": {"stability": self.reglages.stabilite, "similarity_boost": 0.75, "speed": self.reglages.vitesse},
        }

        async def appeler(c: dict):
            return await self._client.post(f"{self.reglages.serveur}/v1/text-to-speech/{voix}", params={"output_format": FORMAT},
                                           headers={"xi-api-key": self._cle}, json=c)

        lang = langue(texte)
        if self.reglages.imposer_langue and lang in LANGUES_IMPOSEES:
            r = await appeler({**corps, "language_code": lang})
            if r.status_code in (400, 422):
                import logging

                logging.getLogger("megga").warning("voix : langue imposée refusée (%s), relue sans", r.status_code)
                r = await appeler(corps)
        else:
            r = await appeler(corps)
        if r.status_code >= 400:
            raise RuntimeError(f"ElevenLabs voix {r.status_code} {r.text[:200]}")
        audio = r.content
        if len(audio) < 100:
            raise RuntimeError("audio vide")
        return audio, audio[:4] == b"OggS"
