#!/usr/bin/env bash
# Abonne l'app du jeton au compte WhatsApp donné (POST /<compte>/subscribed_apps),
# puis montre les apps abonnées. Le jeton se saisit masqué, rien ne s'affiche.
#   scripts/abonner_compte.sh <id-du-compte-whatsapp>
set -euo pipefail
compte="${1:?identifiant du compte WhatsApp}"
read -r -s -p "Jeton d'utilisateur système (META_TOKEN) : " jeton
echo
curl -sS -X POST "https://graph.facebook.com/v26.0/$compte/subscribed_apps" -H "authorization: Bearer $jeton"
echo
curl -sS "https://graph.facebook.com/v26.0/$compte/subscribed_apps" -H "authorization: Bearer $jeton" | python3 -c 'import json,sys;d=json.load(sys.stdin);print([a.get("whatsapp_business_api_data",{}).get("name") for a in d.get("data",[])] or d)'
unset jeton
