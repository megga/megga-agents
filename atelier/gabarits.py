"""Les modèles par métier (gabarits) : une configuration complète, prête à marcher.

Le client choisit son métier et donne un prénom ; le gabarit fournit le reste (ton,
consignes, outils, voix). Ce qui tient au client lui-même (identifiant, entreprise,
zone, numéro WhatsApp) et les réglages avancés de MEGGA (modèles, catalogue, modèles
Meta) ne viennent jamais d'un gabarit.

On dit « gabarit » dans le code pour ne pas confondre avec les modèles de langue
(`modeles`) ni avec les modèles de message de Meta (`modeles_meta`).
"""

from __future__ import annotations

from typing import Any

from .regles import Refus

# Elise, une voix de la bibliothèque d'ElevenLabs (celle de l'agent d'essai).
VOIX_PAR_DEFAUT = "EST9Ui6982FZPSi7gCHi"

GABARITS: dict[str, dict[str, Any]] = {
    "generaliste": {
        "titre": "Généraliste",
        "description": "Accueille vos clients, répond à leurs questions, retient ce qu'on lui confie et programme les rappels demandés.",
        "reglages": {
            "metier": "general",
            "outils": [],
            "ton": "chaleureux et professionnel, vouvoie en français",
            "consignes": (
                "Tu accueilles les clients de l'entreprise et tu réponds à leurs questions avec ce que tu sais d'elle. "
                "Ce que tu ne sais pas, tu proposes de le transmettre à l'équipe. "
                "Tu retiens ce qu'on te confie et tu programmes les rappels demandés."
            ),
            "voix": {"voix": VOIX_PAR_DEFAUT},
        },
    },
    "immobilier": {
        "titre": "Immobilier",
        "description": "L'assistant d'une agence : il accueille les demandes d'achat, de vente et de location, retient les critères "
                       "et programme les rappels. La recherche de biens s'ajoute quand le catalogue de l'agence est branché.",
        "reglages": {
            "metier": "immobilier",
            "outils": [],
            "ton": "chaleureux, élégant et précis, vouvoie en français",
            "consignes": (
                "Tu travailles pour une agence immobilière. Tu accueilles les demandes d'achat, de vente et de location, "
                "tu poses les questions utiles (type de bien, lieu, budget, délai) et tu retiens les critères. "
                "Tu ne cites jamais un bien que tes outils ne t'ont pas donné. "
                "Tu proposes un rappel ou la transmission à un conseiller de l'agence."
            ),
            "voix": {"voix": VOIX_PAR_DEFAUT},
        },
    },
}

# Ce qu'il faut pour créer un client d'après un gabarit (MEGGA).
IDENTITE = ("id", "entreprise", "zone", "numero_id")


def lister() -> list[dict]:
    return [{"id": k, "titre": g["titre"], "description": g["description"], "metier": g["reglages"]["metier"],
             "reglages": g["reglages"]} for k, g in GABARITS.items()]


def gabarit(nom: Any) -> dict:
    if not isinstance(nom, str) or nom not in GABARITS:
        raise Refus(400, "Choisissez un modèle : " + ", ".join(g["titre"].lower() for g in GABARITS.values()) + ".")
    return GABARITS[nom]


def reglages_pour(nom: Any, base: dict) -> dict:
    """Les réglages du gabarit pour ce client ; le pack immobilier reste actif si son catalogue est déjà branché."""
    r = {k: (dict(v) if isinstance(v, dict) else list(v) if isinstance(v, list) else v) for k, v in gabarit(nom)["reglages"].items()}
    if r["metier"] == "immobilier" and base.get("catalogue"):
        r["outils"] = ["immobilier"]
    return r


def nouvelle_config(nom: Any, client: Any, nom_agent: Any) -> dict:
    """La configuration complète d'un nouveau client : son identité, son prénom, et le gabarit pour le reste."""
    if not isinstance(client, dict):
        raise Refus(400, "client : " + ", ".join(IDENTITE))
    manquants = [k for k in IDENTITE if not client.get(k)]
    if manquants:
        raise Refus(400, "Il manque : " + ", ".join(manquants) + ".")
    config = {
        "id": client["id"],
        "entreprise": client["entreprise"],
        "zone": client["zone"],
        "whatsapp": {"numero_id": client["numero_id"]},
        "nom_agent": nom_agent,
        **reglages_pour(nom, {}),
    }
    for k in ("langue", "fuseau"):
        if client.get(k):
            config[k] = client[k]
    return config
