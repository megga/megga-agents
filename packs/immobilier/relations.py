"""Les relations d'une agence (lot 7.4) : ce que le noyau branche pour les groupes d'outils partenaires, visiteurs,
vitrine et accueil (noyau/app.py, noyau/agent.py). Les outils, les consignes et le Contexte de chaque tour, par
groupe ; les choix touchés traités sans le modèle ; ce qui se fait à l'heure dite."""

from __future__ import annotations

from .annonces import CONSIGNES as CONSIGNES_ANNONCES
from .annonces import Services
from .reseau import CONSIGNES_PARTENAIRES, CONSIGNES_VITRINE, PREFIXE_CHOIX, Reseau
from .visiteurs import CONSIGNES_ACCUEIL, CONSIGNES_VISITEURS, Visiteurs

GROUPES = ("partenaires", "visiteurs", "vitrine", "accueil")
CONSIGNES = {"annonces": CONSIGNES_ANNONCES, "partenaires": CONSIGNES_PARTENAIRES, "visiteurs": CONSIGNES_VISITEURS,
             "vitrine": CONSIGNES_VITRINE, "accueil": CONSIGNES_ACCUEIL}


def consignes_des_groupes(groupes) -> list[str]:
    """La façon de se servir des outils de ces groupes, dans l'ordre des groupes."""
    return [CONSIGNES[g] for g in groupes if g in CONSIGNES]


class Relations:
    def __init__(self, s: Services):
        self.reseau = Reseau(s)
        self.visiteurs = Visiteurs(s, self.reseau)
        self.choix = {PREFIXE_CHOIX: self.reseau.choisir}
        self.echeances = [self.visiteurs.suivre_questions]

    def outils(self, groupes) -> list:
        par_groupe = {"partenaires": self.reseau.outils_gestionnaire, "visiteurs": self.visiteurs.outils_gestionnaire,
                      "vitrine": self.reseau.outils_partenaire, "accueil": self.visiteurs.outils_visiteur}
        return [o for g in groupes if g in par_groupe for o in par_groupe[g]()]

    def contexte(self, groupes):
        """Le Contexte d'un tour pour une personne de ce rôle (async f(personne) -> texte), ou None."""
        par_groupe = {"partenaires": self.reseau.contexte_gestionnaire, "visiteurs": self.visiteurs.contexte_gestionnaire,
                      "vitrine": self.reseau.contexte_partenaire, "accueil": self.visiteurs.contexte_visiteur}
        fonctions = [par_groupe[g] for g in groupes if g in par_groupe]
        if not fonctions:
            return None

        async def contexte(personne: str) -> str:
            return "\n".join(t for t in [await f(personne) for f in fonctions] if t)

        return contexte
