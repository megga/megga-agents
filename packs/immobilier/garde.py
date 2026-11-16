"""Les garde-fous d'un texte d'annonce avant qu'il parte sur le site (repris de garde.js d'Alix FSP).

Le 12.11.2026, une annonce est partie en ligne sous le titre « Annières, Greg, Julien » : depuis, un texte
d'annonce ne nomme jamais quelqu'un de l'équipe, ne parle pas de la machinerie (PDF, WhatsApp, brouillon),
et un titre n'est ni trop court ni une liste de mots.
"""

from __future__ import annotations

import re

from noyau.typographie import sans_artefacts

CHAMPS = ("titre", "titre_en", "accroche", "accroche_en", "description", "description_en")
NOMS_CHAMPS = {"titre": "Le titre", "titre_en": "Le titre anglais", "accroche": "L'accroche", "accroche_en": "L'accroche anglaise",
               "description": "La description", "description_en": "La description anglaise"}
CONSIGNE = re.compile(r"\b(pdf|whatsapp|fiche|brouillon|annonce test|à corriger|todo)\b", re.I)


def nettoyer(valeur):
    """Sans tiret long ni point médian, en profondeur (textes, listes, objets)."""
    if isinstance(valeur, str):
        return sans_artefacts(valeur)
    if isinstance(valeur, list):
        return [nettoyer(v) for v in valeur]
    if isinstance(valeur, dict):
        return {k: nettoyer(v) for k, v in valeur.items()}
    return valeur


def problemes(textes: dict, noms_interdits: tuple[str, ...] = ()) -> list[str]:
    """Ce qui empêche ces textes de partir ; vide s'ils peuvent partir."""
    noms = re.compile(r"\b(" + "|".join(re.escape(n) for n in noms_interdits if n.strip()) + r")\b", re.I) if any(
        n.strip() for n in noms_interdits) else None
    sortie = []
    for champ in CHAMPS:
        t = " ".join(str(textes.get(champ) or "").split())
        if not t:
            continue
        nom = NOMS_CHAMPS[champ]
        if noms and (m := noms.search(t)):
            sortie.append(f"{nom} nomme « {m.group(1)} » : jamais le nom de quelqu'un de l'équipe dans une annonce.")
        if champ.startswith(("titre", "accroche")) and (m := CONSIGNE.search(t)):
            sortie.append(f"{nom} parle de « {m.group(1)} » : c'est une consigne, pas un texte d'annonce.")
        if champ.startswith("titre"):
            if len(t) < 12:
                sortie.append(f"{nom} est trop court.")
            if t.count(",") >= 2:
                sortie.append(f"{nom} est une liste de mots, pas un titre.")
    return sortie


def verifier(textes: dict, noms_interdits: tuple[str, ...] = ()) -> None:
    p = problemes(textes, noms_interdits)
    if p:
        raise ValueError(" ".join(p) + " Réécris ces textes (ou demande à la personne), sans rien inventer.")


def blocs(texte: str) -> list:
    """Une description en texte vers les blocs du site : « ## X » un titre, des lignes « - » une liste, sinon un paragraphe."""
    sortie = []
    for bloc in re.split(r"\n\s*\n", str(texte or "").strip()):
        lignes = [l.strip() for l in bloc.splitlines() if l.strip()]
        if not lignes:
            continue
        if len(lignes) == 1 and lignes[0].startswith("## "):
            sortie.append(["titre", lignes[0][3:].strip()])
        elif all(l.startswith("-") for l in lignes):
            sortie.append(["liste", [l.lstrip("-").strip() for l in lignes]])
        else:
            sortie.append(" ".join(lignes))
    return sortie


def texte(blocs_: list) -> str:
    """Les blocs du site vers le texte que l'agent lit."""
    sortie = []
    for b in blocs_ or []:
        if isinstance(b, str):
            sortie.append(b)
        elif isinstance(b, list) and len(b) == 2 and b[0] == "titre":
            sortie.append(f"## {b[1]}")
        elif isinstance(b, list) and len(b) == 2 and b[0] == "liste":
            sortie.append("\n".join(f"- {x}" for x in b[1]))
    return "\n\n".join(sortie)


def forme(blocs_: list) -> list:
    """La forme des blocs (paragraphe, titre, liste de n éléments) : le français et l'anglais doivent l'avoir pareille."""
    return [("p" if isinstance(b, str) else "t" if b[0] == "titre" else f"l{len(b[1])}") for b in blocs_]
