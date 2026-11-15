"""Les garde-fous du noyau.

- Aucun secret ne sort : ce qui ressemble à une clé, un jeton ou une adresse de base
  est masqué avant l'envoi, même si le modèle l'a écrit.
- Un débit limité par personne : au-delà, une phrase polie au lieu d'un tour de
  modèle (protège la facture d'un client contre une boucle ou un abus).
"""

from __future__ import annotations

import re
import time
from collections import deque

MASQUE = "[masqué]"
_SECRETS = (
    re.compile(r"\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?)://\S+", re.I),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"\bEAA[A-Za-z0-9]{30,}"),
    re.compile(r"\b(?:xi|sk|pk|rk)_[A-Za-z0-9]{20,}"),
    # Une longue suite de lettres ET de chiffres, sans espace : un jeton, pas un mot ni un numéro.
    re.compile(r"\b(?=[A-Za-z0-9_\-]*[A-Za-z])(?=[A-Za-z0-9_\-]*\d)[A-Za-z0-9_\-]{40,}\b"),
)


def masquer_secrets(texte):
    if not isinstance(texte, str):
        return texte
    for r in _SECRETS:
        texte = r.sub(MASQUE, texte)
    return texte


def crochet_secrets(run_output) -> None:
    """Crochet de sortie d'Agno : masque les secrets de la réponse."""
    if isinstance(getattr(run_output, "content", None), str):
        run_output.content = masquer_secrets(run_output.content)


TROP = "Vous m'écrivez beaucoup en peu de temps. Je reprends dans quelques minutes."


class Debit:
    """Au plus `maximum` tours par personne sur `fenetre` secondes."""

    def __init__(self, maximum: int = 20, fenetre: float = 600):
        self.maximum, self.fenetre = maximum, fenetre
        self._tours: dict[str, deque] = {}
        self._prevenu: dict[str, float] = {}

    def permis(self, personne: str, maintenant: float | None = None) -> bool:
        maintenant = time.monotonic() if maintenant is None else maintenant
        q = self._tours.setdefault(personne, deque())
        while q and maintenant - q[0] > self.fenetre:
            q.popleft()
        if len(q) >= self.maximum:
            return False
        q.append(maintenant)
        return True

    def prevenir(self, personne: str, maintenant: float | None = None) -> bool:
        """Faut-il le dire ? Une fois par fenêtre, pas à chaque message."""
        maintenant = time.monotonic() if maintenant is None else maintenant
        if maintenant - self._prevenu.get(personne, -1e9) < self.fenetre:
            return False
        self._prevenu[personne] = maintenant
        return True
