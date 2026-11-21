"""Les modèles par métier (gabarits) : une configuration complète, prête à marcher.

Le client choisit son métier et donne un prénom ; le gabarit fournit le reste (ton,
consignes, outils, voix). Ce qui tient au client lui-même (identifiant, entreprise,
zone, numéro WhatsApp) et les réglages avancés de MEGGA (modèles, catalogue, modèles
Meta) ne viennent jamais d'un gabarit.

Le catalogue (lot 11, `catalogue/<catégorie>/<id>.md`) : les 283 agents d'agency-agents (licence MIT,
`LICENCE-agency-agents.txt`), écrits par `scripts/catalogue_agency_agents.py`. Un fichier par agent : un en-tête YAML
entre deux lignes `---`, puis le rôle. Ses consignes sont le socle `catalogue/_catalogue.md`, les garde-fous de
l'en-tête (`_securite.md`, `_sante.md`, `_juridique.md`) puis le rôle. Tout est vérifié à l'import : un fichier mal
formé arrête l'import, donc la CI et le démarrage de l'atelier.

On dit « gabarit » dans le code pour ne pas confondre avec les modèles de langue
(`modeles`) ni avec les modèles de message de Meta (`modeles_meta`).
"""

from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

import yaml

from ..regles import Refus

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

ICI = Path(__file__).parent
CATALOGUE_DIR = ICI / "catalogue"
# Les bornes de Config (noyau/config.py) : un modèle qui les dépasse ne se charge pas.
CONSIGNES_MAX = 8000
TON_MAX = 200
INTERDITS = re.compile(r"[\u2014\u2013\u00b7]")  # tiret long, tiret moyen, point médian (Config.sans_artefacts)
# Les catégories d'agency-agents, ses garde-fous, les champs des en-têtes.
CATEGORIES = ("academic", "design", "engineering", "finance", "game-development", "gis", "healthcare", "marketing",
              "paid-media", "product", "project-management", "research", "sales", "security", "spatial-computing",
              "specialized", "support", "testing")
GARDE_FOUS = ("securite", "sante", "juridique")
CHAMPS = ("titre", "description", "metier", "categorie", "ton", "garde_fous", "source")
FACULTATIFS = ("adapte",)  # ce qui a été changé dans le texte de la source, pour la règle de sécurité
CHAMPS_SOURCE = ("depot", "chemins", "commit", "licence")


def _texte(fichier: str, champ: str, v: Any, maximum: int | None = None) -> str:
    """Un texte non vide, sans caractère refusé par Config, et pas trop long."""
    if not isinstance(v, str) or not v.strip():
        raise ValueError(f"{fichier} : {champ} : manquant ou vide")
    if INTERDITS.search(v):
        raise ValueError(f"{fichier} : {champ} : pas de tiret long, de tiret moyen ni de point médian")
    if maximum is not None and len(v) > maximum:
        raise ValueError(f"{fichier} : {champ} : {len(v)} caractères, {maximum} au plus")
    return v


def _source(fichier: str, v: Any) -> dict:
    """Le dépôt, ses fichiers, le commit lu et la licence, MIT seulement."""
    if not isinstance(v, dict) or set(v) != set(CHAMPS_SOURCE):
        raise ValueError(f"{fichier} : source : {', '.join(CHAMPS_SOURCE)}")
    if v["licence"] != "MIT":
        raise ValueError(f"{fichier} : source : licence MIT seulement (lu : {v['licence']})")
    chemins = v["chemins"]
    if not (isinstance(chemins, list) and chemins and all(isinstance(c, str) and c for c in chemins)):
        raise ValueError(f"{fichier} : source : chemins, une liste non vide")
    _texte(fichier, "source.depot", v["depot"])
    _texte(fichier, "source.commit", v["commit"])
    return {"depot": v["depot"], "chemins": list(chemins), "commit": v["commit"], "licence": "MIT"}


def _lire(chemin: Path, f: str) -> tuple[dict, str]:
    """L'en-tête (entre deux lignes `---`) et le rôle d'un fichier."""
    lignes = chemin.read_text(encoding="utf-8").replace("\r\n", "\n").split("\n")
    fins = [i for i, l in enumerate(lignes) if l.strip() == "---"]
    if lignes[0].strip() != "---" or len(fins) < 2:
        raise ValueError(f"{f} : un en-tête YAML entre deux lignes ---, puis le rôle")
    try:
        entete = yaml.safe_load("\n".join(lignes[1:fins[1]]))
    except yaml.YAMLError as e:
        raise ValueError(f"{f} : en-tête illisible ({' '.join(str(e).split())})") from None
    if not isinstance(entete, dict):
        raise ValueError(f"{f} : l'en-tête est une suite de champs (titre, description, ...)")
    return entete, "\n".join(lignes[fins[1] + 1:]).strip()


