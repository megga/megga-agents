"""Les commandes du pilote, chez le client : docker compose exec pilote python -m pilote <commande>

  ordres          les derniers ordres de MEGGA et, pour ceux qui attendent, ce qui changerait
  accepter <n>    accepte l'ordre n : l'agent le prend dans la minute, après ses tours en cours
  refuser <n>     refuse l'ordre n
  revenir         retire les configurations poussées par MEGGA : l'agent revient à client.yaml
  journal [n]     les n derniers événements du pilotage (30 par défaut)
  cle             la clé publique de l'installation, à remettre à MEGGA
  vivant          la sonde de santé du pilote
"""

from __future__ import annotations

import json
import os
import sys
import time

from noyau import config as configuration
from noyau import pilotage
from noyau.environnement import charger

from .service import Installation, en_vie

ETATS = {
    "attente_accord": "attend votre accord",
    "a_appliquer": "accepté, l'agent le prend dans la minute",
    "applique": "appliqué",
    "propose": "proposé",
    "refuse": "refusé",
    "echec": "en échec",
    "remplace": "remplacé",
    "retire": "retiré",
    "expire": "expiré",
}


def date(t: float) -> str:
    return time.strftime("%d.%m.%Y %H:%M", time.localtime(t))


def court(v) -> str:
    if isinstance(v, str):
        return f"(texte de {len(v)} caractères)" if len(v) > 60 else f"« {v} »"
    texte = json.dumps(v, ensure_ascii=False)
    return texte if len(texte) <= 60 else f"({len(texte)} caractères)"


def differences(avant: dict, apres: dict, prefixe: str = "") -> list[str]:
    """Ce qui change d'une configuration à l'autre, réglage par réglage."""
    lignes = []
    for k in sorted(set(avant) | set(apres)):
        a, b = avant.get(k), apres.get(k)
        if a == b:
            continue
        if isinstance(a, dict) and isinstance(b, dict):
            lignes += differences(a, b, f"{prefixe}{k}.")
        else:
            lignes.append(f"{prefixe}{k} : {court(a)} devient {court(b)}")
    return lignes


def ordres(inst: Installation, ecrire) -> None:
    conf, source = inst.config_servie()
    ecrire("Configuration servie : " + (f"version {source['version']} de MEGGA (ordre {source['ordre']})" if source
                                        else "le fichier client.yaml"))
    lignes = inst.ordres.lister(inst.client, 20)
    if not lignes:
        ecrire("Aucun ordre de MEGGA.")
    for l in lignes:
        o = pilotage.contenu(l["jeton"])  # vérifié à sa réception ; ici, seulement montré
        ecrire(f"Ordre {l['numero']} du {date(l['cree'])} : {Installation.decrire(o)}, {ETATS.get(l['etat'], l['etat'])}"
               + (f" ({l['detail']})" if l["detail"] and l["etat"] not in ("attente_accord", "propose") else ""))
        if l["etat"] == "attente_accord" and o.get("genre") == "config":
            nouvelle = (o.get("contenu") or {}).get("config") or {}
            for ligne in differences(conf.model_dump(mode="json"), nouvelle) or ["aucun réglage ne change"]:
                ecrire(f"    {ligne}")
            ecrire(f"    jusqu'au {date(l['expire'])} : python -m pilote accepter {l['numero']}, ou refuser {l['numero']}")
        elif l["etat"] == "propose":
            ecrire(f"    son installation viendra avec les mises à jour signées ; refuser : python -m pilote refuser {l['numero']}")


def main(argv: list[str], env: dict[str, str] | None = None, ecrire=print, cle_megga=None) -> int:
    env = charger(dict(os.environ if env is None else env))
    commande, args = (argv[0] if argv else ""), argv[1:]
    if commande == "cle":
        if not env.get("PILOTE_CLE"):
            ecrire("PILOTE_CLE manquante : la clé de l'installation")
            return 1
        ecrire(pilotage.en_texte(pilotage.cle_privee(env["PILOTE_CLE"]).public_key()))
        return 0
    if commande == "vivant":
        return 0 if en_vie(float(env.get("PILOTAGE_INTERVALLE") or 60)) else 1
    if commande not in ("ordres", "accepter", "refuser", "revenir", "journal"):
        ecrire(__doc__.strip())
        return 2
    source = env.get("CLIENT_CONFIG_FILE") or env.get("CLIENT_CONFIG")
    if not source or not env.get("DATABASE_URL"):
        ecrire("CLIENT_CONFIG_FILE et DATABASE_URL attendues")
        return 1
    inst = Installation(env["DATABASE_URL"], configuration.lire(source), cle_megga)
    if not inst.prete():
        ecrire("La base n'est pas encore prête : l'agent a-t-il démarré ?")
        return 1
    try:
        if commande == "ordres":
            ordres(inst, ecrire)
        elif commande == "journal":
            n = int(args[0]) if args and args[0].isdigit() else 30
            for e in inst.journal.lire(inst.client, n):
                ecrire(f"{date(e['quand'])}  {e['evenement']}" + (f", ordre {e['numero']}" if e["numero"] is not None else "")
                       + (f" : {e['detail']}" if e["detail"] else ""))
        elif commande == "revenir":
            ecrire(inst.revenir())
        else:
            if len(args) != 1 or not args[0].isdigit():
                ecrire(f"python -m pilote {commande} <numéro de l'ordre>")
                return 2
            ecrire((inst.accepter if commande == "accepter" else inst.refuser)(int(args[0])))
    except pilotage.PilotageRefuse as e:
        ecrire(f"Refusé : {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
