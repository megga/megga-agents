"""Un tour de conversation sur WhatsApp, de la réception à la réponse (et le même tour par API).

- Les messages d'une même personne qui arrivent à quelques secondes d'intervalle
  sont lus ensemble (on envoie souvent plusieurs messages à la suite).
- Un vocal est transcrit ; à un vocal, l'agent répond par un vocal s'il a une voix,
  et par écrit en plus ce qui se copie ou se clique (lien, e-mail, numéro).
- Coches bleues et « en train d'écrire » dès la lecture ; un 👀 si le tour traîne,
  retiré à la réponse.
- Hors des 24 heures de WhatsApp, un message de l'agent ne part que par un modèle Meta.
- Une erreur technique n'est jamais envoyée telle quelle.
- L'accueil d'un rôle (Role.accueil) part tel quel au premier message d'une conversation (noyau/accueil.py).
- Un choix touché dans une liste ou sur un bouton qu'un pack sait traiter (`choix`, par préfixe) l'est sans le
  modèle ; un message que l'agent envoie de lui-même hors des 24 heures attend le prochain message de la personne.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from dataclasses import dataclass, field

from . import accueil as accueils
from .api import DELAI_TOUR
from .config import Config
from .garde import TROP, TROP_JOUR, Debit, Plafond, masquer_secrets
from .oral import pour_la_voix
from .typographie import nettoyer
from .voix import a_ecrire, se_prete
from .whatsapp import Entrant, decrire_media, fenetre_ouverte

log = logging.getLogger("megga")

EXCUSE = "Je rencontre un petit souci technique. Je reviens vers vous dès que possible."
NON_COMPRIS = "Je n'ai pas pu écouter ce vocal. Pouvez-vous me l'écrire ?"
REGARD = "\U0001F440"
REESSAI_RAPPEL = 300  # secondes avant de retenter un rappel en échec
GARDE_JOURNAL = 400 * 86400  # le journal du noyau (échecs, volumes) : un peu plus d'un an
ABANDON_RAPPEL = 24 * 3600  # un rappel encore en échec un jour après son heure est abandonné (noté au journal)
NON_LU = "Je ne lis que les messages écrits, les vocaux, les photos et les documents pour le moment."
IMAGES_MAX = 5  # photos montrées au modèle dans un même tour
IMAGE_MAX = 5_000_000  # octets, au-delà le modèle ne la voit pas (elle reste numérotée)
ANNONCE_VALIDE = 12 * 3600  # un modèle « message » vaut pour ce qui s'ajoute pendant douze heures, tant que la personne n'a pas répondu


def en_echec(sortie) -> bool:
    statut = getattr(sortie, "status", None)
    return str(getattr(statut, "value", statut) or "").upper() in {"ERROR", "CANCELLED"}


@dataclass
class _Boite:
    messages: list[Entrant] = field(default_factory=list)
    tache: asyncio.Task | None = None
    role: str = "public"


class Conversations:
    """Les conversations d'un client, une file par personne."""

    def __init__(self, conf: Config, agent, expediteur, voie=None, contacts=None, reecrire=None,
                 attente: float = 2.5, seuil_regard: float = 8.0, rappels=None, debit: Debit | None = None,
                 journal=None, fil=None, delai_api: float = DELAI_TOUR, agents: dict | None = None, medias=None,
                 differes=None, choix: dict | None = None, echeances: list | None = None, fil_tenu=None, etats=None):
        self.conf = conf
        # L'agent de tous (sans rôles), ou un agent par rôle (noyau/roles.py) : {rôle: agent}.
        self.agent = agent
        self.agents = agents or {}
        # Les médias reçus, numérotés par personne (stockage.Medias) ; sans eux, numérotés dans le tour seulement.
        self.medias = medias
        self.exp = expediteur
        self.voie = voie
        self.contacts = contacts
        self.reecrire = reecrire
        self.attente = attente
        self.seuil_regard = seuil_regard
        self.rappels = rappels
        self.debit = debit or Debit()
        self.plafond = Plafond()
        self._purge_le = 0.0
        # Un tour par API ne retient pas la personne plus longtemps que le logiciel n'attend.
        self.delai_api = delai_api
        # Le suivi, écrit en arrière-plan : il ne retarde ni ne fait échouer un tour.
        # Le journal (stockage.Journal) : échecs et volumes de voix, jamais de texte.
        # Le fil (stockage.Fil) : les messages tels que la personne les a vécus.
        self.journal = journal
        self.fil = fil
        # Ce que l'agent envoie de lui-même hors des 24 heures, gardé pour le prochain message (stockage.Differes).
        self.differes = differes
        # Les choix touchés que les packs traitent eux-mêmes : {préfixe: async f(personne, rôle, charge) -> réponse}.
        self.choix = dict(choix or {})
        # Ce que les packs ont à faire à l'heure dite (un visiteur à prévenir) : async f(maintenant) -> prochaine heure.
        self.echeances = list(echeances or [])
        # Le fil des conversations (noyau/fil.py), refait après les réponses, s'il est réglé.
        self.fil_tenu = fil_tenu
        # Le dernier message de chaque personne, tel que le modèle l'a lu (une règle apprise doit en venir).
        self._entendus: dict[str, str] = {}
        # L'heure du dernier modèle « message » envoyé à chaque personne : une annonce suffit tant qu'elle n'a pas répondu.
        # Gardée aussi dans la base (stockage.Etats) : un conteneur qui s'endort ne la renvoie pas (relecture, I13).
        self._annonces: dict[str, float] = {}
        self.etats = etats
        self._boites: dict[str, _Boite] = {}
        # Un verrou par personne, tant qu'un tour la concerne ; oublié ensuite (_a_son_tour).
        self._verrous: dict[str, list] = {}
        self.taches: set[asyncio.Task] = set()

    def _lancer(self, coro) -> asyncio.Task:
        t = asyncio.create_task(coro)
        self.taches.add(t)
        t.add_done_callback(self.taches.discard)
        return t

    def recevoir(self, m: Entrant, role: str = "public") -> None:
        """Range le message ; le tour part après un court délai, avec ceux qui suivent. `role` : celui de la
        personne (noyau/roles.py), qui choisit l'agent qui lui répond."""
        b = self._boites.setdefault(m.de, _Boite(role=role))
        b.messages.append(m)
        if b.tache is None:
            b.tache = self._lancer(self._attendre(m.de))

    async def _attendre(self, personne: str) -> None:
        await asyncio.sleep(self.attente)
        b = self._boites.pop(personne)
        await self._tour(personne, b.messages, b.role)

    def entre_les_tours(self, personne: str):
        """Attend que le tour en cours de cette personne soit fini, et la garde le temps du bloc : ce que l'agent lui
        envoie de lui-même ne s'intercale pas dans une réponse en route."""
        return self._a_son_tour(personne)

    def apres_le_tour(self, personne: str, coro_fn) -> None:
        """Lance `coro_fn()` une fois fini le tour en cours de cette personne (sa réponse partie) : un outil qui
        prévient quelqu'un d'autre ne passe pas devant la réponse qu'il prépare."""
        async def ensuite():
            async with self._a_son_tour(personne):
                pass
            await self._sans_echec(coro_fn())

        self._lancer(ensuite())

    def agent_du_role(self, role: str):
        return self.agents.get(role, self.agent)

    @contextlib.asynccontextmanager
    async def _a_son_tour(self, personne: str):
        """Les tours d'une même personne passent l'un après l'autre. Le verrou est oublié quand plus personne
        ne l'attend : un logiciel peut amener autant de personnes qu'il veut sans que la mémoire grossisse."""
        entree = self._verrous.setdefault(personne, [asyncio.Lock(), 0])
        entree[1] += 1
        try:
            async with entree[0]:
                yield
        finally:
            entree[1] -= 1
            if entree[1] == 0 and self._verrous.get(personne) is entree:
                del self._verrous[personne]

    async def _tour(self, personne: str, messages: list[Entrant], role: str = "public") -> None:
        async with self._a_son_tour(personne):
            dernier = messages[-1]
            premier = await self._premier(personne, role)
            await self._sans_echec(self._noter(personne, max(m.envoye for m in messages)))
            await self._sans_echec(self.exp.lu(dernier.id))
            livres = {"n": 0}
            await self._sans_echec(self._rappels_differes(personne, livres))
            # Le bouton d'un modèle Meta (« Afficher », « Voir la demande ») : ce qui attendait vient de partir, c'est la
            # réponse ; son libellé n'est pas une question pour le modèle (relecture du 16.11.2026, I11).
            if livres["n"] and all(m.genre == "button" for m in messages):
                for m in messages:
                    self._noter_fil(personne, "recu", "bouton", m.texte)
                return
            if not self.debit.permis(personne):
                for m in messages:  # reçus, mais sans tour
                    self._noter_fil(personne, "recu", "vocal" if m.vocal else (m.media.genre if m.media else "texte"), m.texte)
                if self.debit.prevenir(personne):
                    await self._ecrire(personne, TROP)
                return
            if (atteint := self.plafond.libre(personne, role)) is not None:
                for m in messages:
                    self._noter_fil(personne, "recu", "vocal" if m.vocal else (m.media.genre if m.media else "texte"), m.texte)
                self.noter_plafond(atteint)
                if self.plafond.prevenir(personne):
                    await self._ecrire(personne, TROP_JOUR)
                return
            self.plafond.compter(personne, role)
            etat = {"pose": False}
            regard = self._lancer(self._regard(personne, dernier.id, etat)) if self.conf.reactions else None
            try:
                await self._repondre(personne, messages, role, premier)
            finally:
                if regard:
                    regard.cancel()
                    if etat["pose"]:
                        await self._sans_echec(self.exp.reaction(personne, dernier.id, ""))

    async def _regard(self, personne: str, message_id: str, etat: dict) -> None:
        await asyncio.sleep(self.seuil_regard)
        await self._sans_echec(self.exp.reaction(personne, message_id, REGARD))
        etat["pose"] = True

    def _accueil(self, role: str) -> dict[str, str]:
        r = self.conf.les_roles().get(role)
        return r.accueil if r is not None else {}

    async def _premier(self, personne: str, role: str) -> bool:
        """Le premier message d'une conversation (rien de la personne depuis douze heures), pour un rôle qui a un accueil."""
        if not self._accueil(role) or self.contacts is None:
            return False
        try:
            dernier = await asyncio.to_thread(self.contacts.dernier, personne)
        except Exception as e:
            log.warning("contact illisible : %s", str(e)[:200])
            return False
        return dernier is None or time.time() - dernier > accueils.INACTIVITE

    def _bienvenue(self, role: str, entendu: str, profil: str = "") -> str:
        """L'accueil à envoyer, si la langue est sûre ; sinon « » (le modèle le traduit, sa consigne le dit)."""
        accueil = self._accueil(role)
        langue = accueils.langue_sure(entendu, accueil)
        return accueils.texte_accueil(accueil, langue, accueils.prenom_du_profil(profil)) if langue else ""

    async def _choisi(self, personne: str, role: str, charge: str) -> bool:
        """Un choix touché qu'un pack traite lui-même : sa réponse part, sans le modèle. Faux si aucun ne le connaît."""
        traiter = next((f for p, f in self.choix.items() if charge.startswith(p)), None)
        if traiter is None:
            return False
        self._noter_fil(personne, "recu", "choix", charge)
        try:
            reponse = await traiter(personne, role, charge)
        except Exception as e:
            log.error("choix en échec (%s) : %s", self.conf.id, str(e)[:200])
            self.noter_journal("choix_echec", detail=type(e).__name__)
            reponse = EXCUSE
        if reponse:
            await self._ecrire(personne, reponse)
        return True

    async def _repondre(self, personne: str, messages: list[Entrant], role: str = "public", premier: bool = False) -> None:
        parties, vocal, sourd, images, rang, choisis = [], False, False, [], 0, 0
        for m in messages:
            if m.choix and await self._choisi(personne, role, m.choix):
                choisis += 1
            elif m.vocal:
                vocal = True
                texte = await self._ecouter(m.vocal)
                self._noter_fil(personne, "recu", "vocal", texte)
                if texte:
                    parties.append(texte)
                else:
                    sourd = True
            elif m.media:
                # La photo, la vidéo ou le document, numérotés : l'agent les voit, ses outils les retrouvent.
                rang += 1
                n = await self._numeroter(personne, m.media, rang)
                parties.append(decrire_media(m.media, n) + (f"\n{m.texte}" if m.texte else ""))
                self._noter_fil(personne, "recu", m.media.genre, (f"[média {n}] " + m.texte).strip())
                if m.media.genre == "image" and len(images) < IMAGES_MAX:
                    vue = await self._regarder(m.media)
                    if vue is not None:
                        images.append(vue)
            elif m.texte:
                self._noter_fil(personne, "recu", "texte", m.texte)
                parties.append(m.texte)
        entendu = "\n".join(parties).strip()
        if not entendu:
            if not choisis:
                await self._ecrire(personne, NON_COMPRIS if sourd else NON_LU)
            return
        bienvenue = self._bienvenue(role, entendu, messages[-1].profil) if premier else ""
        if bienvenue:
            await self._ecrire(personne, bienvenue)
            if accueils.est_salutation(entendu):  # à une simple salutation, l'accueil seul
                return
        reponse, _ = await self._executer(personne, f"{entendu}\n{accueils.APRES_ACCUEIL}" if bienvenue else entendu, role, images)
        if bienvenue and reponse != EXCUSE:
            reponse = accueils.apres_accueil(reponse, bienvenue)
        if not reponse.strip():
            return
        if vocal and self.voie is not None and self.voie.parle and se_prete(reponse) and reponse != EXCUSE:
            if await self._dire(personne, reponse, entendu):
                if a_ecrire(reponse):
                    await self._ecrire(personne, reponse)
                return
        await self._ecrire(personne, reponse)

    async def _numeroter(self, personne: str, media, provisoire: int) -> int:
        """Le numéro du média pour cette personne (stockage.Medias), ou son rang dans le tour sans base."""
        if self.medias is None:
            return provisoire
        try:
            return await asyncio.to_thread(self.medias.noter, personne, media.genre, media.id, media.type, media.nom)
        except Exception as e:
            log.warning("média non rangé : %s", str(e)[:200])
            return provisoire

    async def _regarder(self, media):
        """Une photo reçue, pour que le modèle la voie (jamais gardée dans l'historique : store_media=False)."""
        try:
            from agno.media import Image

            return Image(content=await self.exp.telecharger(media.id, IMAGE_MAX), mime_type=media.type or "image/jpeg")
        except Exception as e:
            log.warning("photo illisible (%s) : %s", self.conf.id, str(e)[:200])
            return None

    async def _executer(self, personne: str, entendu: str, role: str = "public", images: list | None = None) -> tuple[str, bool]:
        """Le tour du modèle (mémoire, outils) : (réponse, échec) ; l'excuse du noyau s'il échoue, jamais l'erreur."""
        self._entendus[personne] = entendu
        if len(self._entendus) > 5000:  # oublie les plus anciens
            for p in list(self._entendus)[:1000]:
                del self._entendus[p]
        try:
            options = {"images": images} if images else {}
            sortie = await self.agent_du_role(role).arun(entendu, user_id=personne, session_id=personne, **options)
            if en_echec(sortie):
                log.error("tour en échec (%s)", self.conf.id)
                self.noter_journal("tour_echec", detail=str(getattr(sortie, "status", ""))[:60])
                return EXCUSE, True
            if self.fil_tenu is not None:  # après la réponse, en arrière-plan
                self._lancer(self._sans_echec(self.fil_tenu.apres(personne)))
            return getattr(sortie, "content", None) or "", False
        except Exception as e:
            log.error("tour en échec (%s) : %s", self.conf.id, str(e)[:300])
            self.noter_journal("tour_echec", detail=type(e).__name__)
            return EXCUSE, True

    def noter_plafond(self, atteint: str) -> None:
        """Le plafond du jour atteint (« personne » ou « client ») : au journal, une fois par jour, sans numéro."""
        if self.plafond.signaler(atteint):
            log.warning("plafond du jour atteint (%s, %s)", atteint, self.conf.id)
            self.noter_journal("plafond", detail=atteint)

    def entendu(self, personne: str) -> str:
        """Le dernier message de cette personne, tel que le modèle l'a lu dans son tour."""
        return self._entendus.get(personne, "")

    async def repondre_api(self, personne: str, texte: str, role: str = "public") -> tuple[str, bool] | None:
        """Un tour demandé par un logiciel (noyau/api.py) : la réponse est rendue, rien ne part sur WhatsApp.

        Pas de regroupement d'attente (le logiciel envoie un message entier), pas de rappels. Les tours d'une
        même personne passent l'un après l'autre. Rend (réponse, échec), ou None si le débit de la personne
        est dépassé : rien n'est alors noté, le logiciel renverra le même message.
        """
        lance = asyncio.current_task()
        if lance is not None:  # un arrêt en douceur attend aussi les tours par API
            self.taches.add(lance)
        try:
            async with self._a_son_tour(personne):
                if not self.debit.permis(personne):
                    return None
                self.plafond.compter(personne, role)
                premier = await self._premier(personne, role)
                await self._sans_echec(self._noter(personne, time.time()))
                self._noter_fil(personne, "recu", "texte", texte)
                bienvenue = self._bienvenue(role, texte) if premier else ""
                if bienvenue and accueils.est_salutation(texte):
                    brute, echec = bienvenue, False
                else:
                    try:
                        brute, echec = await asyncio.wait_for(
                            self._executer(personne, f"{texte}\n{accueils.APRES_ACCUEIL}" if bienvenue else texte, role), self.delai_api)
                    except asyncio.TimeoutError:
                        log.error("tour par API trop long (%s), abandonné après %.0f s", self.conf.id, self.delai_api)
                        self.noter_journal("tour_echec", detail="delai")
                        brute, echec = EXCUSE, True
                    if bienvenue and not echec:  # l'accueil, puis la réponse, sans rien qui le redise
                        brute = "\n\n".join(p for p in (bienvenue, accueils.apres_accueil(brute, bienvenue)) if p)
                reponse = nettoyer(masquer_secrets(brute))
                self._noter_fil(personne, "envoye", "texte", reponse)
                return reponse, echec
        finally:
            if lance is not None:
                self.taches.discard(lance)

    async def _ecouter(self, media_id: str) -> str:
        if self.voie is None or not self.voie.ecoute:
            return ""
        try:
            texte = await self.voie.transcrire(await self.exp.telecharger(media_id))
            self.noter_journal("vocal_entendu")
            return texte
        except Exception as e:
            log.error("vocal illisible (%s) : %s", self.conf.id, str(e)[:200])
            self.noter_journal("vocal_illisible", detail=type(e).__name__)
            return ""

    async def _dire(self, personne: str, reponse: str, entendu: str) -> bool:
        try:
            dit = await pour_la_voix(self.reecrire, nettoyer(reponse), entendu) if self.reecrire else reponse
            audio, ogg = await self.voie.dire(dit)
            self.noter_journal("voix_caracteres", len(dit))
            await self.exp.vocal(personne, audio, ogg)
            self._noter_fil(personne, "envoye", "vocal", dit)
            return True
        except Exception as e:
            log.error("voix en échec (%s), réponse écrite : %s", self.conf.id, str(e)[:200])
            self.noter_journal("voix_echec", detail=type(e).__name__)
            return False

    async def _ecrire(self, personne: str, texte: str) -> None:
        envoye = nettoyer(masquer_secrets(texte))
        try:
            await self.exp.texte(personne, envoye)
            self._noter_fil(personne, "envoye", "texte", envoye)
        except Exception as e:
            log.error("envoi en échec (%s) : %s", self.conf.id, str(e)[:200])
            self.noter_journal("envoi_echec", detail=type(e).__name__)

    def _plus_tard(self, f, *args) -> None:
        """Une écriture de suivi, en arrière-plan : jamais sur le chemin d'une réponse, jamais en échec visible."""
        self._lancer(self._sans_echec(asyncio.to_thread(f, *args)))

    # L'heure est prise ici, pas à l'écriture : en arrière-plan, l'ordre du fil resterait sinon au hasard.

    def noter_journal(self, genre: str, quantite: float = 1, detail: str = "") -> None:
        if self.journal is not None:
            self._plus_tard(self.journal.noter, genre, quantite, detail, time.time())

    def _noter_fil(self, personne: str, sens: str, genre: str, texte: str) -> None:
        if self.fil is not None:
            self._plus_tard(self.fil.noter, personne, sens, genre, texte or "", time.time())

    async def _noter(self, personne: str, quand: float) -> None:
        if self.contacts is not None and quand:
            await asyncio.to_thread(self.contacts.noter, personne, quand)

    async def ecrire_de_soi_meme(self, personne: str, texte: str, usage: str, variable: str | None = None) -> str:
        """Un message que l'agent envoie sans qu'on vienne de lui écrire (rappel, relance). Hors des 24 heures, le modèle
        Meta de cet usage reçoit `variable` (le texte lui-même, sans elle).

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
            try:
                await self.exp.modele(personne, modele.nom, modele.langue, [nettoyer(variable or texte)[:1000]])
                self._noter_fil(personne, "envoye", "modele", nettoyer(texte)[:1000])
                return "modele"
            except Exception as e:
                # Un modèle suspendu, reclassé ou refusé : le rappel attend le prochain message, sans boucler toutes les
                # 5 minutes (relecture du 16.11.2026, I10).
                log.error("modèle « %s » refusé (%s) : %s", usage, self.conf.id, str(e)[:200])
                self.noter_journal("envoi_echec", detail="modele")
        # Sans modèle de cet usage (ou refusé) : le modèle « message » annonce que quelque chose attend (le rappel part
        # au message suivant).
        await self._annoncer(personne)
        return "attente"

    async def envoyer_de_soi_meme(self, personne: str, messages: list[dict], usage: str, variables: list[str] | None = None,
                                  langue: str = "", garder: bool = True) -> str:
        """Des messages que l'agent envoie de lui-même à une personne (une demande pour un gestionnaire, une fiche
        pour un partenaire, une réponse pour un visiteur). `messages` : {"texte", "apercu"?}, {"document", "nom", "legende"}
        (un identifiant chez Meta) ou {"liste": {corps, bouton, section, lignes}}.

        Dans les 24 heures, ils partent. Au-delà, ils sont gardés pour son prochain message (stockage.Differes, sauf `garder` faux),
        et le modèle Meta de cet usage (« <usage>_<langue> » d'abord) l'annonce s'il est réglé, avec `variables`.
        Rend « libre », « modele », « attente », ou « aucune » (pas de WhatsApp, ou une personne venue par API).
        """
        if self.conf.whatsapp is None or personne.startswith("api:"):
            return "aucune"
        dernier = await asyncio.to_thread(self.contacts.dernier, personne) if self.contacts else None
        if fenetre_ouverte(dernier):
            await self._envoyer_messages(personne, messages, usage)
            return "libre"
        if garder and self.differes is not None:
            await asyncio.to_thread(self.differes.garder, personne, messages)
        modele = self.conf.modeles_meta.get(f"{usage}_{langue}") or self.conf.modeles_meta.get(usage)
        if modele:
            try:
                await self.exp.modele(personne, modele.nom, modele.langue, [nettoyer(v)[:1000] for v in (variables or [])])
                self._noter_fil(personne, "envoye", "modele", " | ".join(variables or []))
                return "modele"
            except Exception as e:
                log.error("modèle refusé (%s) : %s", self.conf.id, str(e)[:200])
                self.noter_journal("envoi_echec", detail="modele")
        # Le repli : le modèle « message » (« Vous avez un message de… ») annonce ce qui est gardé.
        if garder and self.differes is not None and await self._annoncer(personne, langue):
            return "modele"
        return "attente"

    async def _annoncer(self, personne: str, langue: str = "") -> bool:
        """Le modèle Meta « message » (« message_<langue> » d'abord), s'il est réglé : il annonce un message qui attend, sa
        réponse rouvre les 24 heures et ce qui était gardé part aussitôt. Sa variable : le nom de l'agent."""
        modele = self.conf.modeles_meta.get(f"message_{langue}") or self.conf.modeles_meta.get("message")
        if modele is None:
            return False
        # Déjà annoncé depuis son dernier message, il y a moins de douze heures : ce qui s'ajoute partira avec le reste.
        deja = self._annonces.get(personne)
        if deja is None and self.etats is not None:
            try:
                deja = await asyncio.to_thread(self.etats.lire, personne, "annonce")
            except Exception as e:
                log.warning("annonce illisible : %s", str(e)[:200])
        dernier = await asyncio.to_thread(self.contacts.dernier, personne) if self.contacts else None
        if deja and time.time() - deja < ANNONCE_VALIDE and (dernier is None or deja > dernier):
            return True
        try:
            await self.exp.modele(personne, modele.nom, modele.langue, [self.conf.nom_agent])
            self._noter_fil(personne, "envoye", "modele", "un message attend")
            self._annonces[personne] = time.time()
            if self.etats is not None:
                await self._sans_echec(asyncio.to_thread(self.etats.ecrire, personne, "annonce", self._annonces[personne]))
            if len(self._annonces) > 5000:
                for p in list(self._annonces)[:1000]:
                    del self._annonces[p]
            return True
        except Exception as e:
            log.error("modèle « message » refusé (%s) : %s", self.conf.id, str(e)[:200])
            self.noter_journal("envoi_echec", detail="modele")
            return False

    async def peut_ecrire(self, personne: str, usage: str, langue: str = "") -> bool:
        """Un message libre (dans les 24 heures) ou le modèle Meta de cet usage peut-il partir à cette personne ?"""
        if self.conf.whatsapp is None or personne.startswith("api:"):
            return False
        if self.conf.modeles_meta.get(f"{usage}_{langue}") or self.conf.modeles_meta.get(usage):
            return True
        if self.differes is not None and self.conf.modeles_meta.get("message"):
            return True
        return fenetre_ouverte(await asyncio.to_thread(self.contacts.dernier, personne) if self.contacts else None)

    async def _envoyer_messages(self, personne: str, messages: list[dict], usage: str) -> None:
        for m in messages:
            if m.get("document"):
                await self.exp.document(personne, m.get("nom") or "document.pdf", media_id=m["document"], legende=m.get("legende", ""))
                self._noter_fil(personne, "envoye", "document", m.get("legende") or m.get("nom") or "")
            elif m.get("liste"):
                l = m["liste"]
                await self.exp.liste(personne, nettoyer(l["corps"]), l["bouton"], l["section"], l["lignes"])
                self._noter_fil(personne, "envoye", "liste", nettoyer(l["corps"]))
            elif m.get("texte"):
                if m.get("apercu"):  # la carte d'une annonce : son lien avec son aperçu
                    await self.exp.texte(personne, nettoyer(m["texte"]), apercu=True)
                else:
                    await self.exp.texte(personne, m["texte"] if m.get("secret") else nettoyer(m["texte"]))
                # Un mot de passe ne se range jamais dans le fil (relu par la console et par le résumé du fil).
                self._noter_fil(personne, "envoye", usage, "(mot de passe envoyé)" if m.get("secret") else nettoyer(m["texte"]))

    async def _rappels_differes(self, personne: str, livres: dict | None = None) -> None:
        """Les rappels échus hors des 24 heures, sans modèle Meta, et les messages gardés : ils partent maintenant.
        `livres["n"]` : combien sont partis."""
        livres = {"n": 0} if livres is None else livres
        if self.differes is not None:
            # Chaque ligne gardée se retire une fois envoyée : un conteneur qui tombe en route ne perd rien.
            for ligne in await asyncio.to_thread(self.differes.a_envoyer, personne):
                rates = []
                for m in ligne["messages"]:
                    try:
                        await self._envoyer_messages(personne, [m], "differe")
                        livres["n"] += 1
                    except Exception as e:
                        # Retenté au message suivant, sans rajeunir (effacé après un mois) ni retenir ceux qui suivent.
                        log.error("message gardé non envoyé (%s) : %s", self.conf.id, str(e)[:200])
                        self.noter_journal("envoi_echec", detail="differe")
                        rates.append(m)
                if rates:
                    await asyncio.to_thread(self.differes.garder, personne, rates, ligne["quand"])
                await asyncio.to_thread(self.differes.retirer, ligne["ligne"])
        if self.rappels is None:
            return
        for r in await asyncio.to_thread(self.rappels.differes, personne):
            await self.exp.texte(personne, nettoyer(f"Rappel : {r['texte']}"))
            self._noter_fil(personne, "envoye", "rappel", nettoyer(f"Rappel : {r['texte']}"))
            await asyncio.to_thread(self.rappels.marquer, r["id"], "envoye")
            livres["n"] += 1

    async def envoyer_rappels_echus(self, maintenant: float) -> dict:
        """Appelé par la porte à l'heure d'un rappel : envoie ce qui est échu, rend le prochain."""
        bilan = {"libre": 0, "modele": 0, "attente": 0, "echec": 0}
        if self.journal is not None and maintenant >= self._purge_le:  # le journal ne grossit pas sans fin
            self._purge_le = maintenant + 86400
            await self._sans_echec(asyncio.to_thread(self.journal.purger, maintenant - GARDE_JOURNAL))
        if self.rappels is None:
            return {"prochain": await self._echeances(maintenant), **bilan}
        # Les rappels d'abord : une échéance d'un pack (une recherche sur les portails) peut prendre du temps.
        for r in await asyncio.to_thread(self.rappels.echus, maintenant):
            if self.conf.whatsapp is None:
                # Un agent sans WhatsApp (seulement par API) ne peut rien envoyer : un rappel d'avant est
                # annulé, au lieu d'échouer à chaque passage.
                await asyncio.to_thread(self.rappels.marquer, r["id"], "annule")
                self.noter_journal("rappel_echec", detail="sans WhatsApp")
                bilan["echec"] += 1
                continue
            try:
                async with self._a_son_tour(r["personne"]):  # jamais au milieu d'une réponse en route
                    voie = await self.ecrire_de_soi_meme(r["personne"], f"Rappel : {r['texte']}", "rappel", str(r["texte"]).strip().rstrip("."))
                await asyncio.to_thread(self.rappels.marquer, r["id"], "differe" if voie == "attente" else "envoye")
                bilan[voie] += 1
            except Exception as e:
                log.error("rappel en échec (%s) : %s", self.conf.id, str(e)[:200])
                if maintenant - float(r["quand"]) > ABANDON_RAPPEL:  # un jour d'échecs : abandonné, plus retenté
                    await asyncio.to_thread(self.rappels.marquer, r["id"], "echec")
                    self.noter_journal("rappel_echec", detail="abandonné après un jour")
                    continue
                self.noter_journal("rappel_echec", detail=type(e).__name__)
                bilan["echec"] += 1
        prochain = await asyncio.to_thread(self.rappels.prochain)
        if bilan["echec"] and prochain is not None:
            # Un rappel en échec reste à envoyer : il est retenté dans 5 minutes, pas en boucle.
            prochain = max(prochain, maintenant + REESSAI_RAPPEL)
        suivant = await self._echeances(maintenant)
        if suivant is not None:
            prochain = suivant if prochain is None else min(prochain, suivant)
        return {"prochain": prochain, **bilan}

    async def _echeances(self, maintenant: float) -> float | None:
        """Ce que les packs ont à faire à l'heure dite ; rend la plus proche des prochaines heures. Une échéance en
        échec est retentée dans 5 minutes."""
        prochaines = []
        for f in self.echeances:
            try:
                p = await f(maintenant)
            except Exception as e:
                log.error("échéance en échec (%s) : %s", self.conf.id, str(e)[:200])
                self.noter_journal("echeance_echec", detail=type(e).__name__)
                p = maintenant + REESSAI_RAPPEL
            if p is not None:
                prochaines.append(p)
        return min(prochaines) if prochaines else None

    @staticmethod
    async def _sans_echec(coro) -> None:
        try:
            await coro
        except Exception as e:
            log.warning("accessoire en échec : %s", str(e)[:200])
