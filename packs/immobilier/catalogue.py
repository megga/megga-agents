"""Le catalogue des biens d'une agence.

Source, dans la configuration du client (`catalogue`) :
  « demo:megga-estates »   un fichier livré avec l'image (packs/immobilier/demo/)
  « https://… »            un flux JSON de l'agence, relu au plus toutes les 15 minutes
Format : une liste d'objets `Bien` (ou {"biens": [...]}). Un bien invalide est écarté
et signalé dans les journaux ; il ne bloque pas les autres.
"""

from __future__ import annotations

import json
import logging
import time
import unicodedata
from pathlib import Path
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

log = logging.getLogger("megga")
DEMO = Path(__file__).parent / "demo"
RAFRAICHIR_S = 15 * 60
MAX_BIENS = 5000


class Bien(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ref: str = Field(min_length=1, max_length=40)
    titre: str = Field(min_length=1, max_length=200)
    type: Literal["appartement", "maison", "villa", "chalet", "attique", "terrain", "commercial", "autre"] = "autre"
    transaction: Literal["vente", "location"]
    prix: float | None = Field(default=None, ge=0)
    devise: str = Field(default="CHF", pattern=r"^[A-Z]{3}$")
    periode: Literal["mois", "semaine", "nuit"] | None = None
    commune: str = Field(min_length=1, max_length=80)
    region: str = ""
    pays: str = "CH"
    chambres: int | None = Field(default=None, ge=0)
    salles_de_bain: int | None = Field(default=None, ge=0)
    surface: float | None = Field(default=None, ge=0)
    terrain: float | None = Field(default=None, ge=0)
    atouts: list[str] = []
    description: str = Field(default="", max_length=4000)
    photos: list[str] = []
    lien: str | None = None
    disponible: bool = True


def sans_accents(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(t).lower()) if unicodedata.category(c) != "Mn")


def lire_biens(donnees) -> list[Bien]:
    lignes = donnees.get("biens", []) if isinstance(donnees, dict) else donnees
    if not isinstance(lignes, list):
        raise ValueError("catalogue : une liste de biens est attendue")
    biens = []
    for brut in lignes[:MAX_BIENS]:
        if not isinstance(brut, dict):  # une entrée qui n'est pas un bien est écartée, pas tout le flux
            log.warning("entrée du catalogue écartée : pas un objet")
            continue
        try:
            biens.append(Bien.model_validate(brut))
        except ValidationError as e:
            log.warning("bien écarté (%s) : %s", str(brut.get("ref", "?"))[:40], str(e).splitlines()[0][:200])
    return biens


class Catalogue:
    def __init__(self, source: str, client: httpx.Client | None = None):
        self.source = source
        self._client = client
        self._biens: list[Bien] = []
        self._lu = 0.0
        if source.startswith("demo:"):
            nom = source[5:]
            if not nom.replace("-", "").isalnum():
                raise ValueError("catalogue de démo inconnu")
            self._biens = lire_biens(json.loads((DEMO / f"{nom}.json").read_text(encoding="utf-8")))
            self._lu = float("inf")
        elif not source.startswith("https://"):
            raise ValueError("catalogue : « demo:<nom> » ou une adresse https")

    def biens(self) -> list[Bien]:
        if time.time() - self._lu > RAFRAICHIR_S:
            try:
                if self._client is None:  # un seul client, gardé, au lieu d'un nouveau à chaque relecture
                    self._client = httpx.Client(timeout=20)
                r = self._client.get(self.source)
                r.raise_for_status()
                self._biens = lire_biens(r.json())
                self._lu = time.time()
            except Exception as e:  # on garde la dernière version connue
                log.error("catalogue illisible : %s", str(e)[:200])
                self._lu = time.time() - RAFRAICHIR_S + 60  # nouvel essai dans une minute
        return [b for b in self._biens if b.disponible]

    def bien(self, ref: str) -> Bien | None:
        ref = str(ref).strip().lower()
        return next((b for b in self.biens() if b.ref.lower() == ref), None)

    def chercher(self, transaction=None, types=None, communes=None, budget_min=None, budget_max=None,
                 chambres_min=None, surface_min=None, mots=None) -> list[Bien]:
        communes = [sans_accents(c.strip()) for c in (communes or []) if c.strip()]
        types = [t.strip().lower() for t in (types or []) if t.strip()]
        mots = [sans_accents(m) for m in (mots or "").split() if len(m) > 2]
        resultat = []
        for b in self.biens():
            if transaction and b.transaction != transaction:
                continue
            if types and b.type not in types:
                continue
            lieu = sans_accents(f"{b.commune} {b.region}")
            if communes and not any(c in lieu for c in communes):
                continue
            # Un bien « prix sur demande » reste dans les résultats d'une recherche par budget.
            if budget_min is not None and b.prix is not None and b.prix < budget_min:
                continue
            if budget_max is not None and b.prix is not None and b.prix > budget_max:
                continue
            if chambres_min is not None and (b.chambres or 0) < chambres_min:
                continue
            if surface_min is not None and (b.surface or 0) < surface_min:
                continue
            if mots:
                texte = sans_accents(" ".join([b.titre, b.description, " ".join(b.atouts), b.commune]))
                if not all(m in texte for m in mots):
                    continue
            resultat.append(b)
        return resultat
