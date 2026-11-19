"""Le suivi d'un agent : ce que la console montre de lui, calculé dans son propre conteneur.

Les volumes et les modèles viennent des tours d'Agno ; les échecs autour d'un tour et la
voix, du journal du noyau ; les conversations, du fil. Les coûts ne se calculent pas ici :
les tarifs sont ceux de MEGGA, dans l'atelier.
"""

from __future__ import annotations

import re

from .config import Config
from .garde import masquer_secrets

# Un numéro WhatsApp, ou une personne d'un logiciel par API (noyau/api.py).
PERSONNE = re.compile(r"^(\+?\d{6,20}|api:[a-z0-9][a-z0-9-]{0,19}:(?=[^:]*[A-Za-z])[A-Za-z0-9._-]{1,40})$")


def entree_hors_cache(m: dict) -> int:
    """Les jetons d'entrée payés au plein tarif, hors cache, quel que soit le fournisseur.

    Chez Anthropic (Claude), les jetons d'entrée excluent déjà le cache ; chez les
    fournisseurs de type OpenAI (DeepSeek), ils l'incluent (models/openai/chat.py d'Agno).
    """
    entree = int(m.get("input_tokens") or 0)
    if "claude" in str(m.get("id") or "").lower() or "anthropic" in str(m.get("provider") or "").lower():
        return entree
    return max(0, entree - int(m.get("cache_read_tokens") or 0))


def delai(journal: dict[str, dict], genre: str) -> dict:
    """Le temps moyen (secondes) noté au journal sous ce genre, depuis l'envoi du message de la personne."""
    e = journal.get(genre) or {}
    n = int(e.get("nombre", 0))
    return {"nombre": n, "moyenne": round(float(e.get("quantite", 0)) / n, 1) if n else None}


def _compter(modeles: dict[str, dict], tour: dict) -> set:
    """Ajoute à `modeles` les jetons de ce tour, par modèle ; rend les modèles qu'il a employés."""
    vus = set()
    for m in tour["modeles"]:
        ident = m.get("id") or "?"
        e = modeles.setdefault(ident, {"fournisseur": m.get("provider"), "tours": 0, "entree": 0, "sortie": 0,
                                       "cache_lecture": 0, "cache_ecriture": 0})
        e["entree"] += entree_hors_cache(m)
        e["sortie"] += int(m.get("output_tokens") or 0)
        e["cache_lecture"] += int(m.get("cache_read_tokens") or 0)
        e["cache_ecriture"] += int(m.get("cache_write_tokens") or 0)
        vus.add(ident)
    for ident in vus:
        modeles[ident]["tours"] += 1
    return vus


def resumer(conf: Config, tours: list[dict], journal: dict[str, dict], rappels_en_attente: int, depuis: float) -> dict:
    """`modeles` : tous les jetons du client, ceux de ses collègues compris (c'est ce qui se facture). `echanges` : la
    part des collègues (noyau/echanges.py), par collègue, dans la même forme, pour en lire le coût à part."""
    modeles: dict[str, dict] = {}
    collegues: dict[str, dict] = {}
    secours = 0
    reponses = [t for t in tours if t.get("collegue")]  # les réponses des collègues à l'agent
    tours = [t for t in tours if not t.get("collegue")]  # les tours des personnes
    for t in tours:
        vus = _compter(modeles, t)
        if conf.modeles.secours and conf.modeles.secours in vus:
            secours += 1
    for t in reponses:
        _compter(modeles, t)
        e = collegues.setdefault(t["collegue"], {"reponses": 0, "modeles": {}})
        e["reponses"] += 1
        _compter(e["modeles"], t)
    return {
        "depuis": depuis,
        "tours": len(tours),
        # Une seule source pour les échecs : le noyau, qui voit aussi ceux qu'Agno n'enregistre pas.
        "tours_en_echec": int((journal.get("tour_echec") or {}).get("nombre", 0)),
        "secours": secours,
        "personnes": len({t["personne"] for t in tours if t["personne"]}),
        # Les tours venus d'un logiciel par API, comptés aussi dans « tours » (et dans les coûts).
        "tours_api": sum(1 for t in tours if str(t["personne"] or "").startswith("api:")),
        "derniere_activite": max((t["quand"] for t in tours), default=None),
        "modeles": modeles,
        "journal": journal,
        # Ce que la personne a attendu (19.11.2026) : jusqu'aux coches bleues, jusqu'à la réponse, et les réponses lentes.
        "delais": {"lecture": delai(journal, "delai_lecture"), "reponse": delai(journal, "delai_reponse"),
                   "lentes": int((journal.get("reponse_lente") or {}).get("nombre", 0))},
        "rappels_en_attente": rappels_en_attente,
        # Les échanges entre l'agent et ses collègues : combien de réponses, et ce qu'elles ont coûté, par collègue.
        "echanges": {"reponses": len(reponses), "collegues": collegues,
                     "refuses": int((journal.get("echange_boucle") or {}).get("nombre", 0))
                                + int((journal.get("echange_plafond") or {}).get("nombre", 0)),
                     "hors_delai": int((journal.get("echange_hors_delai") or {}).get("nombre", 0)),
                     "en_echec": int((journal.get("echange_echec") or {}).get("nombre", 0))},
    }


def message_lisible(m: dict) -> dict:
    """Un message tel que la console le montre : les clés, jetons et adresses de base masqués, même dits par la personne."""
    return {**m, "texte": masquer_secrets(m.get("texte") or "")}
