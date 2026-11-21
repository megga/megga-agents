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


DELAIS = ("delai_lecture", "delai_reponse")


def centile(valeurs: list[float], p: float) -> float | None:
    """Le centile p (0 à 100) au rang le plus proche : la valeur sous laquelle tombent p % des cas."""
    if not valeurs:
        return None
    v = sorted(valeurs)
    return round(v[max(0, min(len(v) - 1, -(-len(v) * p // 100) - 1))], 1)


def delai(journal: dict[str, dict], genre: str, valeurs: list[float] | None = None) -> dict:
    """Le temps (secondes) noté au journal sous ce genre, depuis l'envoi du message de la personne : la moyenne, et
    avec les valeurs, la médiane et le cas lent (95 % des cas en dessous)."""
    e = journal.get(genre) or {}
    n = int(e.get("nombre", 0))
    sortie = {"nombre": n, "moyenne": round(float(e.get("quantite", 0)) / n, 1) if n else None}
    if valeurs is not None:
        sortie |= {"mediane": centile(valeurs, 50), "p95": centile(valeurs, 95)}
    return sortie


def outils(tours: list[dict]) -> dict[str, dict]:
    """Les outils appelés : combien de fois, combien d'échecs, la durée totale de ceux qui l'ont dite (secondes)."""
    sortie: dict[str, dict] = {}
    for t in tours:
        for o in t.get("outils") or []:
            e = sortie.setdefault(o["nom"], {"appels": 0, "echecs": 0, "duree": 0.0, "mesures": 0})
            e["appels"] += 1
            e["echecs"] += int(o["erreur"])
            if o.get("duree") is not None:
                e["duree"] = round(e["duree"] + o["duree"], 3)
                e["mesures"] += 1
    return sortie


def resumer(conf: Config, tours: list[dict], journal: dict[str, dict], rappels_en_attente: int, depuis: float,
            valeurs: dict[str, list[float]] | None = None) -> dict:
    """`valeurs` : les délais notés un à un (Journal.valeurs), pour la médiane et les cas lents."""
    valeurs = valeurs or {}
    modeles: dict[str, dict] = {}
    secours = 0
    for t in tours:
        vus = set()
        for m in t["modeles"]:
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
        if conf.modeles.secours and conf.modeles.secours in vus:
            secours += 1
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
        "delais": {"lecture": delai(journal, "delai_lecture", valeurs.get("delai_lecture")),
                   "reponse": delai(journal, "delai_reponse", valeurs.get("delai_reponse")),
                   "lentes": int((journal.get("reponse_lente") or {}).get("nombre", 0))},
        # Les outils (20.11.2026) : le nom, les appels, les échecs, la durée ; ni arguments ni résultats.
        "outils": outils(tours),
        "rappels_en_attente": rappels_en_attente,
    }


JOUR = 86400
# Le relevé chiffré (20.11.2026) : aujourd'hui et hier par défaut (en UTC, les clients sont partout) ; deux semaines au
# plus, pour rattraper les jours manqués après une absence (porte/src/releves.js, JOURS_RELEVE_MAX).
JOURS_RELEVE = 14


def jours_utc(nombre: int, maintenant: float) -> list[tuple[str, float, float]]:
    """Les `nombre` derniers jours UTC, du plus ancien à aujourd'hui : (AAAA-MM-JJ, début, fin)."""
    from datetime import datetime, timezone

    aujourdhui = int(maintenant // JOUR) * JOUR
    return [(datetime.fromtimestamp(d, timezone.utc).strftime("%Y-%m-%d"), float(d), float(d + JOUR))
            for d in range(aujourdhui - (nombre - 1) * JOUR, aujourdhui + 1, JOUR)]


def releve(conf: Config, tours: list[dict], journaux: dict[str, dict], jours: list[tuple[str, float, float]],
           rappels_en_attente: int, image: dict, valeurs: dict[str, dict[str, list[float]]] | None = None) -> dict:
    """Le relevé chiffré de l'agent, jour par jour : les chiffres du suivi, jamais un texte, un nom ni un numéro.

    La porte le lit à intervalle fixe et le range dans son annuaire : la console de MEGGA suit tous les clients
    d'un coup sans réveiller aucun conteneur. `journaux` : les totaux du journal de chaque jour.
    """
    par_jour = {}
    for jour, debut, fin in jours:
        r = resumer(conf, [t for t in tours if debut <= (t["quand"] or 0) < fin], journaux.get(jour) or {}, 0, debut,
                    (valeurs or {}).get(jour))
        for k in ("depuis", "rappels_en_attente", "derniere_activite"):
            r.pop(k)
        par_jour[jour] = r
    return {"forme": 1, "image": {"version": image.get("version"), "revision": image.get("revision")},
            "rappels_en_attente": rappels_en_attente,
            "derniere_activite": max((t["quand"] for t in tours if t["quand"]), default=None), "jours": par_jour}


def message_lisible(m: dict) -> dict:
    """Un message tel que la console le montre : les clés, jetons et adresses de base masqués, même dits par la personne."""
    return {**m, "texte": masquer_secrets(m.get("texte") or "")}
