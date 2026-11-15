"""Qui peut régler quoi.

Deux rôles :
  client  son seul agent, et seulement les réglages simples (CHAMPS_CLIENT) ;
  megga   tous les agents, tous les réglages, et la reprise en main d'un client.

Une nouvelle version part toujours d'une version existante : ce qu'un rôle ne peut
pas toucher est repris tel quel de cette base.
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from noyau.config import METIERS, ZONES, Config

# Les réglages simples d'un client. « voix » : l'identifiant de la voix ElevenLabs, ou rien.
CHAMPS_CLIENT = ("metier", "nom_agent", "voix", "ton", "outils")
# Les zones que la porte Cloudflare sert ; les autres passent par le pilotage (lot 6).
ZONES_PORTE = ("europe", "etats-unis")
MODELES = ("claude-sonnet-5-5", "claude-opus-5-5", "claude-haiku-5-5", "deepseek-v4-pro")


class Refus(Exception):
    def __init__(self, statut: int, message: str, details: Any = None):
        super().__init__(message)
        self.statut = statut
        self.message = message
        self.details = details


def catalogue() -> dict:
    """Ce qu'une interface peut proposer, par rôle. Rien n'y est figé côté écrans."""
    return {
        "metiers": {m: list(o) for m, o in METIERS.items()},
        "champs_client": list(CHAMPS_CLIENT),
        "zones": list(ZONES),
        "zones_porte": list(ZONES_PORTE),
        "modeles": list(MODELES),
    }


def fusionner(base: dict, changements: dict) -> dict:
    """Les changements par-dessus la base ; les objets se fusionnent clé par clé."""
    sortie = dict(base)
    for k, v in changements.items():
        if isinstance(v, dict) and isinstance(sortie.get(k), dict):
            sortie[k] = fusionner(sortie[k], v)
        else:
            sortie[k] = v
    return sortie


def erreurs(e: ValidationError) -> list[dict]:
    return [{"champ": ".".join(str(x) for x in err["loc"]), "message": err["msg"]} for err in e.errors()]


def appliquer(role: str, base: dict, changements: dict, zone_figee: bool) -> Config:
    """La configuration qui résulte de ces changements, validée par le noyau.

    `zone_figee` : le client a déjà été mis en service ; changer sa zone, c'est le
    déménager (copie, vérification, bascule), pas un réglage.
    """
    if not isinstance(changements, dict):
        raise Refus(400, "changements : un objet")
    ch = dict(changements)
    if role == "client":
        interdits = sorted(set(ch) - set(CHAMPS_CLIENT))
        if interdits:
            raise Refus(403, "réglages réservés à MEGGA : " + ", ".join(interdits))
        if "voix" in ch:
            if ch["voix"] is not None and not isinstance(ch["voix"], str):
                raise Refus(400, "voix : l'identifiant d'une voix, ou rien")
            ch["voix"] = {"voix": ch["voix"]}
        if "metier" in ch and "outils" not in ch:
            # Changer de métier retire les outils qu'il ne permet pas.
            permis = METIERS.get(ch["metier"], ())
            ch["outils"] = [o for o in base.get("outils", ()) if o in permis]
    if "id" in ch and ch["id"] != base.get("id"):
        raise Refus(400, "l'identifiant d'un client ne change pas")
    if zone_figee and "zone" in ch and ch["zone"] != base.get("zone"):
        raise Refus(409, "changer de zone, c'est déménager le client : sur demande, hors de l'atelier")
    try:
        return Config.model_validate(fusionner(base, ch))
    except ValidationError as e:
        raise Refus(422, "configuration invalide", erreurs(e)) from e


def manques(conf: Config) -> list[str]:
    """Ce qui empêche une configuration valide d'être mise en service."""
    m = []
    if "immobilier" in conf.outils and not conf.catalogue:
        m.append("le pack immobilier attend son catalogue (réglage de MEGGA)")
    return m
