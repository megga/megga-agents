#!/usr/bin/env bash
# Après un « wrangler deploy » : attend que les applications de conteneurs soient prêtes, puis fait
# redémarrer en douceur les conteneurs encore allumés, qui gardent sinon l'ancienne image jusqu'à
# leur sommeil (15 minutes sans message). Chaque conteneur finit d'abord ses tours en cours.
#   scripts/apres_deploiement.sh https://megga-agents.<sous-domaine>.workers.dev
set -euo pipefail
porte="${1:?adresse de la porte}"
racine=$(cd "$(dirname "$0")/.." && pwd)
for i in $(seq 1 60); do
  etats=$(cd "$racine/porte" && npx wrangler containers list 2> /dev/null | grep "megga-agents-" | awk -F'│' '{gsub(/ /,"",$4); print $4}' | sort -u)
  if [ "$etats" = "ready" ]; then break; fi
  [ "$i" = 60 ] && { echo "applications toujours pas prêtes : $etats"; exit 1; }
  echo "applications : $(echo "$etats" | tr '\n' ' ')… on attend"
  sleep 20
done
admin=$(security find-generic-password -a megga-agents -s megga-agents-admin -w)
# L'en-tête par un fichier de configuration de curl (printf est interne au shell) : jamais dans ps.
curl -sS --fail-with-body -X POST "$porte/admin/redemarrer" -K <(printf 'header = "authorization: Bearer %s"\n' "$admin")
echo
unset admin
