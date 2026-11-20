"""Les coûts d'un agent, d'après ses volumes et les tarifs de MEGGA.

Les tarifs sont ceux que MEGGA paie (modèles, voix) : ils se règlent dans l'atelier, ne
s'inventent pas, et ne se montrent qu'à MEGGA. Sans tarif pour un modèle, son coût n'est
pas compté et il est signalé.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TarifModele(Strict):
    """Par million de jetons."""

    entree: float = Field(ge=0)
    sortie: float = Field(ge=0)
    cache_lecture: float = Field(default=0, ge=0)
    cache_ecriture: float = Field(default=0, ge=0)


class Tarifs(Strict):
    devise: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    modeles: dict[str, TarifModele] = {}
    # La voix d'ElevenLabs, pour 1000 caractères dits ; l'écoute, par vocal entendu.
    voix_par_1000_caracteres: float | None = Field(default=None, ge=0)
    par_vocal_entendu: float | None = Field(default=None, ge=0)


def _jetons(v: dict, t: TarifModele) -> float:
    return (v.get("entree", 0) * t.entree + v.get("sortie", 0) * t.sortie
            + v.get("cache_lecture", 0) * t.cache_lecture + v.get("cache_ecriture", 0) * t.cache_ecriture) / 1e6


def couts(activite: dict, tarifs: Tarifs) -> dict:
    """Les coûts de la période, poste par poste ; ce qui n'a pas de tarif est listé à part. `collegues` : la part de
    chaque collègue de l'agent (noyau/echanges.py), déjà comprise dans les postes des modèles et dans le total."""
    postes: dict[str, float] = {}
    sans_tarif: list[str] = []
    for ident, v in (activite.get("modeles") or {}).items():
        t = tarifs.modeles.get(ident)
        if t is None:
            if v.get("entree") or v.get("sortie"):
                sans_tarif.append(ident)
            continue
        postes[ident] = _jetons(v, t)
    collegues = {nom: round(sum(_jetons(v, tarifs.modeles[m]) for m, v in (e.get("modeles") or {}).items() if m in tarifs.modeles), 4)
                 for nom, e in ((activite.get("echanges") or {}).get("collegues") or {}).items()}
    journal = activite.get("journal") or {}
    caracteres = (journal.get("voix_caracteres") or {}).get("quantite", 0)
    if caracteres:
        if tarifs.voix_par_1000_caracteres is None:
            sans_tarif.append("voix")
        else:
            postes["voix"] = caracteres / 1000 * tarifs.voix_par_1000_caracteres
    vocaux = (journal.get("vocal_entendu") or {}).get("nombre", 0)
    if vocaux:
        if tarifs.par_vocal_entendu is None:
            sans_tarif.append("ecoute")
        else:
            postes["ecoute"] = vocaux * tarifs.par_vocal_entendu
    return {
        "devise": tarifs.devise,
        "postes": {k: round(v, 4) for k, v in postes.items()},
        "total": round(sum(postes.values()), 4),
        "sans_tarif": sans_tarif,
        "collegues": collegues,
    }
