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
from pydantic import BaseModel, ConfigDict, Field, field_validator

VERSION = 1
ZONES = ("suisse", "europe", "etats-unis", "client")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Modeles(Strict):
    """Le modèle principal et celui qui prend le relais s'il échoue."""

    principal: str = "claude-sonnet-5-5"
    secours: str | None = "deepseek-v4-pro"


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
    # Les outils actifs : noms de packs ou d'outils du noyau. Vide au lot 1.
    outils: tuple[str, ...] = ()

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
            raise ValueError("ni tiret long ni point médian dans la configuration")
        return v


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
