"""Un tour de conversation sur WhatsApp, de la réception à la réponse (et le même tour par API).

- Les messages d'une même personne qui arrivent à quelques secondes d'intervalle
  sont lus ensemble (on envoie souvent plusieurs messages à la suite).
- Un vocal est transcrit, et le modèle sait que c'en est un et que sa réponse sera dite ; à un vocal, l'agent répond
  par un vocal s'il a une voix, et par écrit en plus ce qui se copie ou se clique (lien, e-mail, numéro, référence),
  ou tout, si la personne le demande ou accepte l'écrit que le vocal précédent lui proposait.
- Coches bleues et « en train d'écrire » dès la lecture, relancé toutes les 20 secondes ; un 👀 si le tour traîne,
  retiré à la réponse ; parfois une réaction d'humeur (noyau/humeur.py).
- Une réponse vide ou coupée au milieu d'une phrase : un dernier appel au modèle, sinon l'excuse (noyau/phrases.py).
- Hors des 24 heures de WhatsApp, un message de l'agent ne part que par un modèle Meta (noyau/envois.py).
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
from . import flux, phrases
from .api import DELAI_TOUR
from .autour import Autour, _borner
from .config import Config
from .envois import ABANDON_RAPPEL, ANNONCE_VALIDE, GARDE_JOURNAL, REESSAI_RAPPEL, Envois  # noqa: F401 (réexportés)
from .garde import TROP, TROP_JOUR, TROP_TU, Debit, Plafond, masquer_secrets
from .typographie import Remplaceur, nettoyer
from .voix import a_ecrire, se_prete
from .whatsapp import PIECES, Entrant, decrire_media

log = logging.getLogger("megga")

# Au-delà, une réponse est notée « lente » au journal (19.11.2026) : la lecture (les coches bleues) depuis l'envoi du message,
# la réponse depuis ce même envoi (un vocal à dire y compris).
LENT_LECTURE = 30
LENT_REPONSE = 120
EXCUSE = phrases.EXCUSE[0]
NON_COMPRIS = phrases.NON_COMPRIS[0]
REGARD = "\U0001F440"
NON_LU = "Je ne lis que les messages écrits, les vocaux, les photos et les documents pour le moment."
IMAGES_MAX = 5  # photos montrées au modèle dans un même tour (Photos.max)
IMAGE_MAX = 5_000_000  # octets, au-delà le modèle ne la voit pas (elle reste numérotée)
ECRIT = 20.0  # WhatsApp retire « en train d'écrire » après 25 s : relancé toutes les 20 s (D7)


def en_echec(sortie) -> bool:
    statut = getattr(sortie, "status", None)
    return str(getattr(statut, "value", statut) or "").upper() in {"ERROR", "CANCELLED"}


@dataclass
class _Boite:
    messages: list[Entrant] = field(default_factory=list)
    tache: asyncio.Task | None = None
    role: str = "public"


class Conversations(Envois, Autour):
    """Les conversations d'un client, une file par personne."""

    def __init__(self, conf: Config, agent, expediteur, voie=None, contacts=None, reecrire=None,
                 attente: float = 2.5, seuil_regard: float = 8.0, rappels=None, debit: Debit | None = None,
                 journal=None, fil=None, delai_api: float = DELAI_TOUR, agents: dict | None = None, medias=None,
                 differes=None, choix: dict | None = None, echeances: list | None = None, fil_tenu=None, etats=None,
                 juger=None, decrire=None, role_de=None, memoire=None, seconde_passe=None):
        self.conf = conf
        # L'agent de tous (sans rôles), ou un agent par rôle (noyau/roles.py) : {rôle: agent}.
        self.agent = agent
        self.agents = agents or {}
        # async f() appelée pendant l'attente d'un tour (packs/immobilier/reglages.py) ; aucune par défaut.
        self.avant_le_tour = None
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
        # Les plafonds du jour, par rôle s'il en a un (Role.par_jour, D9).
        self.plafond = Plafond(par_role={n: r.par_jour for n, r in conf.les_roles().items() if r.par_jour})
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
        # Le juge des réactions d'humeur : async f(texte, genre) -> émoji ou « » (noyau/humeur.py).
        self.juger = juger
        # La description des photos reçues : async f(images) -> [une ligne par photo] (Photos.decrire).
        self.decrire = decrire
        # Le rôle d'une personne hors d'un tour (un rappel à l'heure dite) : f(personne) -> rôle, lu hors de la boucle.
        self.role_de = role_de
        # La mémoire par les outils du noyau (noyau/memoire.py), pour le Contexte de chaque tour.
        self.memoire = memoire
        # Une seconde passe qu'un pack demande après la réponse (une transmission promise et pas faite, M9) :
        # async f(rôle, personne, réponse, début du tour) -> consigne ou None ; le tour est relancé une fois.
        self.seconde_passe = seconde_passe
        # Ce qui part sur WhatsApp ou se dit passe par les remplacements du client (Config.remplacements).
        self.remplaceur = Remplaceur(conf.remplacements)
        # Le dernier message de chaque personne, tel qu'elle l'a écrit ou dit (une règle apprise doit en venir).
        self._entendus: dict[str, str] = {}
        # L'heure du dernier modèle « message » envoyé à chaque personne : une annonce suffit tant qu'elle n'a pas répondu.
        # Gardée aussi dans la base (stockage.Etats) : un conteneur qui s'endort ne la renvoie pas (relecture, I13).
        self._annonces: dict[str, float] = {}
        self.etats = etats
        # Par personne : son rôle et son profil au dernier tour, les tours depuis sa dernière réaction d'humeur,
        # la conversation en cours (Historique.inactivite), l'écrit proposé par le dernier vocal.
        self._roles: dict[str, str] = {}
        self._profils: dict[str, str] = {}
        self._depuis_reaction: dict[str, int] = {}
        self._sessions: dict[str, dict] = {}
        self._offres: dict[str, float] = {}
        self._boites: dict[str, _Boite] = {}
        # Un verrou par personne, tant qu'un tour la concerne ; oublié ensuite (_a_son_tour).
        self._verrous: dict[str, list] = {}
        self.taches: set[asyncio.Task] = set()

    def _lancer(self, coro) -> asyncio.Task:
        t = asyncio.create_task(coro)
        self.taches.add(t)
        t.add_done_callback(self.taches.discard)
        return t

    # Les réglages du rôle d'une personne

    def _role_conf(self, role: str | None):
        return self.conf.les_roles().get(role) if role else None

    def _tutoie(self, role: str | None) -> bool:
        r = self._role_conf(role)
        return bool(r and r.tutoiement)

    def _humeur(self, role: str | None) -> str:
        r = self._role_conf(role)
        return r.humeur if r is not None and r.humeur is not None else self.conf.humeur

    def _rafale(self, role: str | None) -> int | None:
        r = self._role_conf(role)
        return r.par_dix_minutes if r is not None else None

    def excuse(self, role: str | None) -> str:
        return phrases.phrase(phrases.EXCUSE, self._tutoie(role))

    def debit_libre(self, personne: str, role: str | None) -> bool:
        m = self._rafale(role)
        return self.debit.libre(personne) if m is None else self.debit.libre(personne, maximum=m)

    def debit_attente(self, personne: str, role: str | None) -> int:
        m = self._rafale(role)
        return self.debit.attente(personne) if m is None else self.debit.attente(personne, maximum=m)

    def _debit_permis(self, personne: str, role: str | None) -> bool:
        m = self._rafale(role)
        return self.debit.permis(personne) if m is None else self.debit.permis(personne, maximum=m)

    async def _role_de(self, personne: str) -> str | None:
        if personne in self._roles:
            return self._roles[personne]
        if self.role_de is None:
            return None
        try:
            return await asyncio.to_thread(self.role_de, personne)
        except Exception as e:
            log.warning("rôle illisible : %s", str(e)[:200])
            return None

    def recevoir(self, m: Entrant, role: str = "public") -> None:
        """Range le message ; le tour part après un court délai, avec ceux qui suivent. `role` : celui de la
        personne (noyau/roles.py), qui choisit l'agent qui lui répond."""
        b = self._boites.setdefault(m.de, _Boite(role=role))
        b.messages.append(m)
        if b.tache is None:
            b.tache = self._lancer(self._attendre(m.de))

    async def _attendre(self, personne: str) -> None:
        # Ce qui doit être à jour avant de répondre (les réglages que le client change lui-même, packs) : pendant l'attente.
        if self.avant_le_tour is not None:
            await asyncio.gather(asyncio.sleep(self.attente), self._sans_echec(self.avant_le_tour()))
        else:
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

    def vocal_seul(self, personne: str) -> bool:
        """Cette personne attend-elle un vocal seul pendant ce tour ? (pas de cartes, M5)"""
        return personne in getattr(self.exp, "sans_cartes", ())

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
            self._roles[personne] = role
            if dernier.profil:
                self._profils[personne] = dernier.profil
            _borner(self._roles)
            _borner(self._profils)
            premier = await self._premier(personne, role)
            await self._sans_echec(self._noter(personne, max(m.envoye for m in messages), dernier.profil))
            await self._sans_echec(self.exp.lu(dernier.id))
            ecrit = asyncio.create_task(self._relancer_ecrit(dernier.id))
            try:
                await self._tour_lu(personne, messages, role, premier)
            finally:
                ecrit.cancel()

    async def _relancer_ecrit(self, message_id: str) -> None:
        while True:
            await asyncio.sleep(ECRIT)
            await self._sans_echec(self.exp.lu(message_id))

    async def _tour_lu(self, personne: str, messages: list[Entrant], role: str, premier: bool) -> None:
        dernier = messages[-1]
        # Le temps que la personne a attendu : depuis l'envoi de son plus ancien message (l'heure de Meta, à la seconde près).
        debut = min((m.envoye for m in messages if m.envoye), default=0)
        lecture = time.time() - debut if debut else 0.0
        livres = {"n": 0}
        await self._sans_echec(self._rappels_differes(personne, livres, role))
        # Le bouton d'un modèle Meta (« Afficher », « Voir la demande ») : ce qui attendait vient de partir, c'est la
        # réponse ; son libellé n'est pas une question pour le modèle (relecture du 16.11.2026, I11).
        if livres["n"] and all(m.genre == "button" for m in messages):
            for m in messages:
                self._noter_fil(personne, "recu", "bouton", m.texte)
            return
        if not self._debit_permis(personne, role):
            for m in messages:  # reçus, mais sans tour
                self._noter_fil(personne, "recu", "vocal" if m.vocal else (m.media.genre if m.media else "texte"), m.texte)
            if self.debit.prevenir(personne):
                await self._ecrire(personne, TROP_TU if self._tutoie(role) else TROP)
            return
        if (atteint := self.plafond.libre(personne, role)) is not None:
            for m in messages:
                self._noter_fil(personne, "recu", "vocal" if m.vocal else (m.media.genre if m.media else "texte"), m.texte)
            self.noter_plafond(atteint)
            if self.plafond.prevenir(personne):
                await self._ecrire(personne, TROP_JOUR)
            return
        self.plafond.compter(personne, role)
        etat = {"pose": False, "humeur": False, "fini": False, "id": dernier.id}
        regard = self._lancer(self._regard(personne, dernier.id, etat)) if self.conf.reactions else None
        try:
            await self._repondre(personne, messages, role, premier, etat)
            self.noter_delais(debut, lecture)
        finally:
            etat["fini"] = True
            if regard:
                regard.cancel()
            if etat["pose"] and not etat["humeur"]:
                await self._sans_echec(self.exp.reaction(personne, dernier.id, ""))

    async def _regard(self, personne: str, message_id: str, etat: dict) -> None:
        await asyncio.sleep(self.seuil_regard)
        if etat["humeur"] or etat["fini"]:
            return
        await self._sans_echec(self.exp.reaction(personne, message_id, REGARD))
        etat["pose"] = True

    def _accueil(self, role: str) -> dict[str, str]:
        r = self.conf.les_roles().get(role)
        return r.accueil if r is not None else {}

    def _redit(self, role: str) -> tuple[str, ...]:
        r = self.conf.les_roles().get(role)
        return r.accueil_redit if r is not None else ()

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
            reponse = self.excuse(role)
        if reponse:
            await self._ecrire(personne, reponse)
        return True

    async def _repondre(self, personne: str, messages: list[Entrant], role: str = "public", premier: bool = False,
                        etat: dict | None = None) -> None:
        etat = etat if etat is not None else {"pose": False, "humeur": False, "fini": False, "id": ""}
        parties, bruts, vocal, sourd, images, photos, rang, choisis = [], [], False, False, [], [], 0, 0
        pieces = self.conf.pieces_au_modele
        for m in messages:
            if m.choix and await self._choisi(personne, role, m.choix):
                choisis += 1
            elif m.vocal:
                vocal = True
                texte = await self._ecouter(m.vocal)
                self._noter_fil(personne, "recu", "vocal", texte)
                if texte:
                    parties.append(phrases.TRANSCRIT + texte)
                    bruts.append(texte)
                else:
                    sourd = True
                    if pieces:
                        parties.append(phrases.NON_TRANSCRIT)
            elif m.media:
                # La photo, la vidéo ou le document, numérotés : l'agent les voit, ses outils les retrouvent.
                rang += 1
                n = await self._numeroter(personne, m.media, rang)
                parties.append(decrire_media(m.media, n) + (f"\n{m.texte}" if m.texte else ""))
                bruts.append(m.texte)
                self._noter_fil(personne, "recu", m.media.genre, (f"[média {n}] " + m.texte).strip())
                if m.media.genre == "image" and len(images) < self.conf.photos.max:
                    vue = await self._regarder(m.media)
                    if vue is not None:
                        images.append(vue)
                        photos.append((len(parties) - 1, n))
            elif m.texte:
                self._noter_fil(personne, "recu", "texte", m.texte)
                parties.append(m.texte)
                bruts.append(m.texte)
            elif pieces and m.genre in PIECES:  # une position, un autocollant, une fiche contact (D13)
                self._noter_fil(personne, "recu", m.genre, "")
                parties.append(phrases.piece(PIECES[m.genre]))
        entendu = "\n".join(parties).strip()
        brut = "\n".join(b for b in bruts if b).strip()
        if not entendu:
            if not choisis:
                await self._ecrire(personne, phrases.phrase(phrases.NON_COMPRIS, self._tutoie(role)) if sourd else NON_LU)
            return
        await self._decrire_photos(parties, photos, images)
        entendu = "\n".join(parties).strip()
        bienvenue = self._bienvenue(role, brut or entendu, messages[-1].profil) if premier else ""
        if bienvenue:
            await self._ecrire(personne, bienvenue)
            if accueils.est_salutation(brut):  # à une simple salutation, l'accueil seul
                return
        humeur = self._humeur_du_tour(personne, role, brut, etat)
        # Le vocal (M5) : la réponse sera dite ; l'écrit, demandé ou accepté, la suit en entier.
        parle = vocal and self.voie is not None and self.voie.parle
        offre = await self._offre(personne) if brut else False
        ecrit = vocal and bool(phrases.PAR_ECRIT.search(brut) or (offre and phrases.OUI.match(brut)))
        consignes = []
        if parle:
            consignes.append(phrases.VOCAL_ECRIT if ecrit else phrases.VOCAL_DIT)
        elif offre and phrases.OUI.match(brut):
            consignes.append(phrases.ECRIT_ACCEPTE)
        if bienvenue:
            consignes.append(accueils.APRES_ACCUEIL)
        sans_cartes = getattr(self.exp, "sans_cartes", None) if parle and not ecrit else None
        if sans_cartes is not None:
            sans_cartes.add(personne)
        try:
            reponse, echec = await self._executer(personne, "\n".join([entendu, *consignes]), role, images, brut=brut or entendu)
        finally:
            if sans_cartes is not None:
                sans_cartes.discard(personne)
            if humeur is not None:
                with contextlib.suppress(Exception):
                    await humeur
        if bienvenue and not echec:
            reponse = accueils.apres_accueil(reponse, bienvenue, self._redit(role))
        elif premier and not echec and self._accueil(role):  # l'accueil écrit par le modèle, jamais complété en doublon
            reponse = accueils.sans_doublon(reponse, brut, self._accueil(role), self._redit(role))
        if not reponse.strip():
            return
        if parle and not echec and se_prete(reponse):
            dit = await self._dire(personne, reponse, brut, role)
            if dit is not None:
                if ecrit or a_ecrire(reponse, self.conf.oral.references):
                    await self._ecrire(personne, reponse)
                # Le vocal a proposé le détail par écrit : un oui au message suivant le fait partir.
                await self._garder_offre(personne, not ecrit and bool(phrases.OFFRE_ECRIT.search(dit)))
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

    async def _executer(self, personne: str, entendu: str, role: str = "public", images: list | None = None,
                        brut: str | None = None, sur_evenement=None) -> tuple[str, bool]:
        """Le tour du modèle (mémoire, outils) : (réponse, échec) ; l'excuse du noyau s'il échoue, jamais l'erreur. Une
        réponse vide ou coupée : un dernier appel, sans outil (M1, M2).
        `sur_evenement` : async f(genre, valeur), appelée au fil du premier appel (« texte » : un morceau brut du
        modèle, « outil » : {outil, etat}) ; sans elle, le tour se fait d'un bloc, comme avant. Les derniers appels
        (réponse vide, seconde passe, réponse coupée) ne passent pas par le flux : la réponse rendue fait foi."""
        self._entendus[personne] = brut if brut is not None else entendu
        _borner(self._entendus)
        self._roles.setdefault(personne, role)
        agent = self.agent_du_role(role)
        debut = time.time()
        try:
            session = await self._session(personne)
            options = {"images": images} if images else {}
            if sur_evenement is None:
                sortie = await agent.arun(entendu, user_id=personne, session_id=session, **options)
            else:
                sortie = await flux.suivre(agent.arun(entendu, user_id=personne, session_id=session, stream=True,
                                                  stream_events=True, yield_run_output=True, **options), sur_evenement)
            if en_echec(sortie):
                log.error("tour en échec (%s)", self.conf.id)
                self.noter_journal("tour_echec", detail=str(getattr(sortie, "status", ""))[:60])
                return self.excuse(role), True
            reponse = getattr(sortie, "content", None) or ""
            if not str(reponse).strip():
                reponse = await self._conclure(agent, personne, session, phrases.FINIR)
                if not reponse:
                    log.error("réponse vide (%s)", self.conf.id)
                    self.noter_journal("tour_echec", detail="vide")
                    return self.excuse(role), True
            if self.seconde_passe is not None:
                consigne = await self.seconde_passe(role, personne, str(reponse), debut)
                if consigne:
                    relance = await self._conclure(agent, personne, session, f"[{consigne.strip().strip('[]')}]")
                    reponse = relance or reponse
            if self.conf.reprendre_coupees and phrases.inacheve(reponse):
                repris = await self._conclure(agent, personne, session, phrases.REPRENDRE)
                if repris and not phrases.inacheve(repris):
                    reponse = repris
                else:
                    self.noter_journal("reponse_coupee")
            if self.fil_tenu is not None:  # après la réponse, en arrière-plan
                self._lancer(self._sans_echec(self.fil_tenu.apres(personne)))
            return str(reponse), False
        except Exception as e:
            log.error("tour en échec (%s) : %s", self.conf.id, str(e)[:300])
            self.noter_journal("tour_echec", detail=type(e).__name__)
            return self.excuse(role), True

    async def _conclure(self, agent, personne: str, session: str, consigne: str) -> str:
        """Un dernier appel, sur une consigne du système : la réponse, ou « » s'il échoue."""
        try:
            sortie = await agent.arun(consigne, user_id=personne, session_id=session)
            return "" if en_echec(sortie) else str(getattr(sortie, "content", None) or "").strip()
        except Exception as e:
            log.warning("dernier appel en échec (%s) : %s", self.conf.id, str(e)[:200])
            return ""

    def noter_plafond(self, atteint: str) -> None:
        """Le plafond du jour atteint (« personne » ou « client ») : au journal, une fois par jour, sans numéro."""
        if self.plafond.signaler(atteint):
            log.warning("plafond du jour atteint (%s, %s)", atteint, self.conf.id)
            self.noter_journal("plafond", detail=atteint)

    def entendu(self, personne: str) -> str:
        """Le dernier message de cette personne, tel qu'elle l'a écrit ou dit."""
        return self._entendus.get(personne, "")

    async def repondre_api(self, personne: str, texte: str, role: str = "public", sur_evenement=None) -> tuple[str, bool] | None:
        """Un tour demandé par un logiciel (noyau/api.py) : la réponse est rendue, rien ne part sur WhatsApp.

        Pas de regroupement d'attente (le logiciel envoie un message entier), pas de rappels. Les tours d'une
        même personne passent l'un après l'autre. Rend (réponse, échec), ou None si le débit de la personne
        est dépassé : rien n'est alors noté, le logiciel renverra le même message.

        Avec `sur_evenement` (async f(genre, valeur)), la réponse part aussi au fil de l'eau (noyau/flux.py) : les
        morceaux de texte, masqués, et les outils. La réponse rendue à la fin reste celle qui fait foi. Au premier
        message, avec l'accueil, le texte ne part qu'à la fin du tour, en entier : le modèle peut redire l'accueil. De
        même pour un client qui a des remplacements (Config.remplacements) : aucun nom ne part avant son filtre.
        """
        relais = flux.Relais(sur_evenement) if sur_evenement else None
        lance = asyncio.current_task()
        if lance is not None:  # un arrêt en douceur attend aussi les tours par API
            self.taches.add(lance)
        try:
            async with self._a_son_tour(personne):
                if not self._debit_permis(personne, role):
                    return None
                self.plafond.compter(personne, role)
                self._roles[personne] = role
                premier = await self._premier(personne, role)
                await self._sans_echec(self._noter(personne, time.time()))
                self._noter_fil(personne, "recu", "texte", texte)
                bienvenue = self._bienvenue(role, texte) if premier else ""
                # Le texte du flux attend la conclusion quand la réponse n'est filtrée qu'en entier : l'accueil (le modèle
                # peut le redire, apres_accueil) ou les remplacements du client (un motif peut tenir sur deux morceaux).
                retenu = relais is not None and bool(bienvenue or self.remplaceur)
                if bienvenue and accueils.est_salutation(texte):
                    brute, echec = bienvenue, False
                else:
                    suivi = relais
                    if retenu:  # le texte attend la conclusion (plus bas) ; les outils partent pendant le tour
                        async def suivi(genre, valeur):
                            if genre != "texte":
                                await relais(genre, valeur)
                    try:
                        brute, echec = await asyncio.wait_for(
                            self._executer(personne, f"{texte}\n{accueils.APRES_ACCUEIL}" if bienvenue else texte, role, brut=texte,
                                           sur_evenement=suivi), self.delai_api)
                    except asyncio.TimeoutError:
                        log.error("tour par API trop long (%s), abandonné après %.0f s", self.conf.id, self.delai_api)
                        self.noter_journal("tour_echec", detail="delai")
                        brute, echec = self.excuse(role), True
                    if bienvenue and not echec:  # l'accueil, puis la réponse, sans rien qui le redise
                        brute = "\n\n".join(p for p in (bienvenue, accueils.apres_accueil(brute, bienvenue, self._redit(role))) if p)
                reponse = self.remplaceur.texte(nettoyer(masquer_secrets(brute)))
                if relais is not None:
                    # Le texte retenu (accueil ou filtre de noms) part en entier, filtré, une fois le tour réussi :
                    # jamais l'accueil deux fois, ni affiché puis remplacé par l'excuse, ni un nom avant son filtre.
                    if retenu and not echec:
                        await relais("texte", self.remplaceur.texte(brute))
                    await relais.finir()
                self._noter_fil(personne, "envoye", "texte", reponse)
                return reponse, echec
        finally:
            if lance is not None:
                self.taches.discard(lance)

    async def _ecrire(self, personne: str, texte: str) -> None:
        envoye = self.remplaceur.texte(nettoyer(masquer_secrets(texte)))
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

    def noter_delais(self, debut: float, lecture: float) -> None:
        """Les temps d'un tour réussi : jusqu'à la lecture, puis jusqu'à la réponse (secondes, depuis l'envoi du message)."""
        if not debut:
            return
        lecture, reponse = max(0.0, lecture), max(0.0, time.time() - debut)
        self.noter_journal("delai_lecture", round(lecture, 1))
        self.noter_journal("delai_reponse", round(reponse, 1))
        if lecture > LENT_LECTURE or reponse > LENT_REPONSE:
            self.noter_journal("reponse_lente", round(reponse, 1), f"lecture {lecture:.0f} s, réponse {reponse:.0f} s")

    def noter_journal(self, genre: str, quantite: float = 1, detail: str = "") -> None:
        if self.journal is not None:
            self._plus_tard(self.journal.noter, genre, quantite, detail, time.time())

    def noter_envoi(self, personne: str, genre: str, texte: str) -> None:
        """Un envoi fait par un outil pendant un tour (une fiche PDF, une vidéo) : dans le fil, que le suivi relit (audit du
        17.11.2026 : quatre fiches annoncées, trois vues, et rien pour le vérifier)."""
        self._noter_fil(personne, "envoye", genre, texte)

    def _noter_fil(self, personne: str, sens: str, genre: str, texte: str) -> None:
        if self.fil is not None:
            self._plus_tard(self.fil.noter, personne, sens, genre, texte or "", time.time())

    async def _noter(self, personne: str, quand: float, nom: str = "") -> None:
        if self.contacts is not None and quand:
            await asyncio.to_thread(self.contacts.noter, personne, quand, nom)

    @staticmethod
    async def _sans_echec(coro) -> None:
        try:
            await coro
        except Exception as e:
            log.warning("accessoire en échec : %s", str(e)[:200])
