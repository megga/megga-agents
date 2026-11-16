"""Les relations d'une agence (lots 7.4 et 7.5) : ce que le noyau branche pour les groupes d'outils partenaires,
visiteurs, vitrine, accueil et marche (noyau/app.py, noyau/agent.py). Les outils, les consignes et le Contexte de chaque tour, par
groupe ; les choix touchés traités sans le modèle ; ce qui se fait à l'heure dite."""

from __future__ import annotations

from .annonces import CONSIGNES as CONSIGNES_ANNONCES
from .annonces import Services
from .marche import CONSIGNES as CONSIGNES_MARCHE
from .marche import Marche
from .reseau import CONSIGNES_PARTENAIRES, CONSIGNES_VITRINE, PREFIXE_CHOIX, Reseau
from .visiteurs import CONSIGNES_ACCUEIL, CONSIGNES_VISITEURS, Visiteurs

GROUPES = ("partenaires", "visiteurs", "vitrine", "accueil", "marche")
CONSIGNES = {"annonces": CONSIGNES_ANNONCES, "partenaires": CONSIGNES_PARTENAIRES, "visiteurs": CONSIGNES_VISITEURS,
             "vitrine": CONSIGNES_VITRINE, "accueil": CONSIGNES_ACCUEIL, "marche": CONSIGNES_MARCHE}


def consignes_des_groupes(groupes) -> list[str]:
    """La façon de se servir des outils de ces groupes, dans l'ordre des groupes."""
    return [CONSIGNES[g] for g in groupes if g in CONSIGNES]


class Relations:
    def __init__(self, s: Services):
        self.reseau = Reseau(s)
        self.visiteurs = Visiteurs(s, self.reseau)
        # Le marché, si la configuration en a les régions (Config.marche).
        self.marche = Marche(s) if s.reglage_marche is not None else None
        self.choix = {PREFIXE_CHOIX: self.reseau.choisir}
        self.echeances = [self.visiteurs.suivre_questions, *([self.marche.echeance] if self.marche else [])]

    def outils(self, groupes) -> list:
        par_groupe = {"partenaires": self.reseau.outils_gestionnaire, "visiteurs": self.visiteurs.outils_gestionnaire,
                      "vitrine": self.reseau.outils_partenaire, "accueil": self.visiteurs.outils_visiteur}
        if "marche" in groupes:
            if self.marche is None:
                raise RuntimeError("outils du marché sans les régions de ses portails (Config.marche)")
            par_groupe["marche"] = self.marche.outils
        return [o for g in groupes if g in par_groupe for o in par_groupe[g]()]

    def contexte(self, groupes):
        """Le Contexte d'un tour pour une personne de ce rôle (async f(personne) -> texte), ou None."""
        par_groupe = {"partenaires": self.reseau.contexte_gestionnaire, "visiteurs": self.visiteurs.contexte_gestionnaire,
                      "vitrine": self.reseau.contexte_partenaire, "accueil": self.visiteurs.contexte_visiteur}
        if self.marche is not None:
            par_groupe["marche"] = self.marche.contexte
        fonctions = [par_groupe[g] for g in groupes if g in par_groupe]
        if not fonctions:
            return None

        async def contexte(personne: str) -> str:
            return "\n".join(t for t in [await f(personne) for f in fonctions] if t)

        return contexte
