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
METIERS: dict[str, tuple[str, ...]] = {"general": ("connaissances",), "immobilier": ("immobilier", "connaissances")}
# Les groupes d'outils qu'un rôle peut recevoir, par métier (en plus des rappels).
OUTILS_DES_ROLES: dict[str, tuple[str, ...]] = {"general": ("connaissances",),
                                                "immobilier": ("immobilier", "annonces", "partenaires", "visiteurs",
                                                               "vitrine", "accueil", "marche", "travail", "connaissances")}
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
    # (relecture du 16.11.2026, I16).
    oral: str | None = None

    def petit(self) -> str:
        """Le modèle de l'oral et du fil."""
        if self.oral:
            return self.oral
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


REGLE_OUTIL = Literal["approbation", "interdit"]
NOM_OUTIL = re.compile(r"^[a-z][a-z0-9_]{1,59}$")
APPROBATIONS_MAX = 60


def _approbations(v: dict[str, str]) -> dict[str, str]:
    """{nom d'un outil: « approbation » ou « interdit »} ; un outil absent se fait sans accord (noyau/approbations.py)."""
    if len(v) > APPROBATIONS_MAX:
        raise ValueError(f"approbations : {APPROBATIONS_MAX} outils au plus")
    for nom in v:
        if not NOM_OUTIL.fullmatch(nom):
            raise ValueError("approbations : le nom d'un outil, en minuscules (chercher_biens, envoyer_a_un_contact…)")
    return v


class Role(Strict):
    """Ce qu'un rôle reçoit en plus des consignes de l'agent : ses consignes à lui, et ses outils.

    `accueil` : le premier message à une personne de ce rôle, mot pour mot, par langue ({"fr": …, "en": …}) ;
    envoyé par le noyau (noyau/accueil.py), seule retouche permise : son prénom après le premier mot.
    `approbations` : pour les personnes de ce rôle, par-dessus celles de la configuration (noyau/approbations.py)."""

    consignes: str = Field(default="", max_length=12000)
    outils: tuple[Literal["rappels", "immobilier", "annonces", "partenaires", "visiteurs", "vitrine", "accueil", "marche", "travail",
                         "connaissances"], ...] = ("rappels",)
    accueil: dict[str, str] = {}
    approbations: dict[str, REGLE_OUTIL] = {}

    _approbations = field_validator("approbations")(classmethod(lambda cls, v: _approbations(v)))

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

    @field_validator("sites")
    @classmethod
    def adresses(cls, v: dict[str, str]) -> dict[str, str]:
        for prefixe, url in v.items():
            if not re.fullmatch(r"[a-z0-9-]{1,40}", prefixe) or not re.fullmatch(r"https://[a-z0-9.-]+", url):
                raise ValueError("sites : {préfixe de l'identifiant d'un bien: adresse https du site}")
        return v

    @model_validator(mode="after")
    def publics_connus(self):
        if inconnus := [p for p in self.publics if p not in self.sites]:
            raise ValueError(f"publics : des préfixes de sites, inconnus : {', '.join(inconnus)}")
        return self


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
    # Le fil (noyau/fil.py) : ce qui sort de l'historique se fond dans un résumé relu à chaque tour.
    fil: bool = False
    # Le métier de l'agent ; il borne les packs qu'on peut lui activer.
    metier: Literal["general", "immobilier"] = "general"
    # Les packs actifs : « immobilier », « connaissances » (la base de documents du client, noyau/connaissances.py).
    outils: tuple[Literal["immobilier", "connaissances"], ...] = ()
    # Le catalogue du pack immobilier : « demo:<nom> » ou un flux https de l'agence.
    catalogue: str | None = Field(default=None, pattern=r"^(demo:[a-z0-9-]{1,60}|https://\S{4,500})$")
    # Les rôles des personnes (gestionnaires, partenaires, visiteurs) ; sans eux, un seul agent pour tous.
    roles: Roles | None = None
    # La gestion du site du client, pour les outils qui agissent en son nom.
    gestion: Gestion | None = None
    # Les portails de son marché (outils du marché).
    marche: Marche | None = None
    # Les outils qui attendent l'accord d'un gestionnaire, ou qui sont interdits (noyau/approbations.py).
    approbations: dict[str, REGLE_OUTIL] = {}
    # Le transfert vers un humain (noyau/reprises.py) : l'agent peut confier une conversation à l'équipe.
    transfert: bool = False

    _approbations = field_validator("approbations")(classmethod(lambda cls, v: _approbations(v)))

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

    @model_validator(mode="after")
    def transfert_a_l_equipe(self):
        if self.transfert and "gestionnaire" not in self.les_roles():
            raise ValueError("Le transfert vers un humain demande le rôle gestionnaire : c'est à l'équipe que l'agent passe la main.")
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
