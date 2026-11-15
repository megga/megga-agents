"""Les outils immobiliers de l'agent : chercher des biens, en voir un en détail.

Rien n'est inventé : l'agent ne connaît que ce que les outils lui rendent, et un
prix absent se dit « prix sur demande ».
"""

from __future__ import annotations

from .catalogue import Bien, Catalogue

MAX_RESULTATS = 5


def montant(v: float | None, devise: str, periode: str | None = None) -> str:
    if v is None:
        return "prix sur demande"
    entier = f"{round(v):,}".replace(",", "’")
    return f"{devise} {entier}" + (f" par {periode}" if periode else "")


def resume(b: Bien) -> str:
    chiffres = [x for x in (
        f"{b.chambres} chambres" if b.chambres else "",
        f"{round(b.surface)} m²" if b.surface else "",
    ) if x]
    return f"{b.ref} : {b.titre}, {b.commune}, {montant(b.prix, b.devise, b.periode)}" + (f", {', '.join(chiffres)}" if chiffres else "")


def detail(b: Bien) -> str:
    lignes = [
        f"Référence : {b.ref}",
        f"Titre : {b.titre}",
        f"Type : {b.type}, {b.transaction}",
        f"Lieu : {b.commune}" + (f", {b.region}" if b.region else "") + f" ({b.pays})",
        f"Prix : {montant(b.prix, b.devise, b.periode)}",
    ]
    for nom, v, unite in (("Chambres", b.chambres, ""), ("Salles de bain", b.salles_de_bain, ""),
                          ("Surface habitable", b.surface, " m²"), ("Terrain", b.terrain, " m²")):
        if v:
            lignes.append(f"{nom} : {round(v)}{unite}")
    if b.atouts:
        lignes.append("Atouts : " + ", ".join(b.atouts))
    if b.description:
        lignes.append("Description : " + b.description)
    if b.lien:
        lignes.append("Fiche en ligne : " + b.lien)
    return "\n".join(lignes)


def _liste(v) -> list[str]:
    if not v:
        return []
    if isinstance(v, str):
        return [x for x in v.replace(";", ",").split(",") if x.strip()]
    return [str(x) for x in v]


def outils(catalogue: Catalogue):
    def chercher_biens(transaction: str = "", types: str = "", communes: str = "", budget_min: float = 0,
                       budget_max: float = 0, chambres_min: int = 0, surface_min: float = 0, mots: str = "") -> str:
        """Cherche des biens de l'agence selon les critères de la personne. Laisse vide un critère non donné.

        Args:
            transaction: « vente » ou « location ».
            types: types séparés par des virgules (appartement, maison, villa, chalet, attique, terrain, commercial).
            communes: communes ou régions séparées par des virgules.
            budget_min: prix minimum.
            budget_max: prix maximum.
            chambres_min: nombre minimum de chambres.
            surface_min: surface habitable minimum, en m².
            mots: mots à retrouver (vue lac, piscine, jardin...).
        """
        t = transaction.strip().lower() or None
        if t not in (None, "vente", "location"):
            raise ValueError("transaction : vente ou location")
        trouves = catalogue.chercher(
            transaction=t, types=_liste(types), communes=_liste(communes),
            budget_min=budget_min or None, budget_max=budget_max or None,
            chambres_min=chambres_min or None, surface_min=surface_min or None, mots=mots,
        )
        if not trouves:
            return "Aucun bien ne correspond à ces critères."
        tete = f"{len(trouves)} bien(s) trouvé(s)" + (f", les {MAX_RESULTATS} premiers :" if len(trouves) > MAX_RESULTATS else " :")
        return "\n".join([tete, *(resume(b) for b in trouves[:MAX_RESULTATS])])

    def voir_bien(reference: str) -> str:
        """Le détail d'un bien de l'agence, d'après sa référence.

        Args:
            reference: la référence du bien (donnée par chercher_biens).
        """
        b = catalogue.bien(reference)
        return detail(b) if b else "Aucun bien avec cette référence."

    return [chercher_biens, voir_bien]
