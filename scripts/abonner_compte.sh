#!/usr/bin/env bash
# Abonne l'app du jeton au compte WhatsApp donné (POST /<compte>/subscribed_apps),
# puis montre les apps abonnées. Le jeton se saisit masqué, rien ne s'affiche.
#   scripts/abonner_compte.sh <id-du-compte-whatsapp>
set -euo pipefail
compte="${1:?identifiant du compte WhatsApp}"
read -r -s -p "Jeton d'utilisateur système (META_TOKEN) : " jeton
echo
# Le jeton par un fichier de configuration de curl (printf est interne au shell) : jamais dans ps.
entete() { printf 'header = "authorization: Bearer %s"\n' "$jeton"; }
curl -sS -X POST "https://graph.facebook.com/v26.0/$compte/subscribed_apps" -K <(entete)
echo
curl -sS "https://graph.facebook.com/v26.0/$compte/subscribed_apps" -K <(entete) | python3 -c 'import json,sys;d=json.load(sys.stdin);print([a.get("whatsapp_business_api_data",{}).get("name") for a in d.get("data",[])] or d)'
unset jeton
