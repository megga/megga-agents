"""Un tour de conversation sur WhatsApp, de la réception à la réponse.

- Les messages d'une même personne qui arrivent à quelques secondes d'intervalle
  sont lus ensemble (on envoie souvent plusieurs messages à la suite).
- Un vocal est transcrit ; à un vocal, l'agent répond par un vocal s'il a une voix,
  et par écrit en plus ce qui se copie ou se clique (lien, e-mail, numéro).
- Coches bleues et « en train d'écrire » dès la lecture ; un 👀 si le tour traîne,
  retiré à la réponse.
- Hors des 24 heures de WhatsApp, un message de l'agent ne part que par un modèle Meta.
- Une erreur technique n'est jamais envoyée telle quelle.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

from .config import Config
from .garde import TROP, Debit, masquer_secrets
from .oral import pour_la_voix
from .typographie import nettoyer
from .voix import a_ecrire, se_prete
from .whatsapp import Entrant, fenetre_ouverte

log = logging.getLogger("megga")

EXCUSE = "Je rencontre un petit souci technique. Je reviens vers vous dès que possible."
NON_COMPRIS = "Je n'ai pas pu écouter ce vocal. Pouvez-vous me l'écrire ?"
REGARD = "\U0001F440"


def en_echec(sortie) -> bool:
    statut = getattr(sortie, "status", None)
    return str(getattr(statut, "value", statut) or "").upper() in {"ERROR", "CANCELLED"}


@dataclass
class _Boite:
    messages: list[Entrant] = field(default_factory=list)
    tache: asyncio.Task | None = None


class Conversations:
    """Les conversations d'un client, une file par personne."""

    def __init__(self, conf: Config, agent, expediteur, voie=None, contacts=None, reecrire=None,
                 attente: float = 2.5, seuil_regard: float = 8.0, rappels=None, debit: Debit | None = None,
                 journal=None, fil=None):
        self.conf = conf
        self.agent = agent
        self.exp = expediteur
        self.voie = voie
        self.contacts = contacts
        self.reecrire = reecrire
        self.attente = attente
        self.seuil_regard = seuil_regard
        self.rappels = rappels
        self.debit = debit or Debit()
        # Le suivi, écrit en arrière-plan : il ne retarde ni ne fait échouer un tour.
        # Le journal (stockage.Journal) : échecs et volumes de voix, jamais de texte.
        # Le fil (stockage.Fil) : les messages tels que la personne les a vécus.
        self.journal = journal
        self.fil = fil
        self._boites: dict[str, _Boite] = {}
        self._verrous: dict[str, asyncio.Lock] = {}
        self.taches: set[asyncio.Task] = set()

    def _lancer(self, coro) -> asyncio.Task:
        t = asyncio.create_task(coro)
        self.taches.add(t)
        t.add_done_callback(self.taches.discard)
        return t

    def recevoir(self, m: Entrant) -> None:
        """Range le message ; le tour part après un court délai, avec ceux qui suivent."""
        b = self._boites.setdefault(m.de, _Boite())
        b.messages.append(m)
        if b.tache is None:
            b.tache = self._lancer(self._attendre(m.de))

    async def _attendre(self, personne: str) -> None:
        await asyncio.sleep(self.attente)
        b = self._boites.pop(personne)
        await self._tour(personne, b.messages)

    async def _tour(self, personne: str, messages: list[Entrant]) -> None:
        async with self._verrous.setdefault(personne, asyncio.Lock()):
            dernier = messages[-1]
            await self._sans_echec(self._noter(personne, max(m.envoye for m in messages)))
            await self._sans_echec(self.exp.lu(dernier.id))
            await self._sans_echec(self._rappels_differes(personne))
            if not self.debit.permis(personne):
                for m in messages:  # reçus, mais sans tour
                    self._noter_fil(personne, "recu", "vocal" if m.vocal else "texte", m.texte)
                if self.debit.prevenir(personne):
                    await self._ecrire(personne, TROP)
                return
            etat = {"pose": False}
            regard = self._lancer(self._regard(personne, dernier.id, etat)) if self.conf.reactions else None
            try:
                await self._repondre(personne, messages)
            finally:
                if regard:
                    regard.cancel()
                    if etat["pose"]:
                        await self._sans_echec(self.exp.reaction(personne, dernier.id, ""))

    async def _regard(self, personne: str, message_id: str, etat: dict) -> None:
        await asyncio.sleep(self.seuil_regard)
        await self._sans_echec(self.exp.reaction(personne, message_id, REGARD))
        etat["pose"] = True

    async def _repondre(self, personne: str, messages: list[Entrant]) -> None:
        parties, vocal, sourd = [], False, False
        for m in messages:
            if m.vocal:
                vocal = True
                texte = await self._ecouter(m.vocal)
                self._noter_fil(personne, "recu", "vocal", texte)
                if texte:
                    parties.append(texte)
                else:
                    sourd = True
            elif m.texte:
                self._noter_fil(personne, "recu", "texte", m.texte)
                parties.append(m.texte)
        entendu = "\n".join(parties).strip()
        if not entendu:
            await self._ecrire(personne, NON_COMPRIS if sourd else "Je ne lis que les messages écrits et les vocaux pour le moment.")
            return
        try:
            sortie = await self.agent.arun(entendu, user_id=personne, session_id=personne)
            reponse = EXCUSE if en_echec(sortie) else (getattr(sortie, "content", None) or "")
            if en_echec(sortie):
                log.error("tour en échec (%s)", self.conf.id)
                self._noter_journal("tour_echec", detail=str(getattr(sortie, "status", ""))[:60])
        except Exception as e:
            log.error("tour en échec (%s) : %s", self.conf.id, str(e)[:300])
            self._noter_journal("tour_echec", detail=type(e).__name__)
            reponse = EXCUSE
        if not reponse.strip():
            return
        if vocal and self.voie is not None and self.voie.parle and se_prete(reponse) and reponse != EXCUSE:
            if await self._dire(personne, reponse, entendu):
                if a_ecrire(reponse):
                    await self._ecrire(personne, reponse)
                return
        await self._ecrire(personne, reponse)

    async def _ecouter(self, media_id: str) -> str:
        if self.voie is None or not self.voie.ecoute:
            return ""
        try:
            texte = await self.voie.transcrire(await self.exp.telecharger(media_id))
            self._noter_journal("vocal_entendu")
            return texte
        except Exception as e:
            log.error("vocal illisible (%s) : %s", self.conf.id, str(e)[:200])
            self._noter_journal("vocal_illisible", detail=type(e).__name__)
            return ""

    async def _dire(self, personne: str, reponse: str, entendu: str) -> bool:
        try:
            dit = await pour_la_voix(self.reecrire, nettoyer(reponse), entendu) if self.reecrire else reponse
            audio, ogg = await self.voie.dire(dit)
            self._noter_journal("voix_caracteres", len(dit))
            await self.exp.vocal(personne, audio, ogg)
            self._noter_fil(personne, "envoye", "vocal", dit)
            return True
        except Exception as e:
            log.error("voix en échec (%s), réponse écrite : %s", self.conf.id, str(e)[:200])
            self._noter_journal("voix_echec", detail=type(e).__name__)
            return False

    async def _ecrire(self, personne: str, texte: str) -> None:
        envoye = nettoyer(masquer_secrets(texte))
        try:
            await self.exp.texte(personne, envoye)
            self._noter_fil(personne, "envoye", "texte", envoye)
        except Exception as e:
            log.error("envoi en échec (%s) : %s", self.conf.id, str(e)[:200])
            self._noter_journal("envoi_echec", detail=type(e).__name__)

    def _plus_tard(self, f, *args) -> None:
        """Une écriture de suivi, en arrière-plan : jamais sur le chemin d'une réponse, jamais en échec visible."""
        self._lancer(self._sans_echec(asyncio.to_thread(f, *args)))

    # L'heure est prise ici, pas à l'écriture : en arrière-plan, l'ordre du fil resterait sinon au hasard.

    def _noter_journal(self, genre: str, quantite: float = 1, detail: str = "") -> None:
        if self.journal is not None:
            self._plus_tard(self.journal.noter, genre, quantite, detail, time.time())

    def _noter_fil(self, personne: str, sens: str, genre: str, texte: str) -> None:
        if self.fil is not None:
            self._plus_tard(self.fil.noter, personne, sens, genre, texte or "", time.time())

    async def _noter(self, personne: str, quand: float) -> None:
        if self.contacts is not None and quand:
            await asyncio.to_thread(self.contacts.noter, personne, quand)

    async def ecrire_de_soi_meme(self, personne: str, texte: str, usage: str) -> str:
        """Un message que l'agent envoie sans qu'on vienne de lui écrire (rappel, relance).

        Rend « libre » (dans les 24 heures), « modele » (par le modèle Meta de cet
        usage) ou « attente » (ni l'un ni l'autre : à remettre au prochain message).
        """
        dernier = await asyncio.to_thread(self.contacts.dernier, personne) if self.contacts else None
        if fenetre_ouverte(dernier):
            await self.exp.texte(personne, nettoyer(texte))
            self._noter_fil(personne, "envoye", usage, nettoyer(texte))
            return "libre"
        modele = self.conf.modeles_meta.get(usage)
        if modele:
            await self.exp.modele(personne, modele.nom, modele.langue, [nettoyer(texte)[:1000]])
            self._noter_fil(personne, "envoye", "modele", nettoyer(texte)[:1000])
            return "modele"
        return "attente"

    async def _rappels_differes(self, personne: str) -> None:
        """Les rappels échus hors des 24 heures, sans modèle Meta : ils partent maintenant."""
        if self.rappels is None:
            return
        for r in await asyncio.to_thread(self.rappels.differes, personne):
            await self.exp.texte(personne, nettoyer(f"Rappel : {r['texte']}"))
            self._noter_fil(personne, "envoye", "rappel", nettoyer(f"Rappel : {r['texte']}"))
            await asyncio.to_thread(self.rappels.marquer, r["id"], "envoye")

    async def envoyer_rappels_echus(self, maintenant: float) -> dict:
        """Appelé par la porte à l'heure d'un rappel : envoie ce qui est échu, rend le prochain."""
        bilan = {"libre": 0, "modele": 0, "attente": 0, "echec": 0}
        if self.rappels is None:
            return {"prochain": None, **bilan}
        for r in await asyncio.to_thread(self.rappels.echus, maintenant):
            try:
                voie = await self.ecrire_de_soi_meme(r["personne"], f"Rappel : {r['texte']}", "rappel")
                await asyncio.to_thread(self.rappels.marquer, r["id"], "differe" if voie == "attente" else "envoye")
                bilan[voie] += 1
            except Exception as e:
                log.error("rappel en échec (%s) : %s", self.conf.id, str(e)[:200])
                self._noter_journal("rappel_echec", detail=type(e).__name__)
                bilan["echec"] += 1
        return {"prochain": await asyncio.to_thread(self.rappels.prochain), **bilan}

    @staticmethod
    async def _sans_echec(coro) -> None:
        try:
            await coro
        except Exception as e:
            log.warning("accessoire en échec : %s", str(e)[:200])
