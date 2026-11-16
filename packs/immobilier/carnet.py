"""Le carnet du marché : des prix au m², chacun avec sa source, et les chiffres qu'on en tire (repris de carnet.js et
de zones.js d'Alix FSP). Les chiffres sont calculés ici, jamais par le modèle.

  vente     un prix de vente réalisé, donné par un courtier
  avis      son avis sur un prix au m² (« entre 25 et 30 000 à Cologny »), en fourchette
  annonce   un prix demandé, lu sur un portail ou relayé, avec son lien

Nos propres biens en ligne s'y ajoutent à l'analyse (prix demandés), lus dans la gestion du site.
"""

from __future__ import annotations

import datetime as dt
import math
import re
import time
import unicodedata
from zoneinfo import ZoneInfo

NATURES = ("vente", "avis", "annonce")
FAMILLES = ("maison", "appartement", "terrain", "autre")
DEVISES = ("CHF", "EUR", "AED")
BORNES = {"CHF": (1000, 150000), "EUR": (1000, 150000), "AED": (2000, 200000)}  # prix au m² plausibles
POUR_CONCLURE = 5  # en deçà, trop peu pour une médiane
ANCIEN = 365 * 86400
VARIATION = 0.05  # un suivi de zone ne prévient qu'au-delà
CATEGORIES = {
    "maison": ("villa", "maison", "maison individuelle", "maison de ville", "chateau", "propriete", "propriete de campagne"),
    "appartement": ("appartement", "appartement terrasse", "duplex", "studio", "attique", "duplex en attique", "penthouse", "loft"),
    "terrain": ("terrain",),
}
NOMS = {"vente": "vente réalisée", "avis": "avis du courtier", "annonce": "prix demandé d'une annonce"}


def plat(t) -> str:
    t = "".join(c for c in unicodedata.normalize("NFD", str(t or "").lower()) if unicodedata.category(c) != "Mn").replace("œ", "oe")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", t).split())


def famille_de(t) -> str:
    if t in FAMILLES:
        return t
    return next((f for f, cats in CATEGORIES.items() if plat(t) in cats), "autre")


def meme_lieu(a, b) -> bool:
    """Le même lieu, mot pour mot : « Genève » et « Genève, Champel » oui ; « Ollon » et « Collonge-Bellerive » non."""
    x, y = set(re.findall(r"[a-z0-9]+", plat(a))), set(re.findall(r"[a-z0-9]+", plat(b)))
    return bool(x and y and (x <= y or y <= x))


def montant(n: float, devise: str) -> str:
    return f"{devise} {round(n):,}".replace(",", "’")


def date_courte(t: float, fuseau: str = "Europe/Zurich") -> str:
    return dt.datetime.fromtimestamp(t, ZoneInfo(fuseau)).strftime("%d.%m.%Y")


def _quantile(tries: list[float], q: float) -> float:
    p = (len(tries) - 1) * q
    b = math.floor(p)
    return tries[b] + (tries[min(b + 1, len(tries) - 1)] - tries[b]) * (p - b)


def statistiques(valeurs) -> dict:
    """Médiane, quartiles, bornes ; à partir de cinq valeurs, celles hors norme (1,5 écart interquartile) sont écartées."""
    v = sorted(x for x in valeurs if isinstance(x, (int, float)) and math.isfinite(x))
    ecartees = 0
    if len(v) >= POUR_CONCLURE:
        q1, q3 = _quantile(v, 0.25), _quantile(v, 0.75)
        e = (q3 - q1) * 1.5
        # Des valeurs presque toutes égales (écart interquartile nul) : rien n'est écarté, la moindre différence n'est pas
        # « hors norme ».
        gardees = [x for x in v if q1 - e <= x <= q3 + e] if e > 0 else v
        ecartees, v = len(v) - len(gardees), gardees
    if not v:
        return {"n": 0, "ecartees": ecartees}
    return {"n": len(v), "ecartees": ecartees, "mediane": _quantile(v, 0.5), "q1": _quantile(v, 0.25), "q3": _quantile(v, 0.75),
            "min": v[0], "max": v[-1]}


