#!/usr/bin/env bash
# Pose les secrets du Worker megga-agents. Rien ne s'affiche à l'écran.
#  - les clés des fournisseurs : wrangler les demande, saisie masquée ;
#  - META_VERIFY_TOKEN : tiré au hasard, posé, et copié dans le presse-papiers
#    pour le coller dans l'app Meta (Webhooks, « Jeton de vérification ») ;
#  - ADMIN_TOKEN : tiré au hasard, posé, et rangé dans le trousseau macOS
#    (service megga-agents-admin), où scripts/secrets_client.sh le reprend.
set -euo pipefail
cd "$(dirname "$0")/../porte"

for nom in META_APP_SECRET META_TOKEN ANTHROPIC_API_KEY DEEPSEEK_API_KEY ELEVENLABS_API_KEY; do
  echo "→ $nom"
  npx wrangler secret put "$nom"
done

jeton=$(openssl rand -hex 32)
printf '%s' "$jeton" | npx wrangler secret put META_VERIFY_TOKEN >/dev/null
printf '%s' "$jeton" | pbcopy
echo "→ META_VERIFY_TOKEN posé et copié dans le presse-papiers"

admin=$(openssl rand -hex 32)
printf '%s' "$admin" | npx wrangler secret put ADMIN_TOKEN >/dev/null
# Par l'entrée de « security -i » : jamais en argument de commande, lisible un instant dans ps.
printf 'add-generic-password -U -a megga-agents -s megga-agents-admin -w %s\n' "$admin" | security -i > /dev/null
echo "→ ADMIN_TOKEN posé et rangé dans le trousseau"
unset jeton admin
