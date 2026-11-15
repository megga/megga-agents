#!/usr/bin/env bash
# Vérifie qu'une image a bien été signée par MEGGA (clé publique socle/cosign.pub).
# Sert à MEGGA avant un déploiement, au pilote et au client avant une mise à jour.
#   scripts/verifier_image.sh ghcr.io/megga/megga-agents@sha256:<empreinte>
set -euo pipefail
image="${1:?image, de préférence par empreinte (@sha256:…)}"
racine=$(cd "$(dirname "$0")/.." && pwd)
cosign verify --key "$racine/socle/cosign.pub" --insecure-ignore-tlog=true "$image" > /dev/null
echo "signée par MEGGA : $image"
