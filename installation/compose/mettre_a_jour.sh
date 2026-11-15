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

# Une seule exécution à la fois (mkdir est atomique, et existe partout). Un verrou de plus de 30 minutes
# vient d'une exécution interrompue (serveur redémarré) : il ne doit pas bloquer les suivantes.
verrou=.mise-a-jour.verrou
find . -maxdepth 1 -name "$verrou" -type d -mmin +30 -exec rmdir {} + 2> /dev/null || true
mkdir "$verrou" 2> /dev/null || exit 0
trap 'rmdir "$verrou"' EXIT

heure() { date -u +"%d.%m.%Y %H:%M:%S UTC"; }
valeur() { sed -n "s/^$1=//p" .env | tail -n 1 | tr -d "\"'"; }
# L'image de l'agent qui tourne vraiment : celle de son conteneur.
image_agent() {
    local id
    id=$(docker compose ps -a -q agent 2> /dev/null | head -n 1)
    [ -n "$id" ] && docker inspect -f '{{.Config.Image}}' "$id" 2> /dev/null || true
}
actuelle=$(image_agent)
[ -n "$actuelle" ] || actuelle=$(valeur MEGGA_IMAGE)
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
        # Seulement une image du dépôt de MEGGA (ou du miroir du client), nommée par son empreinte :
        # jamais une étiquette, jamais un autre dépôt, jamais une commande.
        depot=$(valeur MEGGA_DEPOT)
        depot=${depot:-ghcr.io/megga/megga-agents}
        if [ "${cible%@sha256:*}" != "$depot" ] || ! printf '%s' "$cible" | grep -Eq '^[a-z0-9]+([.-][a-z0-9]+)*(:[0-9]{1,5})?(/[a-z0-9]+([._-][a-z0-9]+)*)+@sha256:[0-9a-f]{64}$'; then
            echo "$(heure) réponse du pilote refusée : $reponse"
            exit 1
        fi
        echo "$(heure) $action : $cible (avant : $actuelle)"
        # Déjà là (l'image d'avant, d'ordinaire) : pas besoin du registre, qui peut être en panne.
        docker image inspect "$cible" > /dev/null 2>&1 || docker pull -q "$cible" > /dev/null
        # .env garde la nouvelle image : un « docker compose up » plus tard la reprend.
        awk -v ligne="MEGGA_IMAGE=$cible" '/^MEGGA_IMAGE=/ { print ligne; next } { print }' .env > .env.nouveau
        cat .env.nouveau > .env && rm -f .env.nouveau
        # L'agent seul : le pilote, resté sur l'image d'avant, surveille la nouvelle et décide du retour.
        docker compose up -d --no-deps agent
        # Le pilote apprend l'image qui tourne vraiment, pas celle qu'on voulait poser.
        pilote "$(image_agent)" > /dev/null || true
        ;;
    *)
        echo "$(heure) réponse du pilote inattendue : $reponse"
        exit 1
        ;;
esac
