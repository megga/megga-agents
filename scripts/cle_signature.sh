#!/usr/bin/env bash
# Crée, une seule fois, la paire de clés qui signe l'image (cosign).
# La clé privée et son mot de passe vont dans les secrets GitHub du dépôt, sans s'afficher ;
# le mot de passe se saisit en masqué. Seule la clé publique reste : socle/cosign.pub, à commiter.
#   scripts/cle_signature.sh
set -euo pipefail
command -v cosign > /dev/null || { echo "cosign manque : brew install cosign"; exit 1; }
command -v gh > /dev/null || { echo "gh manque : brew install gh"; exit 1; }
racine=$(cd "$(dirname "$0")/.." && pwd)
[ -e "$racine/socle/cosign.pub" ] && { echo "socle/cosign.pub existe déjà : une seule paire de clés"; exit 1; }
dossier=$(mktemp -d)
trap 'rm -rf "$dossier"' EXIT
read -r -s -p "Mot de passe de la clé de signature : " mdp
echo
(cd "$dossier" && COSIGN_PASSWORD="$mdp" cosign generate-key-pair > /dev/null)
gh secret set COSIGN_PRIVATE_KEY --repo megga/megga-agents < "$dossier/cosign.key"
printf %s "$mdp" | gh secret set COSIGN_PASSWORD --repo megga/megga-agents
unset mdp
cp "$dossier/cosign.pub" "$racine/socle/cosign.pub"
echo "Clé publique : socle/cosign.pub (à commiter). La clé privée n'existe plus que dans les secrets du dépôt."
