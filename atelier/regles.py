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

from noyau.config import METIERS, ZONES, Config, manques  # noqa: F401 (manques réexporté)

# Les réglages simples d'un client. « voix » : l'identifiant de la voix ElevenLabs, ou rien.
# « approbations » : quels outils attendent l'accord de son équipe, ou lui sont interdits (noyau/approbations.py) ;
# c'est le client qui porte le risque d'une action, c'est lui qui en décide.
# « transfert » : l'agent peut confier une conversation à son équipe (noyau/reprises.py).
# « leads » : le webhook de son CRM, où partent les fiches de ses leads (noyau/connecteurs.py).
# « modeles » : son modèle principal et son secours, parmi ceux du catalogue (lot 9.5).
# « mention_ia », « minutes_par_conversation » : sa conformité et le calcul de ce que l'agent lui fait gagner (lot 9.5).
CHAMPS_CLIENT = ("metier", "nom_agent", "voix", "ton", "outils", "approbations", "transfert", "leads", "modeles", "mention_ia",
                 "minutes_par_conversation")
# Les zones que la porte Cloudflare sert ; les autres passent par le pilotage (lot 6).
ZONES_PORTE = ("europe", "etats-unis")
MODELES = ("claude-sonnet-5-5", "claude-opus-5-5", "claude-haiku-5-5", "deepseek-v4-pro", "mistral-large-latest",
           "mistral-medium-latest")
# Ce qu'un client voit pour choisir (lot 9.5) : qui fait tourner le modèle, et où. Ce qu'il envoie au modèle quitte son
# infrastructure pour ce fournisseur (docs/plan.md) ; pour une donnée qui ne doit pas sortir de l'UE, Mistral.
MODELES_DETAIL = {
    "claude-sonnet-5-5": {"fournisseur": "Anthropic", "hebergement": "États-Unis"},
    "claude-opus-5-5": {"fournisseur": "Anthropic", "hebergement": "États-Unis"},
    "claude-haiku-5-5": {"fournisseur": "Anthropic", "hebergement": "États-Unis"},
    "deepseek-v4-pro": {"fournisseur": "DeepSeek", "hebergement": "Chine"},
    "mistral-large-latest": {"fournisseur": "Mistral AI", "hebergement": "Union européenne (France)"},
    "mistral-medium-latest": {"fournisseur": "Mistral AI", "hebergement": "Union européenne (France)"},
}


class Refus(Exception):
    def __init__(self, statut: int, message: str, details: Any = None):
        super().__init__(message)
        self.statut = statut
        self.message = message
        self.details = details


def offerts(env: dict) -> tuple[str, ...]:
    """Les modèles qu'un client peut choisir : ceux de Mistral AI une fois sa clé posée (MISTRAL_API_KEY)."""
    return tuple(m for m in MODELES if not m.startswith("mistral-") or env.get("MISTRAL_API_KEY"))


def catalogue(modeles: tuple[str, ...] = MODELES) -> dict:
    """Ce qu'une interface peut proposer, par rôle. Rien n'y est figé côté écrans."""
    return {
        "metiers": {m: list(o) for m, o in METIERS.items()},
        "champs_client": list(CHAMPS_CLIENT),
        "zones": list(ZONES),
        "zones_porte": list(ZONES_PORTE),
        "modeles": list(modeles),
        "modeles_detail": [{"id": m, **MODELES_DETAIL[m]} for m in modeles],
    }


# Les sous-objets de la configuration : un changement s'y fusionne clé par clé.
# Partout ailleurs (modeles_meta, voix.par_langue, outils...), la valeur donnée remplace
# l'ancienne en entier : c'est ainsi qu'on retire un modèle Meta ou une voix.
SOUS_OBJETS = ("modeles", "voix", "whatsapp", "roles", "gestion")


def fusionner(base: dict, changements: dict) -> dict:
    """Les changements par-dessus la base."""
    sortie = dict(base)
    for k, v in changements.items():
        if k in SOUS_OBJETS and isinstance(v, dict) and isinstance(sortie.get(k), dict):
            sortie[k] = {**sortie[k], **v}
        else:
            sortie[k] = v
    return sortie


def erreurs(e: ValidationError) -> list[dict]:
    from .messages import erreurs as en_francais

    return en_francais(e)


