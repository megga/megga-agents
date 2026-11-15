"""Le suivi d'un agent : ce que la console montre de lui, calculé dans son propre conteneur.

Les volumes et les modèles viennent des tours d'Agno ; les échecs autour d'un tour et la
voix, du journal du noyau. Les coûts ne se calculent pas ici : les tarifs sont ceux de
MEGGA, dans l'atelier.
"""

from __future__ import annotations

import re

from .config import Config
from .garde import masquer_secrets

PERSONNE = re.compile(r"^\+?\d{6,20}$")


def resumer(conf: Config, tours: list[dict], journal: dict[str, dict], rappels_en_attente: int, depuis: float) -> dict:
    modeles: dict[str, dict] = {}
    secours = 0
    for t in tours:
        vus = set()
        for m in t["modeles"]:
            ident = m.get("id") or "?"
            e = modeles.setdefault(ident, {"fournisseur": m.get("provider"), "tours": 0, "entree": 0, "sortie": 0,
                                           "cache_lecture": 0, "cache_ecriture": 0})
            e["entree"] += int(m.get("input_tokens") or 0)
            e["sortie"] += int(m.get("output_tokens") or 0)
            e["cache_lecture"] += int(m.get("cache_read_tokens") or 0)
            e["cache_ecriture"] += int(m.get("cache_write_tokens") or 0)
            vus.add(ident)
        for ident in vus:
            modeles[ident]["tours"] += 1
        if conf.modeles.secours and conf.modeles.secours in vus:
            secours += 1
    return {
        "depuis": depuis,
        "tours": len(tours),
        "tours_en_echec": sum(1 for t in tours if t["statut"] not in ("COMPLETED", None)),
        "secours": secours,
        "personnes": len({t["personne"] for t in tours if t["personne"]}),
        "derniere_activite": max((t["quand"] for t in tours), default=None),
        "modeles": modeles,
        "journal": journal,
        "rappels_en_attente": rappels_en_attente,
    }


def echange_lisible(e: dict) -> dict:
    """Un échange tel que la console le montre : les clés, jetons et adresses de base masqués, même dits par la personne."""
    return {**e, "entendu": masquer_secrets(e["entendu"]), "reponse": masquer_secrets(e["reponse"])}
