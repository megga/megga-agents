#!/usr/bin/env bash
# Copie une version publiée (registre de MEGGA) dans le registre de Cloudflare, après en avoir
# vérifié la signature : Cloudflare ne tire pas depuis GitHub. Même image, même empreinte.
#   scripts/vers_cloudflare.sh 0.2.0
# Pour l'instant, wrangler deploy construit encore l'image depuis socle/Dockerfile ; cette copie
# servira quand Cloudflare passera à l'image publiée (docs/deploiement.md).
set -euo pipefail
version="${1:?version publiée, par exemple 0.2.0}"
racine=$(cd "$(dirname "$0")/.." && pwd)
source_image="ghcr.io/megga/megga-agents:$version"
docker pull --platform linux/amd64 "$source_image" > /dev/null
# L'empreinte dans le registre de MEGGA, pas celle d'une copie déjà faite ailleurs.
empreinte=$(docker image inspect --format '{{range .RepoDigests}}{{println .}}{{end}}' "$source_image" | grep '^ghcr.io/megga/megga-agents@' | head -1)
[ -n "$empreinte" ] || { echo "empreinte introuvable dans ghcr.io pour $source_image"; exit 1; }
"$racine/scripts/verifier_image.sh" "$empreinte"
docker tag "$source_image" "megga-agents:$version"
(cd "$racine/porte" && npx wrangler containers push "megga-agents:$version")
echo "copiée chez Cloudflare : megga-agents:$version (empreinte ${empreinte#*@})"
