"""La configuration d'un client : un client = une configuration, pas un développement.

Rien de secret ici : les clés et l'adresse de la base arrivent par l'environnement
(voir noyau/app.py). La configuration est validée au démarrage ; une erreur arrête
le conteneur plutôt que de laisser tourner un agent mal réglé.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

VERSION = 1
# Une image sert une configuration sans WhatsApp (entrée par API seulement) à partir de la version 2 de
# nos tables (stockage.SCHEMA_VERSION, que /sante donne) : le même lot, quel que soit son numéro de version.
SANS_WHATSAPP_SCHEMA = 2
ZONES = ("suisse", "europe", "etats-unis", "client")
# Les métiers, et les packs d'outils que chacun permet.
METIERS: dict[str, tuple[str, ...]] = {"general": (), "immobilier": ("immobilier",)}
# Les groupes d'outils qu'un rôle peut recevoir, par métier (en plus des rappels).
OUTILS_DES_ROLES: dict[str, tuple[str, ...]] = {"general": (), "immobilier": ("immobilier", "annonces", "partenaires", "visiteurs",
                                                                                "vitrine", "accueil", "marche", "travail")}
# Les groupes d'outils qui agissent au nom du compte d'un gestionnaire : seulement pour le rôle gestionnaire.
OUTILS_GESTIONNAIRE = ("annonces", "partenaires", "visiteurs", "marche", "travail")
# Les groupes qui lisent la gestion du site (packs/immobilier/gestion.py).
OUTILS_GESTION = ("annonces", "partenaires", "visiteurs", "vitrine", "accueil", "marche", "travail")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


PETIT_CLAUDE = "claude-haiku-5-5"


class Modeles(Strict):
    """Le modèle principal, celui qui prend le relais s'il échoue, et celui qui réécrit pour l'oral."""

    principal: str = "claude-sonnet-5-5"
    secours: str | None = "deepseek-v4-pro"
    # Le petit modèle de la réécriture pour un vocal et du résumé du fil ; vide : Claude Haiku quand le principal est Claude,
    # sinon le principal. Jamais le secours d'office : il ne sert qu'en panne, et ces textes portent les conversations
    # (relecture du 16.11.2026, I16). Un modèle DeepSeek (« deepseek-… ») y sert aussi.
    oral: str | None = None
    # Le modèle du fil (noyau/fil.py) ; vide : celui de l'oral (petit()).
    fil: str | None = None
    # Claude, le modèle principal : les jetons d'une réponse, la réflexion adaptative et son effort (parité, D8).
    jetons: int = Field(default=4096, ge=1024, le=64000)
    reflexion: bool = False
    effort: Literal["low", "medium", "high"] | None = None

    def petit(self) -> str:
        """Le modèle de l'oral et du fil."""
        if self.oral:
            return self.oral
        return PETIT_CLAUDE if self.principal.startswith("claude-") else self.principal

    def du_fil(self) -> str:
        return self.fil or self.petit()

    def juge(self) -> str:
        """Le petit modèle qui juge (une réaction d'humeur) et qui regarde les photos : Claude Haiku quand le principal est
        Claude (il voit les images), sinon le principal."""
        return PETIT_CLAUDE if self.principal.startswith("claude-") else self.principal


