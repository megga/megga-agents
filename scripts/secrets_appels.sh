#!/usr/bin/env bash
# Pose les clés des appels WhatsApp d'un client dans son objet (noyau/appels.py, docs/appels.md), par la route
# d'administration de la porte. Rien ne s'affiche.
#   APPELS_CLE        tirée du trousseau (megga-agents / megga-agents-appels-<id>), la même que le secret « Bearer … »
#                     d'ElevenLabs qui signe le webhook de début et les outils
#   APPELS_SIGNATURE  le secret de signature du webhook de fin, copié du tableau de bord d'ElevenLabs, saisi masqué
#                     (Entrée seule : celui en place reste)
# Le conteneur du client redémarre : ses tours en cours finissent d'abord.
#   scripts/secrets_appels.sh <id-du-client> <adresse-de-la-porte>
# Exemple : scripts/secrets_appels.sh four-seasons-properties https://megga-agents.api-963.workers.dev
set -euo pipefail
id="${1:?identifiant du client}"
porte="${2:?adresse de la porte}"
admin=$(security find-generic-password -a megga-agents -s megga-agents-admin -w)
cle=$(security find-generic-password -a megga-agents -s "megga-agents-appels-$id" -w)
read -r -s -p "Secret de signature du webhook de fin d'ElevenLabs (Entrée : inchangé) : " signature
echo
corps=$(CLE="$cle" SIGNATURE="$signature" python3 -c 'import json, os
d = {"APPELS_CLE": os.environ["CLE"]}
s = os.environ["SIGNATURE"].strip()
if s:
    d["APPELS_SIGNATURE"] = s
print(json.dumps(d))')
curl -sS --fail-with-body -X PUT "$porte/admin/clients/$id/secrets" \
  -K <(printf 'header = "authorization: Bearer %s"\n' "$admin") -H "content-type: application/json" --data-binary @- <<<"$corps"
echo
unset admin cle signature corps
