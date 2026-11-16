#!/usr/bin/env bash
# Pose les secrets d'un client (aujourd'hui : l'adresse de sa base) dans son objet,
# par la route d'administration de la porte. Rien ne s'affiche.
#   scripts/secrets_client.sh <id-du-client> <adresse-de-la-porte> [fichier-env]
# Avec un fichier (par exemple .env.local, écrit par « neon init »), l'adresse y est
# lue (DATABASE_URL_UNPOOLED, sinon DATABASE_URL) ; sans fichier, saisie masquée.
# Exemple : scripts/secrets_client.sh essai-megga https://megga-agents.<compte>.workers.dev .env.local
set -euo pipefail
id="${1:?identifiant du client}"
porte="${2:?adresse de la porte}"
fichier="${3:-}"
admin=$(security find-generic-password -a megga-agents -s megga-agents-admin -w)
if [ -n "$fichier" ]; then
  base=$(python3 - "$fichier" <<'PY'
import sys
v = {}
for l in open(sys.argv[1], encoding="utf-8"):
    if "=" in l and not l.lstrip().startswith("#"):
        k, x = l.split("=", 1)
        v[k.strip()] = x.strip().strip('"').strip("'")
print(v.get("DATABASE_URL_UNPOOLED") or v.get("DATABASE_URL") or "")
PY
)
  [ -n "$base" ] || { echo "aucune adresse de base dans $fichier"; exit 1; }
else
  read -r -s -p "Adresse de la base du client (postgresql://…) : " base
  echo
fi
corps=$(python3 -c 'import json,sys;print(json.dumps({"DATABASE_URL":sys.stdin.read().strip()}))' <<<"$base")
curl -sS --fail-with-body -X PUT "$porte/admin/clients/$id/secrets" \
  -K <(printf 'header = "authorization: Bearer %s"\n' "$admin") -H "content-type: application/json" --data-binary @- <<<"$corps"
echo
unset admin base corps
