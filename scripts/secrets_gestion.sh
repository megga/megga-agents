#!/usr/bin/env bash
# Pose les secrets de la gestion d'un client (lot 7.1) dans son objet, par la route d'administration de
# la porte : la clé partagée avec son site (GESTION_CLE) et ses gestionnaires (GESTIONNAIRES, en JSON
# {"+41…": "compte de gestion"}) ; et, si on la donne, la clé de son site pour /site/… (SITE_CLE, lot 7.4).
# Saisie masquée, rien ne s'affiche ; le conteneur redémarre en douceur.
#   scripts/secrets_gestion.sh <id-du-client> <adresse-de-la-porte>
set -euo pipefail
id="${1:?identifiant du client}"
porte="${2:?adresse de la porte}"
admin=$(security find-generic-password -a megga-agents -s megga-agents-admin -w)
read -r -s -p "Clé de la gestion du site (GESTION_CLE) : " cle
echo
read -r -s -p "Gestionnaires, en JSON {\"+41…\": \"compte\"} : " gestionnaires
echo
read -r -s -p "Clé du site pour /site/… (SITE_CLE, 32 caractères au moins ; vide pour aucune) : " site
echo
corps=$(CLE="$cle" GESTIONNAIRES="$gestionnaires" SITE="$site" python3 -c '
import json, os, sys
g = json.loads(os.environ["GESTIONNAIRES"])
if not isinstance(g, dict) or not g:
    sys.exit("GESTIONNAIRES : un objet JSON {numéro: compte}")
s = {"GESTION_CLE": os.environ["CLE"], "GESTIONNAIRES": json.dumps(g)}
if os.environ["SITE"]:
    if len(os.environ["SITE"]) < 32:
        sys.exit("SITE_CLE : 32 caractères au moins")
    s["SITE_CLE"] = os.environ["SITE"]
print(json.dumps(s))')
curl -sS --fail-with-body -X PUT "$porte/admin/clients/$id/secrets" \
  -H "authorization: Bearer $admin" -H "content-type: application/json" --data-binary @- <<<"$corps"
echo
unset admin cle gestionnaires site corps
