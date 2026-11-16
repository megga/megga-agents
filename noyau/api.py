"""L'entrée par API : un logiciel (dossier médical, site) envoie un message à l'agent et reçoit sa réponse,
sans WhatsApp ni Meta.

  POST /api/messages   {"personne": "...", "texte": "..."}  ->  {"reponse": "..."}
  Authorization: Bearer mga_...

- Une clé par logiciel, créée par l'atelier (Cloudflare) ou chez le client (python -m noyau.cles) ; montrée
  une fois, seule son empreinte est gardée, dans la base du client (stockage.ClesApi) ; révocable.
- La personne : un identifiant opaque choisi par le logiciel, jamais un numéro de téléphone. L'agent s'en
  souvient sous « api:<logiciel>:<identifiant> » : deux logiciels du même client ne mêlent pas leurs gens.
- Le même tour que WhatsApp (mémoire, outils, garde-fous), sans regroupement d'attente ; pas de rappels.
- Un débit par clé (par minute), en plus de celui de chaque personne.
"""

from __future__ import annotations

import hashlib
import re
import secrets
import time

from .garde import Debit

PREFIXE = "mga_"
CLE = re.compile(r"^mga_[A-Za-z0-9_-]{43}$")
EMPREINTE = re.compile(r"^[0-9a-f]{64}$")
IDENT_CLE = re.compile(r"^[0-9a-f]{12}$")
LOGICIEL = re.compile(r"^[a-z0-9][a-z0-9-]{0,19}$")
# Un identifiant opaque, avec au moins une lettre : un numéro de téléphone ne passe pas, même écrit autrement.
IDENTIFIANT = re.compile(r"^(?=.*[A-Za-z])[A-Za-z0-9._-]{1,40}$")
TEXTE_MAX = 4000
CORPS_MAX = 16 * 1024
PAR_MINUTE = 30  # par défaut, pour une clé
PAR_MINUTE_MAX = 600


def nouvelle_cle() -> tuple[str, str, str]:
    """Une clé neuve : (identifiant, clé à montrer une fois, empreinte à garder)."""
    cle = PREFIXE + secrets.token_urlsafe(32)
    return secrets.token_hex(6), cle, empreinte(cle)


def empreinte(cle: str) -> str:
    return hashlib.sha256(cle.encode()).hexdigest()


def personne_interne(logiciel: str, identifiant: str) -> str:
    return f"api:{logiciel}:{identifiant}"


def par_api(personne: str) -> bool:
    return str(personne or "").startswith("api:")


def par_minute(valeur, defaut: int = PAR_MINUTE) -> int:
    """Le débit d'une clé, en tours par minute (1 à 600)."""
    if valeur is None:
        return defaut
    if isinstance(valeur, bool) or not isinstance(valeur, int) or not 1 <= valeur <= PAR_MINUTE_MAX:
        raise ValueError(f"par_minute : un nombre de 1 à {PAR_MINUTE_MAX}")
    return valeur


class DebitCles:
    """Au plus `par_minute` tours par clé sur une minute (en mémoire : un conteneur par client)."""

    def __init__(self):
        self._debits: dict[str, Debit] = {}

    def permis(self, cle: dict, maintenant: float | None = None) -> bool:
        d = self._debits.get(cle["id"])
        if d is None or d.maximum != cle["par_minute"]:
            d = self._debits[cle["id"]] = Debit(cle["par_minute"], 60)
        return d.permis(cle["id"], maintenant)

    def attente(self, cle: dict, maintenant: float | None = None) -> int:
        """Les secondes avant qu'un tour se libère (Retry-After)."""
        d = self._debits.get(cle["id"])
        q = d._tours.get(cle["id"]) if d else None
        if not q:
            return 1
        maintenant = time.monotonic() if maintenant is None else maintenant
        return max(1, int(q[0] + 60 - maintenant + 0.999))
