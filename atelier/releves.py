"""Le relevé chiffré de tous les agents, pour la console de MEGGA (20.11.2026).

Chaque objet de la porte range, à son alarme, le relevé de son conteneur dans l'annuaire : des chiffres jour par
jour, jamais un texte, un nom ni un numéro. L'atelier les lit tous d'un coup (GET /admin/releves de la porte), y
ajoute ce que lui seul sait (l'entreprise, la version en service, les coûts aux tarifs de MEGGA) et signale les
agents silencieux. Aucun conteneur n'est réveillé.
"""

from __future__ import annotations

from .couts import Tarifs, couts

# Un relevé est pris au plus tous les quarts d'heure ; au-delà de 40 minutes sans relevé, l'agent est silencieux.
SILENCE_S = 40 * 60
# La période lue d'un coup : un trimestre au plus (porte/src/releves.js, JOURS_LUS_MAX).
JOURS_LUS_MAX = 92
CHIFFRES = ("tours", "tours_api", "tours_en_echec", "secours")


def rassembler(brut: dict, tarifs: Tarifs, clients_atelier: dict[str, dict], maintenant: float) -> dict:
    """Les relevés de la porte, client par client, avec leurs coûts et leur santé.

    `clients_atelier` : l'entreprise et la version en service de chaque client connu de l'atelier.
    """
    sortie = []
    for c in brut.get("clients") or []:
        a = clients_atelier.get(c.get("id")) or {}
        jours, totaux, sans_tarif = {}, {k: 0 for k in CHIFFRES} | {"cout": 0.0}, set()
        for jour, chiffres in sorted((c.get("jours") or {}).items()):
            cout = couts(chiffres, tarifs)
            # Le coût du jour, et poste par poste (chaque modèle, la voix, l'écoute) pour les analyses de la console.
            jours[jour] = {**chiffres, "cout": cout["total"], "postes": {k: round(v, 4) for k, v in cout["postes"].items()}}
            for k in CHIFFRES:
                totaux[k] += int(chiffres.get(k) or 0)
            totaux["cout"] += cout["total"]
            sans_tarif.update(cout["sans_tarif"])
        totaux["cout"] = round(totaux["cout"], 4)
        releve_le = c.get("releve_le")
        actif = bool(c.get("actif"))
        sortie.append({
            "id": c.get("id"),
            "entreprise": a.get("entreprise"),
            "zone": c.get("zone"),
            "actif": actif,
            "version_annuaire": c.get("version"),
            "version_en_service": a.get("version_en_service"),
            "ecart": "version_en_service" in a and c.get("version") != a.get("version_en_service"),
            "releve_le": releve_le / 1000 if releve_le else None,
            # Actif sans relevé récent : le conteneur ne répond plus, ou la porte ne le lit plus.
            "silencieux": actif and (not releve_le or maintenant - releve_le / 1000 > SILENCE_S),
            "etat": c.get("etat"),
            "totaux": {**totaux, "sans_tarif": sorted(sans_tarif)},
            "jours": jours,
        })
    return {"depuis": brut.get("depuis"), "periode_jours": brut.get("jours"), "devise": tarifs.devise, "clients": sortie}
