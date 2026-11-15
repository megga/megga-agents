#!/usr/bin/env bash
# Pose les secrets d'un client (aujourd'hui : l'adresse de sa base) dans son objet,
# par la route d'administration de la porte. Saisie masquée, rien ne s'affiche.
#   scripts/secrets_client.sh <id-du-client> <adresse-de-la-porte>
# Exemple : scripts/secrets_client.sh essai-megga https://megga-agents.<compte>.workers.dev
set -euo pipefail
id="${1:?identifiant du client}"
porte="${2:?adresse de la porte}"
admin=$(security find-generic-password -a megga-agents -s megga-agents-admin -w)
read -r -s -p "Adresse de la base du client (postgresql://…) : " base
echo
corps=$(python3 -c 'import json,sys;print(json.dumps({"DATABASE_URL":sys.stdin.read().strip()}))' <<<"$base")
curl -sS --fail-with-body -X PUT "$porte/admin/clients/$id/secrets" \
  -H "authorization: Bearer $admin" -H "content-type: application/json" --data-binary @- <<<"$corps"
echo
unset admin base corps
