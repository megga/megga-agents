"""Qui écrit à l'agent, et donc quel agent lui répond (Config.roles).

  gestionnaire  les gens du client : leur numéro et leur compte dans la gestion du site viennent du
                secret GESTIONNAIRES (JSON {"+41…": "compte"}), jamais de la configuration ;
  bloque        un numéro que le client a bloqué : jamais lu, jamais répondu ;
  partenaire    inscrit par le client (table megga_partenaires) ;
  visiteur      toute autre personne, si le rôle est réglé ; sinon personne ne lui répond
                (un refus poli, une fois par jour, s'il est réglé).

Sans rôles dans la configuration, tout le monde (sauf un numéro bloqué) parle au même agent : « public ».
Une personne venue d'un logiciel par API (noyau/api.py) est un visiteur.
"""

from __future__ import annotations

import json
import time

from .config import Config
from .whatsapp import chiffres

PUBLIC = "public"
UN_JOUR = 24 * 3600


def lire_gestionnaires(brut: str | None) -> dict[str, str]:
    """Le secret GESTIONNAIRES : {numéro: compte}. Illisible ou vide : aucun gestionnaire (et une erreur claire)."""
    if not brut:
        return {}
    try:
        donnees = json.loads(brut)
    except ValueError as e:
        raise ValueError("GESTIONNAIRES : du JSON {\"+41…\": \"compte\"}") from e
    if not isinstance(donnees, dict):
        raise ValueError("GESTIONNAIRES : du JSON {\"+41…\": \"compte\"}")
    sortie = {}
    for numero, compte in donnees.items():
        n = chiffres(numero)
        if not 6 <= len(n) <= 20 or not isinstance(compte, str) or not compte.strip():
            raise ValueError("GESTIONNAIRES : un numéro et un compte par entrée")
        sortie[f"+{n}"] = compte.strip()
    return sortie


class Personnes:
    """Le rôle de chaque personne, d'après la configuration, le secret des gestionnaires et la base."""

    def __init__(self, conf: Config, gestionnaires: dict[str, str] | None = None, bloques=None, partenaires=None):
        self.conf = conf
        self.roles = conf.les_roles()
        self.gestionnaires = gestionnaires or {}
        self.bloques = bloques  # stockage.Bloques
        self.partenaires = partenaires  # stockage.Partenaires
        self._refuses: dict[str, float] = {}

    def compte(self, personne: str) -> str | None:
        """Le compte d'un gestionnaire dans la gestion du site, ou None."""
        return self.gestionnaires.get(f"+{chiffres(personne)}") if not str(personne).startswith("api:") else None

    def role(self, personne: str) -> str | None:
        """« gestionnaire », « partenaire », « visiteur », « public » (sans rôles), « bloque », ou None (pas servi).

        Lit la base (bloqués, partenaires) : à appeler hors de la boucle (asyncio.to_thread).
        """
        par_api = str(personne).startswith("api:")
        if not par_api and self.bloques is not None and self.bloques.bloque(personne):
            return "bloque"
        if not self.roles:
            return PUBLIC
        if self.compte(personne) and "gestionnaire" in self.roles:
            return "gestionnaire"
        if not par_api and "partenaire" in self.roles and self.partenaires is not None and self.partenaires.inscrit(personne):
            return "partenaire"
        return "visiteur" if "visiteur" in self.roles else None

    def refuser(self, personne: str, maintenant: float | None = None) -> str | None:
        """Le refus poli à envoyer à une personne qu'aucun rôle ne sert : une fois par jour au plus, s'il est réglé."""
        texte = self.conf.roles.refus if self.conf.roles else None
        if not texte:
            return None
        maintenant = time.time() if maintenant is None else maintenant
        if maintenant - self._refuses.get(personne, -1e12) < UN_JOUR:
            return None
        self._refuses[personne] = maintenant
        if len(self._refuses) > 5000:  # oublie les plus anciens
            for p in sorted(self._refuses, key=self._refuses.get)[:1000]:
                del self._refuses[p]
        return texte
