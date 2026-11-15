"""La licence d'une installation chez le client, vérifiée sans appel extérieur.

Une licence est un jeton signé par MEGGA (Ed25519) : « <données>.<signature> », en base64.
Les données disent pour quel client et jusqu'à quand. La clé publique est dans l'image
(noyau/licence.pub) ; la clé privée ne quitte jamais le trousseau de MEGGA
(scripts/licence.py). Rien n'est appelé au dehors : l'installation n'a besoin d'aucun accès
à MEGGA pour démarrer.

  valide    jusqu'à la date prévue
  expiree   au-delà, l'agent tourne encore GRACE_JOURS jours et le signale (/sante, pilote)
  refusée   signature fausse, autre client, ou délai de grâce passé : le conteneur ne démarre pas
"""

from __future__ import annotations

import base64
import datetime as dt
import json
from pathlib import Path

GRACE_JOURS = 30
CLE_PUBLIQUE = Path(__file__).with_name("licence.pub")


class LicenceRefusee(RuntimeError):
    pass


def _b64(octets: bytes) -> str:
    return base64.urlsafe_b64encode(octets).decode().rstrip("=")


def _de_b64(texte: str) -> bytes:
    return base64.urlsafe_b64decode(texte + "=" * (-len(texte) % 4))


def cle_publique(pem: bytes | None = None):
    from cryptography.hazmat.primitives.serialization import load_pem_public_key

    if pem is None:
        if not CLE_PUBLIQUE.exists():
            raise LicenceRefusee("clé publique de licence absente de l'image (scripts/licence.py cle)")
        pem = CLE_PUBLIQUE.read_bytes()
    return load_pem_public_key(pem)


def emettre(donnees: dict, cle_privee) -> str:
    """Un jeton de licence signé (côté MEGGA seulement)."""
    brut = json.dumps(donnees, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return f"{_b64(brut)}.{_b64(cle_privee.sign(brut))}"


def etat_du_jour(licence: dict, aujourd_hui: dt.date | None = None) -> dict:
    """L'état d'une licence vérifiée au démarrage, recalculé chaque jour (un conteneur tourne longtemps)."""
    fin = dt.date.fromisoformat(licence["jusqu_au"])
    jour = aujourd_hui or dt.date.today()
    etat = "valide" if jour <= fin else "expiree" if jour <= fin + dt.timedelta(days=GRACE_JOURS) else "hors_delai"
    return {"jusqu_au": licence["jusqu_au"], "etat": etat}


def verifier(jeton: str, client: str, aujourd_hui: dt.date | None = None, cle=None) -> dict:
    """La licence de ce client, vérifiée ; lève LicenceRefusee sinon."""
    from cryptography.exceptions import InvalidSignature

    if not jeton or jeton.count(".") != 1:
        raise LicenceRefusee("licence absente ou mal formée (MEGGA_LICENCE)")
    partie, signature = jeton.split(".")
    try:
        brut, sig = _de_b64(partie), _de_b64(signature)
    except ValueError as e:
        raise LicenceRefusee("licence mal formée") from e
    try:
        (cle or cle_publique()).verify(sig, brut)
    except InvalidSignature as e:
        raise LicenceRefusee("licence non signée par MEGGA") from e
    donnees = json.loads(brut)
    if donnees.get("client") != client:
        raise LicenceRefusee(f"licence d'un autre client ({donnees.get('client')})")
    fin = dt.date.fromisoformat(donnees["jusqu_au"])
    jour = aujourd_hui or dt.date.today()
    if jour <= fin:
        etat = "valide"
    elif jour <= fin + dt.timedelta(days=GRACE_JOURS):
        etat = "expiree"
    else:
        raise LicenceRefusee(f"licence expirée le {fin.isoformat()}, délai de grâce passé")
    return {"client": client, "jusqu_au": fin.isoformat(), "etat": etat}
