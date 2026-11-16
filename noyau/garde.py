"""Les garde-fous du noyau.

- Aucun secret ne sort : ce qui ressemble à une clé, un jeton ou une adresse de base
  est masqué avant l'envoi, même si le modèle l'a écrit.
- Un débit limité par personne : au-delà, une phrase polie au lieu d'un tour de
  modèle (protège la facture d'un client contre une boucle ou un abus).
"""

from __future__ import annotations

import math
import re
import time
from collections import deque

MASQUE = "[masqué]"
_SECRETS = (
    re.compile(r"\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?)://\S+", re.I),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"\bEAA[A-Za-z0-9]{30,}"),
    re.compile(r"\b(?:xi|sk|pk|rk)_[A-Za-z0-9]{20,}"),
)
# Une longue suite de lettres ET de chiffres, sans espace : un jeton, pas un mot ni un numéro.
_JETON = re.compile(r"\b(?=[A-Za-z0-9_\-]*[A-Za-z])(?=[A-Za-z0-9_\-]*\d)[A-Za-z0-9_\-]{40,}\b")
# L'adresse d'une page, jusqu'à ses paramètres : l'identifiant d'une annonce y est long, avec des chiffres
# (« …/property/dubai-high-floor-2-br-apartment-… »), et n'est pas un jeton. Ses paramètres restent regardés.
_ADRESSE = re.compile(r"https?://[^\s?#]+", re.I)


def masquer_secrets(texte):
    if not isinstance(texte, str):
        return texte
    for r in _SECRETS:
        texte = r.sub(MASQUE, texte)
    # Le motif général, partout sauf dans le chemin d'une adresse.
    morceaux, fin = [], 0
    for m in _ADRESSE.finditer(texte):
        morceaux += [_JETON.sub(MASQUE, texte[fin:m.start()]), m.group(0)]
        fin = m.end()
    return "".join([*morceaux, _JETON.sub(MASQUE, texte[fin:])])


def crochet_secrets(run_output) -> None:
    """Crochet de sortie d'Agno : masque les secrets de la réponse."""
    if isinstance(getattr(run_output, "content", None), str):
        run_output.content = masquer_secrets(run_output.content)


TROP = "Vous m'écrivez beaucoup en peu de temps. Je reprends dans quelques minutes."


class Debit:
    """Au plus `maximum` tours par personne sur `fenetre` secondes."""

    BALAYAGE = 1000  # tous les combien de tours on oublie les personnes silencieuses

    def __init__(self, maximum: int = 20, fenetre: float = 600):
        self.maximum, self.fenetre = maximum, fenetre
        self._tours: dict[str, deque] = {}
        self._prevenu: dict[str, float] = {}
        self._comptes = 0

    def _balayer(self, maintenant: float) -> None:
        """Oublie ce qui est sorti de la fenêtre : une personne venue une fois ne reste pas en mémoire."""
        for personne in [p for p, q in self._tours.items() if not q or maintenant - q[-1] > self.fenetre]:
            del self._tours[personne]
        for personne in [p for p, t in self._prevenu.items() if maintenant - t >= self.fenetre]:
            del self._prevenu[personne]

    def permis(self, personne: str, maintenant: float | None = None) -> bool:
        maintenant = time.monotonic() if maintenant is None else maintenant
        self._comptes += 1
        if self._comptes % self.BALAYAGE == 0:
            self._balayer(maintenant)
        q = self._tours.setdefault(personne, deque())
        while q and maintenant - q[0] > self.fenetre:
            q.popleft()
        if len(q) >= self.maximum:
            return False
        q.append(maintenant)
        return True

    def libre(self, personne: str, maintenant: float | None = None) -> bool:
        """Un tour serait-il permis ? Sans le compter (permis le compte)."""
        maintenant = time.monotonic() if maintenant is None else maintenant
        q = self._tours.get(personne)
        while q and maintenant - q[0] > self.fenetre:
            q.popleft()
        return not q or len(q) < self.maximum

    def rendre(self, personne: str) -> None:
        """Rend le dernier tour compté (un tour compté qui n'a finalement pas eu lieu)."""
        q = self._tours.get(personne)
        if q:
            q.pop()

    def attente(self, personne: str, maintenant: float | None = None) -> int:
        """Les secondes avant qu'un tour se libère (au moins 1) : l'en-tête Retry-After."""
        maintenant = time.monotonic() if maintenant is None else maintenant
        q = self._tours.get(personne)
        if not q or len(q) < self.maximum:
            return 1
        return max(1, math.ceil(q[0] + self.fenetre - maintenant))

    def prevenir(self, personne: str, maintenant: float | None = None) -> bool:
        """Faut-il le dire ? Une fois par fenêtre, pas à chaque message."""
        maintenant = time.monotonic() if maintenant is None else maintenant
        if maintenant - self._prevenu.get(personne, -1e9) < self.fenetre:
            return False
        self._prevenu[personne] = maintenant
        return True
