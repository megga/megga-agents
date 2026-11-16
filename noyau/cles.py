"""Les clés des logiciels, chez le client (installation hors Cloudflare) : créées et retirées dans sa propre base.

  python -m noyau.cles creer <logiciel> [par_minute]   une clé, montrée une seule fois
  python -m noyau.cles lister                          les clés, sans empreinte
  python -m noyau.cles retirer <id>                    la clé ne sert plus, tout de suite

Dans le conteneur de l'agent (DATABASE_URL ou DATABASE_URL_FILE) :
  docker compose exec agent python -m noyau.cles creer dossier-patients
  kubectl exec deploy/<agent> -- python -m noyau.cles creer dossier-patients
Chez MEGGA (Cloudflare), les clés se créent dans l'atelier (docs/atelier.md).
"""

from __future__ import annotations

import datetime as dt
import os
import sys

from . import api, stockage
from .environnement import charger

AIDE = __doc__.split("\n\n")[1]


def principal(args: list[str], env: dict[str, str] | None = None, ecrire=print) -> int:
    env = charger(dict(os.environ if env is None else env))
    if not args or args[0] not in ("creer", "lister", "retirer"):
        ecrire(AIDE)
        return 2
    if not env.get("DATABASE_URL"):
        ecrire("DATABASE_URL manquante")
        return 1
    cles = stockage.ClesApi(env["DATABASE_URL"])
    commande, reste = args[0], args[1:]
    if commande == "creer":
        if not reste or not api.LOGICIEL.fullmatch(reste[0]):
            ecrire("logiciel : un nom court, en minuscules (lettres, chiffres, tirets, 20 au plus)")
            return 2
        try:
            debit = api.par_minute(int(reste[1]) if len(reste) > 1 else None)
        except ValueError as e:
            ecrire(str(e) if str(e).startswith("par_minute") else f"par_minute : un nombre de 1 à {api.PAR_MINUTE_MAX}")
            return 2
        for _ in range(3):  # un identifiant déjà pris (très improbable) : on en tire un autre
            ident, cle, empreinte = api.nouvelle_cle()
            if cles.ajouter(ident, reste[0], empreinte, debit):
                break
        else:
            ecrire("La clé n'a pas pu être enregistrée : réessayez.")
            return 1
        ecrire(f"Clé {ident} pour {reste[0]} ({debit} messages par minute). Elle ne sera plus jamais montrée :")
        ecrire(cle)
        return 0
    if commande == "lister":
        for c in cles.lister():
            cree = dt.datetime.fromtimestamp(c["cree"]).strftime("%d.%m.%Y")
            etat = "retirée le " + dt.datetime.fromtimestamp(c["retiree"]).strftime("%d.%m.%Y") if c["retiree"] else "en service"
            ecrire(f"{c['id']}  {c['logiciel']}  {c['par_minute']}/min  créée le {cree}  {etat}")
        return 0
    if not reste or not api.IDENT_CLE.fullmatch(reste[0]):
        ecrire("retirer <id> : l'identifiant donné par lister")
        return 2
    if cles.retirer(reste[0]):
        ecrire(f"Clé {reste[0]} retirée : elle ne sert plus.")
        return 0
    ecrire("Aucune clé en service avec cet identifiant.")
    return 1


if __name__ == "__main__":
    sys.exit(principal(sys.argv[1:]))