def charger_catalogue(dossier: Path | None = None, pris: Any = ()) -> dict[str, dict]:
    """Les modèles du catalogue, vérifiés, par catégorie puis par nom. Chacun vient d'agency-agents (sa source, MIT,
    est obligatoire) ; un modèle de la catégorie security a toujours le garde-fou sécurité. `pris` : les noms déjà
    donnés (les gabarits écrits ici), qu'un modèle du catalogue ne peut pas reprendre."""
    dossier = Path(dossier) if dossier is not None else CATALOGUE_DIR
    socle = _texte("_catalogue.md", "socle", (dossier / "_catalogue.md").read_text(encoding="utf-8").strip())
    blocs = {g: _texte(f"_{g}.md", "garde-fou", (dossier / f"_{g}.md").read_text(encoding="utf-8").strip())
             for g in GARDE_FOUS}
    metiers = ("general", "immobilier")
    modeles: dict[str, dict] = {}
    for chemin in sorted(dossier.glob("*/*.md"), key=lambda c: (CATEGORIES.index(c.parent.name)
                                                                if c.parent.name in CATEGORIES else -1, c.stem)):
        f = f"{chemin.parent.name}/{chemin.name}"
        entete, role = _lire(chemin, f)
        if inconnus := [k for k in entete if k not in CHAMPS + FACULTATIFS]:
            raise ValueError(f"{f} : {', '.join(map(str, inconnus))} : champ inconnu")
        if manquants := [k for k in CHAMPS if k not in entete]:
            raise ValueError(f"{f} : {', '.join(manquants)} : manquant")
        categorie = entete["categorie"]
        if categorie not in CATEGORIES or categorie != chemin.parent.name:
            raise ValueError(f"{f} : categorie : {categorie!r}, celle de son dossier et l'une de : {', '.join(CATEGORIES)}")
        if entete["metier"] not in metiers:
            raise ValueError(f"{f} : metier : {entete['metier']!r} n'est pas un métier ({', '.join(metiers)})")
        garde = entete["garde_fous"]
        if not isinstance(garde, list) or len(set(garde)) != len(garde) or any(g not in GARDE_FOUS for g in garde):
            raise ValueError(f"{f} : garde_fous : une liste prise dans {', '.join(GARDE_FOUS)}")
        if categorie == "security" and "securite" not in garde:
            raise ValueError(f"{f} : garde_fous : un agent de sécurité a toujours le garde-fou securite")
        source = _source(f, entete["source"])
        if "adapte" in entete:
            _texte(f, "adapte", entete["adapte"])
        if chemin.stem in modeles or chemin.stem in pris:
            raise ValueError(f"{f} : {chemin.stem} : ce nom de modèle est déjà pris")
        _texte(f, "consignes", role)
        consignes = _texte(f, "consignes", "\n\n".join([socle, *(blocs[g] for g in garde), role]), CONSIGNES_MAX)
        modeles[chemin.stem] = {
            "titre": _texte(f, "titre", entete["titre"]),
            "description": _texte(f, "description", entete["description"]),
            "source": source,
            "categorie": categorie,
            "garde_fous": list(garde),
            "reglages": {
                "metier": entete["metier"],
                "outils": [],
                "ton": _texte(f, "ton", entete["ton"], TON_MAX),
                "consignes": consignes,
                "voix": {"voix": VOIX_PAR_DEFAUT},
            },
        }
    return modeles


CATALOGUE: dict[str, dict[str, Any]] = charger_catalogue(pris=GABARITS)
# Tous les modèles qu'on peut choisir : ceux écrits ici, puis le catalogue.
MODELES: dict[str, dict[str, Any]] = {**GABARITS, **CATALOGUE}
CONSIGNES_CONNUES: frozenset[str] = frozenset(g["reglages"]["consignes"] for g in MODELES.values())
# Les numéros d'urgence du garde-fou santé (le 144, le 145) sont suisses : pas encore pour la zone États-Unis.
PAS_AUX_ETATS_UNIS = tuple(k for k, g in CATALOGUE.items() if "sante" in g["garde_fous"])

# Ce qu'il faut pour créer un client d'après un gabarit (MEGGA).
IDENTITE = ("id", "entreprise", "zone")
# Facultatif : sans numéro, l'agent ne sert que par API (noyau/api.py).
NUMERO = "numero_id"


def lister() -> list[dict]:
    """Les gabarits écrits ici (sans catégorie), puis le catalogue, rangé par catégorie."""
    return [{"id": k, "titre": g["titre"], "description": g["description"], "metier": g["reglages"]["metier"],
             "categorie": g.get("categorie"), "garde_fous": g.get("garde_fous", []), "source": g.get("source"),
             "reglages": g["reglages"]} for k, g in MODELES.items()]


def gabarit(nom: Any) -> dict:
    if not isinstance(nom, str) or nom not in MODELES:
        raise Refus(400, "Choisissez un modèle : " + ", ".join(g["titre"].lower() for g in GABARITS.values())
                    + ", ou un modèle du catalogue.")
    return MODELES[nom]


def reglages_pour(nom: Any, base: dict) -> dict:
    """Les réglages du gabarit pour ce client ; le pack immobilier reste actif si son catalogue est déjà branché.
    Les modèles qui ont le garde-fou santé sont refusés pour la zone États-Unis."""
    g = gabarit(nom)
    if nom in PAS_AUX_ETATS_UNIS and base.get("zone") == "etats-unis":
        raise Refus(400, "Ce modèle n'est pas encore disponible pour la zone États-Unis.")
    r = copy.deepcopy(g["reglages"])
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
        "nom_agent": nom_agent,
        **reglages_pour(nom, {"zone": client["zone"]}),
    }
    if client.get(NUMERO):
        config["whatsapp"] = {"numero_id": client[NUMERO]}
    for k in ("langue", "fuseau"):
        if client.get(k):
            config[k] = client[k]
    return config
