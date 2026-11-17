"""Les modèles par métier (gabarits) : une configuration complète, prête à marcher.

Le client choisit son métier et donne un prénom ; le gabarit fournit le reste (ton,
consignes, outils, voix). Ce qui tient au client lui-même (identifiant, entreprise,
zone, numéro WhatsApp) et les réglages avancés de MEGGA (modèles, catalogue, modèles
Meta) ne viennent jamais d'un gabarit.

Un fichier par modèle, `<id>.md` : un en-tête YAML entre deux lignes `---` (titre,
description, metier, ton, ordre, source, et a_valider s'il le faut), puis le bloc de
consignes propre au métier. Les consignes d'un modèle sont le socle d'accueil commun
(`_accueil.md`) suivi de ce bloc. Tout est vérifié à l'import : un fichier mal formé
arrête l'import, donc la CI et le démarrage de l'atelier (pas la construction de l'image :
`pip install .` n'importe rien).

Les textes tirés d'agency-agents (licence MIT, `LICENCE-agency-agents.txt`) nomment leur
source dans `source` ; un modèle écrit sans source a `source: null`.

On dit « gabarit » dans le code pour ne pas confondre avec les modèles de langue
(`modeles`) ni avec les modèles de message de Meta (`modeles_meta`).
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

import yaml

from noyau.config import NOMS_METIERS

from ..regles import Refus

ICI = Path(__file__).parent
# Elise, une voix de la bibliothèque d'ElevenLabs (celle de l'agent d'essai).
VOIX_PAR_DEFAUT = "EST9Ui6982FZPSi7gCHi"
# Les outils de tous les modèles : les documents de l'entreprise et les demandes notées pour l'équipe.
OUTILS = ("connaissances", "leads")
# Les bornes de Config (noyau/config.py) : un modèle qui les dépasse ne se charge pas.
CONSIGNES_MAX = 8000
TON_MAX = 200
INTERDITS = re.compile(r"[\u2014\u2013\u00b7]")  # tiret long, tiret moyen, point médian (Config.sans_artefacts)
CHAMPS = ("titre", "description", "metier", "ton", "ordre", "source")
# Ce qui reste à faire relire par des professionnels du métier ; reste dans le fichier.
FACULTATIFS = ("a_valider",)
CHAMPS_SOURCE = ("depot", "chemins", "commit", "licence")


def _plein(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


def _texte(fichier: str, champ: str, v: Any, maximum: int | None = None) -> str:
    """Un texte non vide, sans caractère refusé par Config, et pas trop long."""
    if not _plein(v):
        raise ValueError(f"{fichier} : {champ} : manquant ou vide")
    if INTERDITS.search(v):
        raise ValueError(f"{fichier} : {champ} : pas de tiret long, de tiret moyen ni de point médian")
    if maximum is not None and len(v) > maximum:
        raise ValueError(f"{fichier} : {champ} : {len(v)} caractères, {maximum} au plus")
    return v


def _source(fichier: str, v: Any) -> dict | None:
    """Nulle (un modèle écrit sans source) ou complète : le dépôt, ses fichiers, le commit lu, la licence MIT."""
    if v is None:
        return None
    if not isinstance(v, dict) or set(v) != set(CHAMPS_SOURCE):
        raise ValueError(f"{fichier} : source : null, ou {', '.join(CHAMPS_SOURCE)}")
    if v["licence"] != "MIT":
        raise ValueError(f"{fichier} : source : licence MIT seulement (lu : {v['licence']})")
    chemins = v["chemins"]
    if not (_plein(v["depot"]) and _plein(v["commit"]) and isinstance(chemins, list) and chemins
            and all(_plein(c) for c in chemins)):
        raise ValueError(f"{fichier} : source : le dépôt, ses chemins et le commit, non vides")
    return {"depot": v["depot"], "chemins": list(chemins), "commit": v["commit"], "licence": "MIT"}


def _lire(chemin: Path) -> tuple[dict, str]:
    """L'en-tête (entre deux lignes `---`) et le bloc de consignes d'un fichier."""
    lignes = chemin.read_text(encoding="utf-8").replace("\r\n", "\n").split("\n")
    fins = [i for i, l in enumerate(lignes) if l.strip() == "---"]
    if not lignes or lignes[0].strip() != "---" or len(fins) < 2:
        raise ValueError(f"{chemin.name} : un en-tête YAML entre deux lignes ---, puis les consignes")
    try:
        entete = yaml.safe_load("\n".join(lignes[1:fins[1]]))
    except yaml.YAMLError as e:
        raise ValueError(f"{chemin.name} : en-tête illisible ({' '.join(str(e).split())})") from None
    if not isinstance(entete, dict):
        raise ValueError(f"{chemin.name} : l'en-tête est une suite de champs (titre, description, ...)")
    return entete, "\n".join(lignes[fins[1] + 1:]).strip()


def charger(dossier: Path | None = None) -> dict[str, dict]:
    """Les modèles d'un dossier (celui du paquet par défaut), vérifiés, dans l'ordre de leur champ `ordre`.
    Les fichiers qui commencent par « _ » ne sont pas des modèles (le socle). Une erreur nomme le fichier et le champ."""
    dossier = Path(dossier) if dossier is not None else ICI
    socle = _texte("_accueil.md", "socle", (dossier / "_accueil.md").read_text(encoding="utf-8").strip())
    modeles: list[tuple[int, str, dict]] = []
    ordres: dict[int, str] = {}
    for chemin in sorted(dossier.glob("*.md")):
        if chemin.name.startswith("_"):
            continue
        f = chemin.name
        entete, bloc = _lire(chemin)
        if inconnus := [k for k in entete if k not in CHAMPS + FACULTATIFS]:
            raise ValueError(f"{f} : {', '.join(map(str, inconnus))} : champ inconnu")
        if manquants := [k for k in CHAMPS if k not in entete]:
            raise ValueError(f"{f} : {', '.join(manquants)} : manquant")
        titre = _texte(f, "titre", entete["titre"])
        description = _texte(f, "description", entete["description"])
        ton = _texte(f, "ton", entete["ton"], TON_MAX)
        metier = entete["metier"]
        if metier not in NOMS_METIERS:
            raise ValueError(f"{f} : metier : {metier!r} n'est pas un métier ({', '.join(NOMS_METIERS)})")
        ordre = entete["ordre"]
        if not isinstance(ordre, int) or isinstance(ordre, bool):
            raise ValueError(f"{f} : ordre : un nombre entier")
        if ordre in ordres:
            raise ValueError(f"{f} : ordre : {ordre}, déjà celui de {ordres[ordre]}")
        ordres[ordre] = f
        source = _source(f, entete["source"])
        if "a_valider" in entete:
            _texte(f, "a_valider", entete["a_valider"])
        _texte(f, "consignes", bloc)  # le bloc du métier
        consignes = _texte(f, "consignes", socle + "\n\n" + bloc, CONSIGNES_MAX)
        modeles.append((ordre, chemin.stem, {
            "titre": titre,
            "description": description,
            "source": source,
            "reglages": {
                "metier": metier,
                # Les réglages communs à tous les modèles : les documents de l'entreprise, les demandes notées pour
                # l'équipe, le transfert à un humain, la mention de l'IA (lot 9).
                "outils": list(OUTILS),
                # Le transfert passe la main à l'équipe : il n'agit qu'avec le rôle gestionnaire (sans lui, il est inerte,
                # relecture du lot 9.3), et le visiteur sert tous les autres. Les deux gardent les outils de l'agent : rien ne change pour le public,
                # et les gestionnaires reçoivent ceux de l'équipe pour prendre et rendre la main.
                "roles": {r: {"outils": ["rappels", *OUTILS]} for r in ("gestionnaire", "visiteur")},
                "ton": ton,
                "consignes": consignes,
                "voix": {"voix": VOIX_PAR_DEFAUT},
                "transfert": True,
                "mention_ia": True,
            },
        }))
    return {nom: g for _, nom, g in sorted(modeles, key=lambda m: m[0])}


GABARITS: dict[str, dict[str, Any]] = charger()
# Les consignes des modèles d'avant leurs fichiers (lot 10), à l'octet près : un client créé avec elles peut toujours
# passer à un autre modèle, et elles ne sont pas prises pour des consignes écrites sur mesure par MEGGA.
ANCIENNES: dict[str, str] = json.loads((ICI / "anciens.json").read_text(encoding="utf-8"))
CONSIGNES_CONNUES: frozenset[str] = frozenset([*(g["reglages"]["consignes"] for g in GABARITS.values()), *ANCIENNES.values()])

# Les modèles dont les numéros d'urgence (le 144, le 112) sont ceux de la Suisse et de l'Europe : pas encore pour la zone
# États-Unis, où ils seraient faux (relecture finale du lot 10, I7).
PAS_AUX_ETATS_UNIS = ("sante", "garage")

# Ce qu'il faut pour créer un client d'après un gabarit (MEGGA).
IDENTITE = ("id", "entreprise", "zone")
# Facultatif : sans numéro, l'agent ne sert que par API (noyau/api.py).
NUMERO = "numero_id"


def lister() -> list[dict]:
    return [{"id": k, "titre": g["titre"], "description": g["description"], "metier": g["reglages"]["metier"],
             "source": g["source"], "reglages": g["reglages"]} for k, g in GABARITS.items()]


def gabarit(nom: Any) -> dict:
    if not isinstance(nom, str) or nom not in GABARITS:
        raise Refus(400, "Choisissez un modèle : " + ", ".join(g["titre"].lower() for g in GABARITS.values()) + ".")
    return GABARITS[nom]


def reglages_pour(nom: Any, base: dict) -> dict:
    """Les réglages du gabarit pour ce client ; le pack immobilier reste actif si son catalogue est déjà branché, et les rôles
    déjà réglés restent. Santé et garage sont refusés pour la zone États-Unis."""
    g = gabarit(nom)
    if nom in PAS_AUX_ETATS_UNIS and base.get("zone") == "etats-unis":
        raise Refus(400, "Ce modèle n'est pas encore disponible pour la zone États-Unis.")
    r = copy.deepcopy(g["reglages"])
    if r["metier"] == "immobilier" and base.get("catalogue"):
        r["outils"] = ["immobilier", *r["outils"]]
        for role in r["roles"].values():
            role["outils"] = ["rappels", "immobilier", *role["outils"][1:]]
    if base.get("roles"):  # les rôles déjà réglés pour ce client (par MEGGA) restent : un modèle ne les remplace pas
        del r["roles"]
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
