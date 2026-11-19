#!/usr/bin/env bash
# Pose les secrets du Worker megga-console (docs/console-en-ligne.md). Aucune valeur ne s'affiche ni ne s'écrit sur le disque.
#  - BETTER_AUTH_SECRET : tiré au hasard (openssl rand -base64 32) et remis à wrangler par un tube. Si le Worker en a déjà
#    un, il est gardé : le remplacer déconnecte tout le monde. Pour le remplacer quand même : secrets.sh --nouveau-secret ;
#  - CONSOLE_BASE_URL (l'adresse de la base Neon) et ATELIER_JETON (le jeton MEGGA de l'atelier) : repris de
#    l'environnement s'ils y sont déjà, sinon demandés en saisie masquée (ou lus sur l'entrée, une ligne chacun, dans cet
#    ordre). Un champ vide passe son tour : le secret déjà posé reste.
# Le Worker doit exister (un premier « npx wrangler deploy ») et wrangler être connecté au compte de MEGGA Inc.
set -euo pipefail
set +x # jamais de trace : elle afficherait les valeurs

nouveau=0
for a in "$@"; do
  case "$a" in
    --nouveau-secret) nouveau=1 ;;
    *) echo "usage : secrets.sh [--nouveau-secret]" >&2; exit 2 ;;
  esac
done

cd "$(dirname "$0")"

# Les noms des secrets déjà posés (wrangler ne rend jamais leurs valeurs).
if ! existants=$(npx wrangler secret list --format json </dev/null 2>/dev/null); then
  echo "Impossible de lire les secrets du Worker megga-console : déployez-le d'abord (npx wrangler deploy)," >&2
  echo "et vérifiez que wrangler est connecté au compte de MEGGA Inc. (npx wrangler whoami)." >&2
  exit 1
fi
deja_pose() { grep -Eq "\"name\": *\"$1\"" <<<"$existants"; }

# Une valeur remise à wrangler par l'entrée standard, jamais en argument (lisible un instant dans ps).
poser() { npx wrangler secret put "$1" >/dev/null; }

if deja_pose BETTER_AUTH_SECRET && [ "$nouveau" = 0 ]; then
  echo "→ BETTER_AUTH_SECRET déjà posé : gardé (--nouveau-secret pour le remplacer, ce qui déconnecte tout le monde)"
else
  openssl rand -base64 32 | tr -d '\n' | poser BETTER_AUTH_SECRET
  echo "→ BETTER_AUTH_SECRET tiré au hasard et posé"
fi

# Repris de l'environnement s'il y est, sinon demandé en masqué ; vide, il passe son tour.
demander() {
  local nom=$1 explication=$2 valeur
  valeur=${!nom-}
  if [ -z "$valeur" ]; then
    read -rsp "$nom ($explication, vide pour passer) : " valeur || true
    [ -t 0 ] && echo >&2
  fi
  if [ -z "$valeur" ]; then
    echo "→ $nom : rien de saisi, passé"
  else
    printf '%s' "$valeur" | poser "$nom"
    echo "→ $nom posé"
  fi
  unset valeur
}

demander CONSOLE_BASE_URL "l'adresse de la base Neon, sans regroupeur"
demander ATELIER_JETON "le jeton MEGGA de l'atelier"
unset CONSOLE_BASE_URL ATELIER_JETON existants
echo "Le conteneur les reçoit à son prochain démarrage (docs/console-en-ligne.md, « Les secrets »)."