def _nombre(x) -> float | None:
    try:
        n = float(x)
    except (TypeError, ValueError):
        return None
    return n if math.isfinite(n) and n > 0 else None


def _court(t, n: int) -> str:
    return " ".join(str(t or "").split())[:n]


def releve(e: dict, maintenant: float | None = None) -> dict:
    """Un relevé tel qu'on l'entre : vérifié, prix au m² calculé ; une ValueError lisible sinon."""
    maintenant = time.time() if maintenant is None else maintenant
    nature = e.get("nature") if e.get("nature") in NATURES else None
    if not nature:
        raise ValueError("nature : vente, avis ou annonce")
    lieu = _court(e.get("lieu"), 80)
    if len(lieu) < 2:
        raise ValueError("il faut le lieu (la commune)")
    devise = e.get("devise") if e.get("devise") in DEVISES else None
    if not devise:
        raise ValueError("devise : CHF, EUR ou AED")
    prix, surface = _nombre(e.get("prix")), _nombre(e.get("surface"))
    m2, bas, haut = _nombre(e.get("prix_m2")), _nombre(e.get("prix_m2_bas")), _nombre(e.get("prix_m2_haut"))
    if not m2 and prix and surface:
        m2 = prix / surface
    if not m2 and bas and haut:
        m2 = (bas + haut) / 2
    if not m2:
        raise ValueError("il faut un prix au m², ou un prix et une surface habitable, ou une fourchette au m²")
    mini, maxi = BORNES[devise]
    for x in (m2, bas, haut):
        if x and not mini <= x <= maxi:
            raise ValueError(f"{montant(x, devise)} le m² n'est pas plausible : vérifie le chiffre et la surface (habitable, pas le terrain) avant de le noter")
    if bas and haut and bas > haut:
        bas, haut = haut, bas
    quand = maintenant
    d = str(e.get("date") or "")
    if re.fullmatch(r"\d{4}-\d{2}(-\d{2})?", d):
        try:
            quand = dt.datetime.fromisoformat(d if len(d) == 10 else f"{d}-15").replace(tzinfo=dt.timezone.utc).timestamp()
        except ValueError:
            pass
    lien = str(e.get("lien") or "")[:300] if re.fullmatch(r"https?://\S+", str(e.get("lien") or "")) else None
    texte = _court(e.get("texte"), 300) or None
    if nature == "annonce" and not lien and not texte:
        raise ValueError("une annonce se note avec son lien, ou ce que le courtier en a dit")
    return {"nature": nature, "lieu": lieu, "quartier": _court(e.get("quartier"), 80) or None, "famille": famille_de(e.get("type")),
            "devise": devise, "prix": prix, "surface": surface, "prix_m2": round(m2), "bas": round(bas) if bas else None,
            "haut": round(haut) if haut else None, "texte": texte, "lien": lien, "date": quand, "note": maintenant}


def fourchette(r: dict, devise: str | None = None) -> str:
    d = devise or r["devise"]
    return f"de {montant(r['bas'], d)} à {montant(r['haut'], d)}" if r.get("bas") and r.get("haut") else montant(r["prix_m2"], d)


def ligne_releve(r: dict, fuseau: str = "Europe/Zurich") -> str:
    return (f"{r['id']}. [{r['nature']}, {date_courte(r['date'], fuseau)}] {r['lieu']}{' (' + r['quartier'] + ')' if r.get('quartier') else ''}, "
            f"{r['famille']} : {fourchette(r)}/m²{' (' + str(round(r['surface'])) + ' m²)' if r.get('surface') else ''}"
            f"{', « ' + r['texte'] + ' »' if r.get('texte') else ''}{', ' + r['lien'] if r.get('lien') else ''}")


