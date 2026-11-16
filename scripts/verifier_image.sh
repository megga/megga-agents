#!/usr/bin/env bash
# Vérifie qu'une image a bien été signée par MEGGA (clé publique socle/cosign.pub).
# Sert à MEGGA avant un déploiement, et au client avant d'installer une image à la main (le pilote, lui,
# vérifie la signature lui-même, pilote/image.py).
#   scripts/verifier_image.sh ghcr.io/megga/megga-agents@sha256:<empreinte>
set -euo pipefail
image="${1:?image, de préférence par empreinte (@sha256:…)}"
racine=$(cd "$(dirname "$0")/.." && pwd)
cosign verify --key "$racine/socle/cosign.pub" --insecure-ignore-tlog=true "$image" > /dev/null
echo "signée par MEGGA : $image"
