"""Les garde-fous du noyau.

- Aucun secret ne sort : ce qui ressemble à une clé, un jeton ou une adresse de base
  est masqué avant l'envoi, même si le modèle l'a écrit.
- Un débit limité par personne : au-delà, une phrase polie au lieu d'un tour de
  modèle (protège la facture d'un client contre une boucle ou un abus).
- Un plafond par jour pour les personnes qui ne sont pas les gens du client (visiteurs,
  partenaires, logiciels) : par personne, et pour tout le client.
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
TROP_TU = "Tu m'écris beaucoup en peu de temps. Je reprends dans quelques minutes."


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

    def permis(self, personne: str, maintenant: float | None = None, maximum: int | None = None) -> bool:
        """`maximum` : celui du rôle de la personne (Role.par_dix_minutes), sinon celui du débit ; 0 : sans limite."""
        maximum = self.maximum if maximum is None else maximum
        if maximum == 0:
            return True
        maintenant = time.monotonic() if maintenant is None else maintenant
        self._comptes += 1
        if self._comptes % self.BALAYAGE == 0:
            self._balayer(maintenant)
        q = self._tours.setdefault(personne, deque())
        while q and maintenant - q[0] > self.fenetre:
            q.popleft()
        if len(q) >= maximum:
            return False
        q.append(maintenant)
        return True

    def libre(self, personne: str, maintenant: float | None = None, maximum: int | None = None) -> bool:
        """Un tour serait-il permis ? Sans le compter (permis le compte)."""
        maximum = self.maximum if maximum is None else maximum
        if maximum == 0:
            return True
        maintenant = time.monotonic() if maintenant is None else maintenant
        q = self._tours.get(personne)
        while q and maintenant - q[0] > self.fenetre:
            q.popleft()
        return not q or len(q) < maximum

    def rendre(self, personne: str) -> None:
        """Rend le dernier tour compté (un tour compté qui n'a finalement pas eu lieu)."""
        q = self._tours.get(personne)
        if q:
            q.pop()

    def attente(self, personne: str, maintenant: float | None = None, maximum: int | None = None) -> int:
        """Les secondes avant qu'un tour se libère (au moins 1) : l'en-tête Retry-After."""
        maximum = self.maximum if maximum is None else maximum
        maintenant = time.monotonic() if maintenant is None else maintenant
        q = self._tours.get(personne)
        if not maximum or not q or len(q) < maximum:
            return 1
        return max(1, math.ceil(q[0] + self.fenetre - maintenant))

    def prevenir(self, personne: str, maintenant: float | None = None) -> bool:
        """Faut-il le dire ? Une fois par fenêtre, pas à chaque message."""
        maintenant = time.monotonic() if maintenant is None else maintenant
        if maintenant - self._prevenu.get(personne, -1e9) < self.fenetre:
            return False
        self._prevenu[personne] = maintenant
        return True


TROP_JOUR = "J'ai beaucoup échangé aujourd'hui et je dois m'arrêter là. Je reprends demain."
PAR_PERSONNE_JOUR = 100  # tours par jour pour un visiteur, un partenaire, une personne venue par API
CLIENT_JOUR = 2000  # tours par jour pour tous ceux-là ensemble
SANS_PLAFOND = ("gestionnaire",)  # les gens du client ne sont jamais arrêtés


class Plafond:
    """Au plus PAR_PERSONNE_JOUR tours par personne et CLIENT_JOUR pour tout le client, par jour (UTC), hors des gens du
    client. Le débit (Debit) arrête une rafale ; le plafond arrête un abus lent, qui ferait sinon 2 880 tours de modèle par
    jour et par numéro (relecture du 16.11.2026, I7). En mémoire : un conteneur endormi repart à zéro, mais une personne
    qui écrit sans cesse le garde éveillé."""

    def __init__(self, par_personne: int = PAR_PERSONNE_JOUR, client: int = CLIENT_JOUR, par_role: dict[str, int] | None = None):
        """`par_role` : le plafond par personne d'un rôle (Role.par_jour). Un rôle sans plafond (les gestionnaires) qui en
        reçoit un est compté pour lui seul, jamais dans celui du client."""
        self.par_personne, self.client = par_personne, client
        self.par_role = dict(par_role or {})
        self._jour = ""
        self._personnes: dict[str, int] = {}
        self._total = 0
        self._prevenus: set[str] = set()
        self._signales: set[str] = set()

    def _aujourdhui(self, maintenant: float | None) -> None:
        jour = time.strftime("%Y-%m-%d", time.gmtime(time.time() if maintenant is None else maintenant))
        if jour != self._jour:
            self._jour, self._personnes, self._total, self._prevenus, self._signales = jour, {}, 0, set(), set()

    def libre(self, personne: str, role: str, maintenant: float | None = None) -> str | None:
        """None si un tour est permis ; sinon « personne » ou « client », le plafond atteint. Ne compte rien."""
        if role in SANS_PLAFOND and role not in self.par_role:
            return None
        self._aujourdhui(maintenant)
        if self._personnes.get(personne, 0) >= self.par_role.get(role, self.par_personne):
            return "personne"
        if role not in SANS_PLAFOND and self._total >= self.client:
            return "client"
        return None

    def compter(self, personne: str, role: str, maintenant: float | None = None) -> None:
        if role in SANS_PLAFOND and role not in self.par_role:
            return
        self._aujourdhui(maintenant)
        self._personnes[personne] = self._personnes.get(personne, 0) + 1
        if role not in SANS_PLAFOND:
            self._total += 1

    def prevenir(self, personne: str) -> bool:
        """Faut-il le dire à cette personne ? Une fois par jour."""
        if personne in self._prevenus:
            return False
        self._prevenus.add(personne)
        return True

    def signaler(self, quoi: str) -> bool:
        """Faut-il le noter au journal ? Une fois par jour et par plafond (« client », ou « personne »)."""
        if quoi in self._signales:
            return False
        self._signales.add(quoi)
        return True

    def attente(self, maintenant: float | None = None) -> int:
        """Les secondes jusqu'à minuit (UTC), pour Retry-After."""
        t = time.time() if maintenant is None else maintenant
        return max(1, 86400 - int(t) % 86400)
