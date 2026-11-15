#!/usr/bin/env bash
# Les mises à jour signées de l'image, sous Docker Compose (docs/installation-client.md, « Les mises à jour »).
#
# Le pilote décide de tout : la signature de l'image (clé de MEGGA), l'accord du client, la sauvegarde de
# la base, le contrôle de santé et le retour à l'image d'avant. Il n'a aucun accès à Docker : ce script,
# lancé sur le serveur avec les droits Docker du client, ne fait que remplacer l'image de l'agent par celle
# que le pilote lui rend, une image de MEGGA nommée par son empreinte. Rien d'autre.
#
# Chaque minute, par cron (ou un minuteur systemd), depuis ce dossier :
#   * * * * * /chemin/vers/installation/compose/mettre_a_jour.sh >> /var/log/megga-mises-a-jour.log 2>&1
# Ou à la main, après « python -m pilote accepter <n> ».
set -euo pipefail
cd "$(dirname "$0")"

# Une seule exécution à la fois (mkdir est atomique, et existe partout).
verrou=.mise-a-jour.verrou
mkdir "$verrou" 2> /dev/null || exit 0
trap 'rmdir "$verrou"' EXIT

heure() { date -u +"%d.%m.%Y %H:%M:%S UTC"; }
actuelle=$(sed -n 's/^MEGGA_IMAGE=//p' .env | tail -n 1)
[ -n "$actuelle" ] || { echo "$(heure) MEGGA_IMAGE absente de .env"; exit 1; }

pilote() { docker compose exec -T pilote python -m pilote image --actuelle "$1"; }

if ! reponse=$(pilote "$actuelle"); then
    echo "$(heure) le pilote ne répond pas (docker compose ps)"
    exit 1
fi
action=${reponse%% *}
cible=${reponse#* }

case "$action" in
    rien)
        # Hors mise à jour, le pilote suit l'image de l'agent (sans effet s'il l'a déjà).
        docker compose up -d --no-deps pilote > /dev/null 2>&1
        ;;
    attendre)
        ;;
    installer|revenir)
        # Seulement une image nommée par son empreinte : jamais une étiquette, jamais une commande.
        if ! printf '%s' "$cible" | grep -Eq '^[a-z0-9]+([.-][a-z0-9]+)*(:[0-9]{1,5})?(/[a-z0-9]+([._-][a-z0-9]+)*)+@sha256:[0-9a-f]{64}$'; then
            echo "$(heure) réponse du pilote refusée : $reponse"
            exit 1
        fi
        echo "$(heure) $action : $cible (avant : $actuelle)"
        docker pull -q "$cible" > /dev/null
        # .env garde la nouvelle image : un « docker compose up » plus tard la reprend.
        awk -v ligne="MEGGA_IMAGE=$cible" '/^MEGGA_IMAGE=/ { print ligne; next } { print }' .env > .env.nouveau
        cat .env.nouveau > .env && rm -f .env.nouveau
        # L'agent seul : le pilote, resté sur l'image d'avant, surveille la nouvelle et décide du retour.
        docker compose up -d --no-deps agent
        pilote "$cible" > /dev/null || true
        ;;
    *)
        echo "$(heure) réponse du pilote inattendue : $reponse"
        exit 1
        ;;
esac
