"""Les commandes du pilote, chez le client : docker compose exec pilote python -m pilote <commande>

  ordres          les derniers ordres de MEGGA et, pour ceux qui attendent, ce qui changerait
  accepter <n>    accepte l'ordre n : l'agent le prend dans la minute, après ses tours en cours
  refuser <n>     refuse l'ordre n
  revenir         retire les configurations poussées par MEGGA : l'agent revient à client.yaml
  journal [n]     les n derniers événements du pilotage (30 par défaut)
  sauvegardes     les sauvegardes de la base faites avant chaque mise à jour de l'image
  cle             la clé publique de l'installation, à remettre à MEGGA
  vivant          la sonde de santé du pilote
  image --actuelle <image>   pour le script de l'hôte (installation/compose/mettre_a_jour.sh) : rien,
                  attendre, installer <image> ou revenir <image>
"""

from __future__ import annotations

import json
import os
import re
import sys
import time

ETATS = {
    "attente_accord": "attend votre accord",
    "a_appliquer": "accepté, en cours",
    "applique": "appliqué",
    "propose": "proposé",
    "refuse": "refusé",
    "echec": "en échec",
    "remplace": "remplacé",
    "retire": "retiré",
    "expire": "expiré",
}


def date(t: float) -> str:
    """L'heure du serveur, avec son fuseau (UTC dans un conteneur sans réglage)."""
    return time.strftime("%d.%m.%Y %H:%M %Z", time.localtime(t))


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


def ordres(inst, ecrire) -> None:
    from noyau import pilotage
    from noyau.config import Config

    from .service import Installation

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
            # L'ordre ne porte que les réglages qui s'écartent des valeurs par défaut : comparé une fois complété.
            try:
                nouvelle = Config.model_validate((o.get("contenu") or {}).get("config")).model_dump(mode="json")
            except ValueError:
                nouvelle = {}
            for ligne in differences(conf.model_dump(mode="json"), nouvelle) or ["aucun réglage ne change"]:
                ecrire(f"    {ligne}")
            ecrire(f"    jusqu'au {date(l['expire'])} : python -m pilote accepter {l['numero']}, ou refuser {l['numero']}")
        elif l["etat"] == "attente_accord" and o.get("genre") == "image":
            ecrire(f"    {(o.get('contenu') or {}).get('image')}")
            ecrire("    signature vérifiée, base sauvegardée, puis l'agent mis à jour ; retour à l'image d'avant si /sante échoue")
            ecrire(f"    jusqu'au {date(l['expire'])} : python -m pilote accepter {l['numero']}, ou refuser {l['numero']}")
        elif l["etat"] == "propose":
            ecrire(f"    {(o.get('contenu') or {}).get('image')}")
            ecrire("    à installer à la main (MISES_A_JOUR=non : docs/installation-client.md) ; "
                   f"refuser : python -m pilote refuser {l['numero']}")


def main(argv: list[str], env: dict[str, str] | None = None, ecrire=print, cle_megga=None) -> int:
    commande, args = (argv[0] if argv else ""), argv[1:]
    if commande == "vivant":  # la sonde, chaque minute : rien d'autre à charger
        from .sonde import en_vie

        return 0 if en_vie((os.environ if env is None else env).get("PILOTAGE_INTERVALLE")) else 1
    from noyau import config as configuration
    from noyau import pilotage
    from noyau.environnement import charger

    from . import image as images
    from .service import Installation, MisesAJour, delai, source_config

    env = charger(dict(os.environ if env is None else env))
    if commande == "cle":
        if not env.get("PILOTE_CLE"):
            ecrire("PILOTE_CLE manquante : la clé de l'installation")
            return 1
        ecrire(pilotage.en_texte(pilotage.cle_privee(env["PILOTE_CLE"]).public_key()))
        return 0
    if commande not in ("ordres", "accepter", "refuser", "revenir", "journal", "sauvegardes", "image"):
        ecrire(__doc__.strip())
        return 2
    if not (env.get("CLIENT_CONFIG") or env.get("CLIENT_CONFIG_FILE")) or not env.get("DATABASE_URL"):
        ecrire("CLIENT_CONFIG_FILE et DATABASE_URL attendues")
        return 1
    if commande == "accepter" and (env.get("PILOTAGE") or "non").strip().lower() not in ("suivi", "complet"):
        # Sans pilote qui tourne, personne ne verrait une configuration que l'agent ne prend pas (10 minutes).
        ecrire("Refusé : accepter un ordre demande PILOTAGE=suivi ou complet (le pilote surveille son application).")
        return 1
    if commande == "image" and (env.get("PILOTAGE") or "non").strip().lower() not in ("suivi", "complet"):
        ecrire("rien")
        return 0
    inst = Installation(env["DATABASE_URL"], configuration.lire(source_config(env)), cle_megga,
                        maj=MisesAJour.depuis(env), delai=delai(env))
    if not inst.prete():
        ecrire("La base n'est pas encore prête : l'agent a-t-il démarré ?")
        return 1
    try:
        if commande == "ordres":
            ordres(inst, ecrire)
        elif commande == "journal":
            n = min(int(args[0]), 1000) if args and re.fullmatch(r"[0-9]{1,6}", args[0]) else 30
            for e in inst.journal.lire(inst.client, n):
                ecrire(f"{date(e['quand'])}  {e['evenement']}" + (f", ordre {e['numero']}" if e["numero"] is not None else "")
                       + (f" : {e['detail']}" if e["detail"] else ""))
        elif commande == "revenir":
            ecrire(inst.revenir())
        elif commande == "sauvegardes":
            liste = images.sauvegardes(inst.maj.sauvegardes, inst.client)
            for f in liste:
                ecrire(f"{f}  {f.stat().st_size / 1e6:.1f} Mo")
            if not liste:
                ecrire(f"Aucune sauvegarde dans {inst.maj.sauvegardes}.")
        elif commande == "image":
            if len(args) != 2 or args[0] != "--actuelle" or len(args[1]) > 300:
                ecrire("python -m pilote image --actuelle <image de l'agent>")
                return 2
            ecrire(inst.image_cible(args[1].strip()))
        else:
            if len(args) != 1 or not re.fullmatch(r"[0-9]{1,9}", args[0]):
                ecrire(f"python -m pilote {commande} <numéro de l'ordre>")
                return 2
            ecrire((inst.accepter if commande == "accepter" else inst.refuser)(int(args[0])))
    except pilotage.PilotageRefuse as e:
        ecrire(f"Refusé : {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