class Voix(Strict):
    """La voix ElevenLabs de l'agent : à un vocal, il répond par un vocal.

    Une voix garde l'accent de la personne enregistrée : une voix par langue si besoin.
    Sans voix réglée, l'agent transcrit les vocaux mais répond par écrit.
    """

    voix: str | None = Field(default=None, pattern=r"^[A-Za-z0-9]{10,40}$")
    par_langue: dict[str, str] = {}
    modele: str = "eleven_v4"
    transcription: str = "scribe_v3"
    stabilite: float = Field(default=0.5, ge=0, le=1)
    vitesse: float = Field(default=1.0, ge=0.7, le=1.2)
    # Le serveur d'ElevenLabs (https://api.eu.residency.elevenlabs.io pour l'UE, offre Enterprise).
    serveur: str = Field(default="https://api.elevenlabs.io", pattern=r"^https://[a-z0-9.-]+$")
    # La langue de la réponse (fr, en, es) imposée à ElevenLabs : sinon une voix devine le parler d'après le style
    # (un français familier glissait vers l'accent québécois). Refusée par le modèle (400, 422) : relue sans (M6).
    imposer_langue: bool = True
    # Les indications de jeu d'ElevenLabs que l'oral peut placer (« warmly », « softly ») : une au plus par vocal.
    # Vide : aucune, et tout crochet est ôté (un modèle qui ne les connaît pas les lirait à voix haute).
    balises: tuple[str, ...] = Field(default=(), max_length=12)

    @field_validator("balises")
    @classmethod
    def balises_simples(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        if any(not re.fullmatch(r"[a-z][a-z ]{1,30}", b) for b in v):
            raise ValueError("balises : des mots anglais en minuscules (warmly, laughs softly)")
        return v

    @field_validator("par_langue")
    @classmethod
    def langues(cls, v: dict[str, str]) -> dict[str, str]:
        for k, voix in v.items():
            if not re.fullmatch(r"[a-z]{2}", k) or not re.fullmatch(r"[A-Za-z0-9]{10,40}", voix):
                raise ValueError("par_langue : {code de langue: identifiant de voix}")
        return v


class ModeleMeta(Strict):
    """Un modèle de message approuvé par Meta (seul permis hors des 24 heures)."""

    nom: str = Field(pattern=r"^[a-z0-9_]{1,512}$")
    langue: str = Field(default="fr", pattern=r"^[a-z]{2}(_[A-Z]{2})?$")


class WhatsApp(Strict):
    """Le numéro du client chez Meta (identifiant du numéro dans l'API Cloud)."""

    numero_id: str = Field(pattern=r"^\d{6,30}$")
    version_graph: str = Field(default="v26.0", pattern=r"^v\d+\.\d+$")


# Les groupes d'outils qu'un rôle peut recevoir (noyau/roles.py, noyau/app.py, outils_du_client) :
#   annonces     les annonces du site (lot 7.2), pour un gestionnaire
#   partenaires  le registre des partenaires, leurs demandes, leurs recherches gardées (lot 7.4), pour un gestionnaire
#   visiteurs    les réponses aux visiteurs, l'envoi à un contact, les numéros bloqués (lot 7.4), pour un gestionnaire
#   vitrine      chercher dans la vitrine, sans prix ni adresse : l'outil d'un partenaire
#   accueil      chercher les biens publics, transmettre un contact, poser une question au courtier : ceux d'un visiteur
#   marche       les portails, la veille, le carnet des prix au m², le suivi des zones (lot 7.5), pour un gestionnaire
#   travail      les règles apprises en le corrigeant, le point, ses capacités (lot 7.6), pour un gestionnaire
GROUPES_OUTILS = ("rappels", "immobilier", "annonces", "partenaires", "visiteurs", "vitrine", "accueil", "marche", "travail")


class Role(Strict):
    """Ce qu'un rôle reçoit en plus des consignes de l'agent : ses consignes à lui, et ses outils.

    `accueil` : le premier message à une personne de ce rôle, mot pour mot, par langue ({"fr": …, "en": …}) ;
    envoyé par le noyau (noyau/accueil.py), seule retouche permise : son prénom après le premier mot."""

    consignes: str = Field(default="", max_length=12000)
    outils: tuple[Literal["rappels", "immobilier", "annonces", "partenaires", "visiteurs", "vitrine", "accueil", "marche", "travail"], ...] = ("rappels",)
    accueil: dict[str, str] = {}
    # Les phrases fixes du noyau (excuse, vocal non compris, trop de messages, rappel) au tutoiement (M4).
    tutoiement: bool = False
    # Les réactions d'humeur (🎉 une vente, 😂 une blague, 💪 un coup dur) : complices, sobres, ou celles de l'agent (None).
    humeur: Literal["aucune", "complice", "sobre"] | None = None
    # Les plafonds de ce rôle : tours par personne et par jour (None : 100, sans limite pour un gestionnaire), et par
    # dix minutes (None : 20 ; 0 : sans limite) (D9).
    par_jour: int | None = Field(default=None, ge=1, le=10000)
    par_dix_minutes: int | None = Field(default=None, ge=0, le=1000)
    # Le prénom tiré du profil WhatsApp, redit dans le Contexte de chaque tour (D11).
    prenom_du_profil: bool = False
    # Ce que l'oral sait de plus de ces personnes (« elle le vouvoie, et parle de Greg à la troisième personne »).
    oral: str = Field(default="", max_length=2000)
    # Les paragraphes d'une réponse qui redisent l'accueil déjà parti, par motifs (expressions régulières) (D11).
    accueil_redit: tuple[str, ...] = Field(default=(), max_length=10)

    @field_validator("oral")
    @classmethod
    def oral_sans_artefacts(cls, v: str) -> str:
        if re.search(r"[\u2014\u2013\u00b7]", v):
            raise ValueError("Pas de tiret long ni de point médian.")
        return v

    @field_validator("accueil_redit")
    @classmethod
    def motifs_redit(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(motif_valide(m) for m in v)

    @field_validator("consignes")
    @classmethod
    def sans_artefacts(cls, v: str) -> str:
        if re.search(r"[\u2014\u2013\u00b7]", v):
            raise ValueError("Pas de tiret long ni de point médian.")
        return v

    @field_validator("accueil")
    @classmethod
    def accueils(cls, v: dict[str, str]) -> dict[str, str]:
        for langue, texte in v.items():
            if not re.fullmatch(r"[a-z]{2}", langue) or not isinstance(texte, str) or not 10 <= len(texte) <= 1500:
                raise ValueError("accueil : {code de langue: texte de 10 à 1500 caractères}")
            if re.search(r"[\u2014\u2013\u00b7]", texte):
                raise ValueError("Pas de tiret long ni de point médian.")
        return v


class Roles(Strict):
    """Les personnes qui écrivent à l'agent, par rôle (noyau/roles.py). Sans rôles, tout le monde parle au même agent.

    gestionnaire : les gens du client (leurs numéros dans le secret GESTIONNAIRES, jamais ici) ;
    partenaire   : ceux que le client a inscrits (table megga_partenaires) ;
    visiteur     : toute autre personne ; sans ce rôle, un visiteur n'est pas servi (refus, une fois par jour s'il est réglé).
    Un numéro bloqué par le client n'est jamais lu.
    """

    gestionnaire: Role | None = None
    partenaire: Role | None = None
    visiteur: Role | None = None
    refus: str | None = Field(default=None, max_length=1000)


class Gestion(Strict):
    """La gestion du site du client (son API /api/gestion), que les outils des packs appellent au nom d'un
    gestionnaire. La clé est un secret (GESTION_CLE), jamais ici. `sites` : les biens dont l'identifiant
    commence par ce préfixe ont leur propre site."""

    url: str = Field(pattern=r"^https://[a-z0-9.-]+(:\d+)?$")
    sites: dict[str, str] = {}
    # Les noms que les textes d'une annonce ne doivent jamais porter (les gens de l'équipe, l'agent).
    noms_interdits: tuple[str, ...] = ()
    # Le modèle de fiche PDF du client (fiche/modeles/<modèle> : ses polices et son logo), s'il en a un.
    fiche: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9-]{0,62}$")
    # Le formulaire « Nouvelle annonce » publié chez Meta (WhatsApp Flow), s'il y en a un.
    formulaire_annonce: str | None = Field(default=None, pattern=r"^\d{6,30}$")
    # Les sites (préfixes de `sites`) dont les biens sont publics : un visiteur en voit le prix et le lien. Ceux
    # du site principal et des autres sites se présentent en une ligne, sans prix ni lien (lot 7.4).
    publics: tuple[str, ...] = ()
    # Le site principal, s'il s'ouvre au public et se referme comme les autres (porte_site) : {nom: adresse publique}.
    # Son nom n'est le préfixe d'aucun bien (Greg, 16.11.2026 : « geneve », fspgeneva.com).
    principal: dict[str, str] = Field(default={}, max_length=1)
    # Le prénom du courtier, tel que les textes écrits par le code le nomment aux visiteurs et aux partenaires (« <prénom> a
    # bien reçu votre demande… », « <prénom> vous transmet la fiche… ») ; sans lui, « notre courtier ».
    courtier: str | None = Field(default=None, pattern=r"^[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ'’ -]{0,39}$")
    # Les gestionnaires se tutoient : rappelé dans le Contexte de chaque tour, même si l'historique les vouvoie.
    tutoiement: bool = False

    @field_validator("sites", "principal")
    @classmethod
    def adresses(cls, v: dict[str, str]) -> dict[str, str]:
        for prefixe, url in v.items():
            if not re.fullmatch(r"[a-z0-9-]{1,40}", prefixe) or not re.fullmatch(r"https://[a-z0-9.-]+", url):
                raise ValueError("sites, principal : {nom du site: adresse https du site}")
        return v

    @model_validator(mode="after")
    def publics_connus(self):
        if inconnus := [p for p in self.publics if p not in self.sites]:
            raise ValueError(f"publics : des préfixes de sites, inconnus : {', '.join(inconnus)}")
        if communs := set(self.principal) & set(self.sites):
            raise ValueError(f"principal : un nom déjà pris par sites : {', '.join(communs)}")
        return self


class Remplacement(Strict):
    """Un remplacement au point d'envoi (noyau/typographie.py, Remplaceur) : chaque texte qui part sur WhatsApp, une
    légende, une variable de modèle, une liste, et ce que dit la voix. Un motif (expression régulière, sans casse) et
    ce qui le remplace (vide : il disparaît)."""

    motif: str = Field(min_length=1, max_length=300)
    par: str = Field(default="", max_length=80)

    @field_validator("motif")
    @classmethod
    def motif_lisible(cls, v: str) -> str:
        return motif_valide(v)


class Historique(Strict):
    """Ce que l'agent relit de la conversation (D1) : les derniers tours, et l'oubli après une inactivité."""

    tours: int = Field(default=12, ge=2, le=100)
    # Après tant d'heures sans message, la conversation repart à neuf (ce qui s'y disait rejoint le fil) ; vide : jamais.
    inactivite: float | None = Field(default=None, gt=0, le=24 * 30)


class Memoire(Strict):
    """La mémoire durable de l'agent (D2). Sans outils : celle d'Agno, qu'il tient lui-même, toute relue à chaque tour.
    Avec : retenir, oublier, souvenirs (noyau/memoire.py), et à chaque tour les souvenirs utiles, tous jusqu'à `montres`."""

    outils: bool = False
    montres: int = Field(default=40, ge=5, le=200)


class Oral(Strict):
    """Ce qu'un vocal dit (noyau/oral.py, D3)."""

    # La consigne de la réécriture pour l'oral, propre au client ; vide : celle du noyau.
    consignes: str = Field(default="", max_length=12000)
    # Une référence (de bien, de dossier) ne se lit jamais : elle part par écrit après le vocal. Un motif (expression régulière).
    references: str | None = Field(default=None, max_length=300)

    @field_validator("consignes")
    @classmethod
    def sans_artefacts(cls, v: str) -> str:
        if re.search(r"[\u2014\u2013\u00b7]", v):
            raise ValueError("Pas de tiret long ni de point médian.")
        return v

    @field_validator("references")
    @classmethod
    def motif_references(cls, v: str | None) -> str | None:
        return motif_valide(v) if v else v


class Photos(Strict):
    """Les photos reçues (D6) : combien le modèle en voit par tour, et leur description, gardée pour les tours suivants."""

    max: int = Field(default=5, ge=1, le=10)
    # Le petit modèle (Modeles.juge) dit en une ligne ce qu'on voit sur chacune ; la ligne reste dans l'historique.
    decrire: bool = False
    # Ce qu'il doit y regarder, propre au client ; vide : la consigne du noyau.
    consigne: str = Field(default="", max_length=3000)


class ReglageRappels(Strict):
    """Les rappels (D4) : l'heure d'un rappel demandé sans heure (vide : minuit), et les rappels prévus dans le Contexte."""

    heure: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    contexte: bool = False


def motif_valide(v: str) -> str:
    """Une expression régulière lisible, qui ne trouve jamais une chaîne vide (elle remplacerait partout)."""
    try:
        r = re.compile(v, re.I)
    except re.error as e:
        raise ValueError(f"motif illisible : {e}") from None
    if r.fullmatch(""):
        raise ValueError("un motif qui ne trouve jamais une chaîne vide")
    return v


DOMAINE = re.compile(r"[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}")


class Region(Strict):
    """Les portails d'une région : les grands (la recherche simple), puis les autres (la recherche avancée)."""

    nom: str = Field(min_length=1, max_length=60)
    simple: tuple[str, ...] = Field(min_length=1, max_length=6)
    autres: tuple[str, ...] = Field(default=(), max_length=10)

    @field_validator("simple", "autres")
    @classmethod
    def domaines(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        if any(not DOMAINE.fullmatch(d) for d in v):
            raise ValueError("des domaines de portails (homegate.ch)")
        return v


class Marche(Strict):
    """Le marché du client (lot 7.5) : ses régions et leurs portails, celle par défaut."""

    regions: dict[str, Region] = Field(min_length=1)
    defaut: str

    @model_validator(mode="after")
    def defaut_connu(self):
        if any(not re.fullmatch(r"[a-z0-9-]{1,30}", k) for k in self.regions):
            raise ValueError("regions : {identifiant: région}")
        if self.defaut not in self.regions:
            raise ValueError("defaut : une des régions")
        return self


class Config(Strict):
    version: int = VERSION
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,62}$")
    nom_agent: str = Field(min_length=1, max_length=40)
    entreprise: str = Field(min_length=1, max_length=120)
    zone: Literal["suisse", "europe", "etats-unis", "client"]
    langue: str = Field(default="fr", pattern=r"^[a-z]{2}$")
    fuseau: str = "Europe/Zurich"
    ton: str = Field(default="chaleureux et professionnel", max_length=200)
    consignes: str = Field(default="", max_length=8000)
    modeles: Modeles = Modeles()
    # Facultatif : un agent branché seulement par API (un logiciel, noyau/api.py) n'a pas de numéro.
    # Une configuration sans WhatsApp demande une image qui la connaît (SANS_WHATSAPP_SCHEMA).
    whatsapp: WhatsApp | None = None
    voix: Voix = Voix()
    # Les modèles Meta du client, par usage (« rappel », « relance »).
    modeles_meta: dict[str, ModeleMeta] = {}
    # Un 👀 sur le message quand un tour traîne, retiré à la réponse.
    reactions: bool = True
    # Les réactions d'humeur de l'agent sans rôles, et par défaut de ses rôles (Role.humeur) (M7).
    humeur: Literal["aucune", "complice", "sobre"] = "aucune"
    # Ce qui part sur WhatsApp ou se dit passe par ces remplacements (un nom qui ne doit jamais sortir).
    remplacements: tuple[Remplacement, ...] = Field(default=(), max_length=20)
    historique: Historique = Historique()
    memoire: Memoire = Memoire()
    oral: Oral = Oral()
    photos: Photos = Photos()
    rappels: ReglageRappels = ReglageRappels()
    # Un vocal non transcrit, une position, un autocollant, une fiche contact : passés au modèle, qui répond lui-même,
    # au lieu d'une phrase fixe (M4, D13).
    pieces_au_modele: bool = False
    # Une réponse qui s'arrête au milieu d'une phrase (« Oui je transmets votre ») est réécrite par un dernier appel (M2).
    reprendre_coupees: bool = False
    # Le fil (noyau/fil.py) : ce qui sort de l'historique se fond dans un résumé relu à chaque tour.
    fil: bool = False
    # Le mot du matin (packs/immobilier/bonjour.py) : chaque jour à cette heure (« 08:00 », heure du client), un
    # message d'encouragement plein de bonne humeur à chaque gestionnaire, qui peut l'arrêter ou changer l'heure.
    bonjour: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    # Le métier de l'agent ; il borne les packs qu'on peut lui activer.
    metier: Literal["general", "immobilier"] = "general"
    # Les packs actifs (aujourd'hui : « immobilier »).
    outils: tuple[Literal["immobilier"], ...] = ()
    # Le catalogue du pack immobilier : « demo:<nom> » ou un flux https de l'agence.
    catalogue: str | None = Field(default=None, pattern=r"^(demo:[a-z0-9-]{1,60}|https://\S{4,500})$")
    # Les rôles des personnes (gestionnaires, partenaires, visiteurs) ; sans eux, un seul agent pour tous.
    roles: Roles | None = None
    # La gestion du site du client, pour les outils qui agissent en son nom.
    gestion: Gestion | None = None
    # Les portails de son marché (outils du marché).
    marche: Marche | None = None

    @model_validator(mode="before")
    @classmethod
    def metier_par_defaut(cls, d):
        # Une configuration d'avant le métier : celui de ses packs.
        if isinstance(d, dict) and "metier" not in d and "immobilier" in (d.get("outils") or ()):
            d = {**d, "metier": "immobilier"}
        return d

    @model_validator(mode="after")
    def outils_du_metier(self):
        hors = [o for o in self.outils if o not in METIERS[self.metier]]
        for r in self.les_roles().values():
            hors += [o for o in r.outils if o != "rappels" and o not in OUTILS_DES_ROLES[self.metier] and o not in hors]
        if hors:
            raise ValueError(f"Ces outils ne vont pas avec ce métier : {', '.join(hors)}.")
        # Les outils qui agissent au nom d'un compte de gestion ne vont qu'aux gestionnaires.
        for nom, r in self.les_roles().items():
            if nom != "gestionnaire" and (pris := [o for o in r.outils if o in OUTILS_GESTIONNAIRE]):
                raise ValueError(f"Ces outils sont ceux des gestionnaires, pas du rôle {nom} : {', '.join(pris)}.")
        return self

    def les_roles(self) -> dict[str, Role]:
        """Les rôles réglés : {nom: rôle}, vide sans rôles."""
        if self.roles is None:
            return {}
        return {n: r for n in ("gestionnaire", "partenaire", "visiteur") if (r := getattr(self.roles, n)) is not None}

    @field_validator("fuseau")
    @classmethod
    def fuseau_connu(cls, v: str) -> str:
        """Un fuseau faux arrêterait le conteneur au démarrage : refusé ici, avec un message clair."""
        from zoneinfo import ZoneInfo

        try:
            ZoneInfo(v)
        except (ValueError, KeyError, OSError):
            raise ValueError("fuseau inconnu : par exemple Europe/Zurich") from None
        return v

    @field_validator("version")
    @classmethod
    def version_connue(cls, v: int) -> int:
        if v != VERSION:
            raise ValueError(f"version de configuration {v} inconnue (attendue : {VERSION})")
        return v

    @field_validator("consignes", "ton", "nom_agent", "entreprise")
    @classmethod
    def sans_artefacts(cls, v: str) -> str:
        if re.search(r"[\u2014\u2013\u00b7]", v):
            raise ValueError("Pas de tiret long ni de point médian.")
        return v


def manques(conf: Config) -> list[str]:
    """Ce qui empêche une configuration valide de servir (l'atelier et le pilotage la refusent)."""
    m = []
    if ("immobilier" in conf.outils or any("immobilier" in r.outils for r in conf.les_roles().values())) and not conf.catalogue:
        m.append("le pack immobilier attend son catalogue (réglage de MEGGA)")
    if any(o in OUTILS_GESTION for r in conf.les_roles().values() for o in r.outils) and conf.gestion is None:
        m.append("les outils d'annonces, de partenaires et de visiteurs attendent la gestion du site (réglage de MEGGA)")
    if any("marche" in r.outils for r in conf.les_roles().values()) and conf.marche is None:
        m.append("les outils du marché attendent les portails de ses régions (réglage de MEGGA)")
    return m


def lire(source: str | Path | dict) -> Config:
    """Une configuration depuis un fichier YAML ou JSON, un texte JSON ou un dict."""
    if isinstance(source, dict):
        return Config.model_validate(source)
    texte = str(source)
    if texte.lstrip().startswith("{"):
        return Config.model_validate(json.loads(texte))
    chemin = Path(texte)
    donnees = yaml.safe_load(chemin.read_text(encoding="utf-8"))
    if not isinstance(donnees, dict):
        raise ValueError(f"{chemin} : une configuration est un objet")
    return Config.model_validate(donnees)


if __name__ == "__main__":  # python -m noyau.config clients/x.yaml : la configuration validée, en JSON
    import sys

    print(json.dumps(lire(sys.argv[1]).model_dump(), ensure_ascii=False))