def appliquer(role: str, base: dict, changements: dict, zone_en_service: str | None, modeles: tuple[str, ...] = MODELES) -> Config:
    """La configuration qui résulte de ces changements, validée par le noyau.

    `zone_en_service` : la zone de la version en service, s'il y en a une. Changer de
    zone, c'est déménager le client (copie, vérification, bascule), pas un réglage.
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
        if "modeles" in ch:  # le client choisit ses modèles (lot 9.5), parmi ceux que MEGGA sait faire tourner
            if not isinstance(ch["modeles"], dict):
                raise Refus(400, "modeles : {principal, secours}")
            if autres := sorted(set(ch["modeles"]) - {"principal", "secours"}):  # le modèle de l'oral reste à MEGGA
                raise Refus(403, "réglages réservés à MEGGA : " + ", ".join(f"modeles.{k}" for k in autres))
            hors = [m for m in ch["modeles"].values() if m is not None and m not in modeles]
            if hors or ch["modeles"].get("principal", "x") is None:
                raise Refus(400, "modeles : choisissez dans la liste (" + ", ".join(modeles) + ") ; le secours peut être vide")
            # Derrière un modèle européen, le secours se choisit : celui d'avant pourrait tourner hors de l'UE.
            if str(ch["modeles"].get("principal")).startswith("mistral-") and "secours" not in ch["modeles"] \
                    and not str((base.get("modeles") or {}).get("secours")).startswith("mistral-"):
                raise Refus(400, "modeles : avec un modèle européen, choisissez aussi le secours (européen, un autre, ou aucun)")
        if "metier" in ch and "outils" not in ch:
            # Changer de métier retire les outils qu'il ne permet pas.
            permis = METIERS.get(ch["metier"], ())
            ch["outils"] = [o for o in base.get("outils", ()) if o in permis]
    if "id" in ch and ch["id"] != base.get("id"):
        raise Refus(400, "l'identifiant d'un client ne change pas")
    conf = valider(fusionner(base, ch))
    verifier_zone(conf, zone_en_service)
    return conf


def valider(donnees: Any) -> Config:
    """Une configuration validée par le noyau, ou un refus lisible (champ et message)."""
    try:
        return Config.model_validate(donnees)
    except ValidationError as e:
        raise Refus(422, "configuration invalide", erreurs(e)) from e


def verifier_zone(conf: Config, zone_en_service: str | None) -> None:
    if zone_en_service and conf.zone != zone_en_service:
        raise Refus(409, f"zone {conf.zone} au lieu de {zone_en_service} : changer de zone, c'est déménager le client, sur demande et hors de l'atelier")


def oui_non(valeur: Any, defaut: bool, nom: str) -> bool:
    """Un vrai booléen JSON : « false » en texte n'est pas faux, il est refusé."""
    if valeur is None:
        return defaut
    if not isinstance(valeur, bool):
        raise Refus(400, f"{nom} : true ou false")
    return valeur


def numero(valeur: Any, nom: str) -> int | None:
    if valeur is None:
        return None
    if isinstance(valeur, bool) or not isinstance(valeur, int) or valeur < 1:
        raise Refus(400, f"{nom} : un numéro de version")
    return valeur


def consignes_de_gabarit(consignes: str) -> bool:
    """Des consignes vides ou celles d'un modèle par métier : un client peut les remplacer par celles d'un autre modèle.
    Les consignes écrites sur mesure par MEGGA, non. Celles des modèles d'avant leurs fichiers (lot 10) restent
    celles d'un modèle."""
    from .gabarits import CONSIGNES_CONNUES

    return not (consignes or "").strip() or consignes in CONSIGNES_CONNUES


def reglages_de_megga(config: dict) -> dict:
    """Ce qu'un client ne règle pas lui-même dans une configuration : tout sauf CHAMPS_CLIENT (la voix choisie, pas ses
    autres réglages), et les consignes si MEGGA les a écrites sur mesure. Comparé avant qu'un client ne mette une version
    en service (relecture du 16.11.2026, I2) : revenir à une version d'avant ne doit pas changer le numéro WhatsApp, les
    modèles Meta, la gestion du site ni les consignes de MEGGA."""
    c = valider(config).model_dump(mode="json")
    sortie = {k: v for k, v in c.items() if k not in CHAMPS_CLIENT and k != "consignes"}
    sortie["voix"] = {k: v for k, v in c["voix"].items() if k != "voix"}
    # Le principal et le secours sont au client (lot 9.5) ; le modèle de l'oral et du fil reste à MEGGA.
    sortie["modeles"] = {k: v for k, v in c["modeles"].items() if k not in ("principal", "secours")}
    if not consignes_de_gabarit(c.get("consignes", "")):
        sortie["consignes"] = c["consignes"]
    return sortie
