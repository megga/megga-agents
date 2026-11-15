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
ZONES = ("suisse", "europe", "etats-unis", "client")
# Les métiers, et les packs d'outils que chacun permet.
METIERS: dict[str, tuple[str, ...]] = {"general": (), "immobilier": ("immobilier",)}


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Modeles(Strict):
    """Le modèle principal, celui qui prend le relais s'il échoue, et celui qui réécrit pour l'oral."""

    principal: str = "claude-sonnet-5-5"
    secours: str | None = "deepseek-v4-pro"
    # La réécriture d'une réponse pour un vocal ; vide : le secours, sinon le principal.
    oral: str | None = None


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
    whatsapp: WhatsApp
    voix: Voix = Voix()
    # Les modèles Meta du client, par usage (« rappel », « relance »).
    modeles_meta: dict[str, ModeleMeta] = {}
    # Un 👀 sur le message quand un tour traîne, retiré à la réponse.
    reactions: bool = True
    # Le métier de l'agent ; il borne les packs qu'on peut lui activer.
    metier: Literal["general", "immobilier"] = "general"
    # Les packs actifs (aujourd'hui : « immobilier »).
    outils: tuple[Literal["immobilier"], ...] = ()
    # Le catalogue du pack immobilier : « demo:<nom> » ou un flux https de l'agence.
    catalogue: str | None = Field(default=None, pattern=r"^(demo:[a-z0-9-]{1,60}|https://\S{4,500})$")

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
        if hors:
            raise ValueError(f"Ces outils ne vont pas avec ce métier : {', '.join(hors)}.")
        return self

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
    if "immobilier" in conf.outils and not conf.catalogue:
        m.append("le pack immobilier attend son catalogue (réglage de MEGGA)")
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