def _groupe(titre: str, valeurs: list[float], devise: str, avertissement: str) -> str | None:
    s = statistiques(valeurs)
    if not s["n"]:
        return None
    tete = f"- {titre} : {s['n']} relevé{'s' if s['n'] > 1 else ''}"
    if s["n"] < POUR_CONCLURE:
        return f"{tete}, trop peu pour une médiane : {', '.join(montant(x, devise) for x in sorted(valeurs))}/m²{avertissement}"
    hors = f" ; {s['ecartees']} valeur{'s' if s['ecartees'] > 1 else ''} hors norme écartée{'s' if s['ecartees'] > 1 else ''}" if s["ecartees"] else ""
    return (f"{tete}, médiane {montant(s['mediane'], devise)}/m², la moitié entre {montant(s['q1'], devise)} et {montant(s['q3'], devise)}, "
            f"de {montant(s['min'], devise)} à {montant(s['max'], devise)}{hors}{avertissement}")


def _nos_biens(annonces, sauf: str | None = None) -> list[dict]:
    return [{"lieu": a.get("localite"), "quartier": a.get("quartier"), "famille": famille_de(a.get("categorie")), "devise": a.get("devise") or "CHF",
             "prix_m2": a["montant"] / a["surface"]}
            for a in annonces or [] if a.get("enLigne", True) and not a.get("offMarket") and not a.get("masquee") and a.get("transaction") == "vente"
            and _nombre(a.get("montant")) and _nombre(a.get("surface")) and (sauf is None or a.get("reference") != sauf)]


def analyse(lieu: str, quartier: str, type_: str, releves: list[dict], annonces: list[dict], maintenant: float | None = None,
            fuseau: str = "Europe/Zurich") -> str:
    """L'analyse d'un lieu : le carnet, puis nos biens en ligne. Un texte à rendre tel quel, avec ses sources."""
    maintenant = time.time() if maintenant is None else maintenant
    famille = famille_de(type_) if type_ else None

    def colle(r):
        return meme_lieu(r["lieu"], lieu) and (not quartier or meme_lieu(r.get("quartier"), quartier)) and (not famille or famille == "autre" or r["famille"] == famille)

    carnet = [r for r in releves if colle(r)]
    nos = [r for r in _nos_biens(annonces) if colle(r)]
    devises = list(dict.fromkeys(r["devise"] for r in [*carnet, *nos]))
    titre = f"{lieu}{', ' + quartier if quartier else ''}{', ' + famille + 's' if famille and famille != 'autre' else ''}"
    if not devises:
        return (f"Marché, {titre} : aucun relevé dans le carnet ni parmi nos biens en ligne. Il faut des chiffres du courtier, ou une recherche "
                "sur les portails (chercher_marche en mode avancé), avant de dire quoi que ce soit.")
    lignes = [f"Marché, {titre} (chiffres calculés : rends-les tels quels, ne les recalcule pas, et dis toujours leur source) :"]
    for devise in devises:
        def de(liste, nature=None):
            return [r for r in liste if r["devise"] == devise and (not nature or r.get("nature") == nature)]

        def vieux(liste):
            return " ; certains datent de plus d'un an" if any(maintenant - r["date"] > ANCIEN for r in liste) else ""

        def periode(liste):
            return f" (du {date_courte(min(r['date'] for r in liste), fuseau)} au {date_courte(max(r['date'] for r in liste), fuseau)})" if liste else ""

        ventes, portails, avis = de(carnet, "vente"), de(carnet, "annonce"), de(carnet, "avis")
        if len(devises) > 1:
            lignes.append(f"En {devise} :")
        lignes += [x for x in [
            _groupe(f"Ventes réalisées, notées par le courtier{periode(ventes)}", [r["prix_m2"] for r in ventes], devise, vieux(ventes)),
            *(f"- Avis du courtier, le {date_courte(r['date'], fuseau)} : {fourchette(r, devise)}/m²{' (« ' + r['texte'] + ' »)' if r.get('texte') else ''}"
              f"{', il y a plus d’un an' if maintenant - r['date'] > ANCIEN else ''}" for r in avis),
            _groupe(f"Annonces relevées sur les portails, prix demandés et non prix de vente{periode(portails)}", [r["prix_m2"] for r in portails], devise,
                    vieux(portails)),
            _groupe("Nos biens en ligne, prix demandés", [r["prix_m2"] for r in de(nos)], devise, ""),
        ] if x]
    return "\n".join(lignes)


