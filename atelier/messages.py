"""Les erreurs de validation en français clair, champ par champ, prêtes à montrer au client."""

from __future__ import annotations

import re

from pydantic import ValidationError

# Par champ (chemin sans les rangs de liste), puis par genre d'erreur de pydantic.
PAR_CHAMP: dict[str, dict[str, str]] = {
    "nom_agent": {
        "missing": "Donnez un prénom à votre agent.",
        "string_too_short": "Donnez un prénom à votre agent.",
        "string_too_long": "Le prénom doit faire {max_length} caractères au plus.",
    },
    "entreprise": {
        "missing": "Indiquez le nom de l'entreprise.",
        "string_too_short": "Indiquez le nom de l'entreprise.",
        "string_too_long": "Le nom de l'entreprise doit faire {max_length} caractères au plus.",
    },
    "voix.voix": {
        "string_pattern_mismatch": "Choisissez une voix dans la liste.",
        "string_type": "Choisissez une voix dans la liste.",
    },
    "voix.par_langue": {"value_error": "Une voix par langue : un code de langue de deux lettres et une voix de la liste."},
    "ton": {"string_too_long": "Le ton doit faire {max_length} caractères au plus."},
    "consignes": {"string_too_long": "Les consignes doivent faire {max_length} caractères au plus."},
    "metier": {"literal_error": "Choisissez un métier : {expected}."},
    "outils": {"literal_error": "Cet outil n'existe pas.", "list_type": "Cochez les outils dans la liste.", "tuple_type": "Cochez les outils dans la liste."},
    "zone": {"literal_error": "Choisissez une zone : {expected}.", "missing": "Choisissez une zone."},
    "id": {
        "missing": "Indiquez l'identifiant du client.",
        "string_pattern_mismatch": "L'identifiant : lettres minuscules, chiffres et tirets, de 2 à 63 caractères.",
    },
    "whatsapp": {"missing": "Indiquez le numéro WhatsApp."},
    "whatsapp.numero_id": {
        "missing": "Indiquez l'identifiant du numéro WhatsApp.",
        "string_pattern_mismatch": "L'identifiant du numéro WhatsApp : des chiffres seulement.",
    },
    "langue": {"string_pattern_mismatch": "La langue : un code de deux lettres, par exemple fr."},
    "catalogue": {"string_pattern_mismatch": "Le catalogue : « demo:nom » ou une adresse https."},
    "voix.vitesse": {"greater_than_equal": "La vitesse de la voix : {ge} au moins.", "less_than_equal": "La vitesse de la voix : {le} au plus."},
    "voix.stabilite": {"greater_than_equal": "La stabilité de la voix : {ge} au moins.", "less_than_equal": "La stabilité de la voix : {le} au plus."},
}

PAR_GENRE: dict[str, str] = {
    "missing": "Ce champ est obligatoire.",
    "string_too_short": "Ce champ ne peut pas être vide.",
    "string_too_long": "{max_length} caractères au plus.",
    "string_pattern_mismatch": "Format non valable.",
    "literal_error": "Choisissez parmi : {expected}.",
    "extra_forbidden": "Réglage inconnu.",
    "greater_than_equal": "La valeur doit être d'au moins {ge}.",
    "less_than_equal": "La valeur doit être d'au plus {le}.",
    "greater_than": "La valeur doit dépasser {gt}.",
    "less_than": "La valeur doit rester sous {lt}.",
}


def _choix(expected: str) -> str:
    """« 'a', 'b' or 'c' » devient « a, b ou c »."""
    return expected.replace("'", "").replace(" or ", " ou ")


def _message(champ: str, err: dict) -> str:
    genre = err.get("type", "")
    ctx = dict(err.get("ctx") or {})
    if "expected" in ctx:
        ctx["expected"] = _choix(str(ctx["expected"]))
    for k, v in ctx.items():  # 0.0 s'écrit 0, 1.2 s'écrit 1,2
        if isinstance(v, float):
            ctx[k] = str(int(v)) if v.is_integer() else str(v).replace(".", ",")
    modele = PAR_CHAMP.get(champ, {}).get(genre) or PAR_GENRE.get(genre)
    if modele:
        try:
            return modele.format(**ctx)
        except (KeyError, IndexError):
            return modele
    if genre == "value_error":
        # Les messages de nos propres règles (noyau/config.py) sont déjà en français.
        texte = re.sub(r"^Value error, ", "", err.get("msg", "")).strip()
        return texte[:1].upper() + texte[1:] if texte else "Valeur non valable."
    return "Valeur non valable."


def erreurs(e: ValidationError) -> list[dict]:
    """Une erreur par champ : son chemin (« voix.voix ») et un message en français clair."""
    sortie = []
    for err in e.errors():
        chemin = [str(x) for x in err.get("loc", ())]
        champ = ".".join(x for x in chemin if not x.isdigit())
        sortie.append({"champ": champ, "message": _message(champ, err)})
    return sortie
