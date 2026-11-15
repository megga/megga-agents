#!/usr/bin/env bash
# Copie une version publiée (registre de MEGGA) dans le registre de Cloudflare, après en avoir
# vérifié la signature : Cloudflare ne tire pas depuis GitHub. Même image, même empreinte.
#   scripts/vers_cloudflare.sh 0.2.0
# Rend la référence à mettre dans porte/wrangler.jsonc (docs/deploiement.md).
set -euo pipefail
version="${1:?version publiée, par exemple 0.2.0}"
racine=$(cd "$(dirname "$0")/.." && pwd)
source_image="ghcr.io/megga/megga-agents:$version"
docker pull --platform linux/amd64 "$source_image" > /dev/null
empreinte=$(docker image inspect --format '{{index .RepoDigests 0}}' "$source_image")
"$racine/scripts/verifier_image.sh" "$empreinte"
docker tag "$source_image" "megga-agents:$version"
(cd "$racine/porte" && npx wrangler containers push "megga-agents:$version")
echo "copiée chez Cloudflare : megga-agents:$version (empreinte ${empreinte#*@})"