def comparer(bien: dict, releves: list[dict], annonces: list[dict]) -> str:
    """Un de nos biens face aux prix du même lieu et du même type : sa place parmi les prix demandés et les ventes notées."""
    if not _nombre(bien.get("montant")) or not _nombre(bien.get("surface")):
        return f"{bien.get('titre', '')} : il faut son prix et sa surface habitable pour le comparer{'' if bien.get('montant') else ' (prix sur demande)'}."
    devise = bien.get("devise") or "CHF"
    m2 = bien["montant"] / bien["surface"]
    famille = famille_de(bien.get("categorie"))

    def colle(r):
        return r["devise"] == devise and meme_lieu(r["lieu"], bien.get("localite")) and r["famille"] == famille

    demandes = [r["prix_m2"] for r in releves if colle(r) and r["nature"] == "annonce"]
    demandes += [r["prix_m2"] for r in _nos_biens(annonces, sauf=bien.get("reference")) if colle(r)]
    ventes = [r["prix_m2"] for r in releves if colle(r) and r["nature"] == "vente"]

    def place(valeurs, quoi):
        st = statistiques(valeurs)
        if st["n"] < POUR_CONCLURE:
            liste = f" ({', '.join(montant(x, devise) for x in sorted(valeurs))}/m²)" if valeurs else ""
            return f"- {quoi} : {st['n']} relevé{'s' if st['n'] > 1 else ''}, trop peu pour le situer{liste}."
        ecart = round((m2 - st["mediane"]) / st["mediane"] * 100)
        sous = sum(1 for x in valeurs if x < m2)
        ou = "à la médiane" if ecart == 0 else f"{abs(ecart)} % {'au-dessus' if ecart > 0 else 'en dessous'}"
        hors = f" ({st['ecartees']} hors norme laissé{'s' if st['ecartees'] > 1 else ''} hors de la médiane)" if st["ecartees"] else ""
        return f"- {quoi} : {len(valeurs)} relevés{hors}, médiane {montant(st['mediane'], devise)}/m² ; ce bien est {ou}, plus cher que {sous} sur {len(valeurs)}."

    return "\n".join([f"{bien.get('titre', '')} ({bien.get('localite', '')}) : {montant(m2, devise)}/m² demandés ({montant(bien['montant'], devise)} pour "
                      f"{round(bien['surface'])} m² habitables). Chiffres calculés, à rendre tels quels :",
                      place(demandes, "Prix demandés du même lieu et du même type (annonces relevées et nos autres biens)"),
                      place(ventes, "Ventes réalisées notées par le courtier")])


def mediane_zone(z: dict, releves: list[dict]) -> dict:
    """La médiane des prix demandés d'une zone dans le carnet, et le nombre de relevés (None en deçà de cinq)."""
    famille = famille_de(z.get("type"))
    v = [r["prix_m2"] for r in releves if r["nature"] == "annonce" and meme_lieu(r["lieu"], z["lieu"])
         and (not z.get("quartier") or meme_lieu(r.get("quartier"), z["quartier"])) and r["famille"] == famille]
    s = statistiques(v)
    return {"n": s["n"], "mediane": s.get("mediane") if s["n"] >= POUR_CONCLURE else None}


def nom_zone(z: dict) -> str:
    return f"{z['lieu']}{' ' + z['quartier'] if z.get('quartier') else ''}, {z.get('type') or 'villa'}"


def variation(avant: dict | None, apres: dict | None, z: dict, devise: str = "CHF") -> str | None:
    """Ce que dit la semaine d'une zone suivie : rien, ou la variation de sa médiane (5 % ou plus)."""
    if not (avant or {}).get("mediane") or not (apres or {}).get("mediane"):
        return None
    d = (apres["mediane"] - avant["mediane"]) / avant["mediane"]
    if abs(d) < VARIATION:
        return None
    return (f"Suivi {nom_zone(z)} : la médiane des prix demandés est passée de {montant(avant['mediane'], devise)} à {montant(apres['mediane'], devise)} "
            f"le m² ({'+' if d > 0 else ''}{round(d * 100)} %), sur {apres['n']} annonces relevées. Ce sont des prix demandés, pas des ventes.")
