# La console en ligne : console.megga.ai

But : la console MEGGA, dont `/admin`, répond à `https://console.megga.ai`. Elle tourne dans un conteneur Cloudflare du compte MEGGA Inc., en zone Europe, derrière le Worker `megga-console` (`console/hebergement/`). Sa base est un Postgres chez Neon. La conception : [superpowers/specs/2026-11-19-console-en-ligne-design.md](superpowers/specs/2026-11-19-console-en-ligne-design.md).

Aucun secret ne passe par Claude ni par le dépôt : chacun se saisit en masqué, ou passe par un tube sans s'afficher.

## Ce qui tourne

- **Le Worker `megga-console`** (`console/hebergement/wrangler.jsonc`) : le domaine `console.megga.ai`, sans adresse `workers.dev` ni adresses d'aperçu. Il ne partage rien avec la porte (`porte/`).
- **Un seul conteneur**, en juridiction `eu`, de type `basic`, construit depuis `console/Dockerfile`. Il s'endort après 15 minutes sans visite ; le premier visiteur attend alors quelques secondes. S'il ne démarre pas, le visiteur reçoit une page d'attente en français (statut 503), qui se recharge seule.
- **L'inscription sur invitation** : en ligne, un compte ne se crée que depuis un lien d'invitation, et Google ou Microsoft ne créent jamais de compte (leurs clés ne sont de toute façon pas posées : seul le mot de passe sert).
- **Pas encore d'équipe d'agents** : `AGENTS_URL` n'est pas posée. La racine mène à `/admin`.

| Ce que le conteneur reçoit | Nature | Qui le pose |
|---|---|---|
| `BETTER_AUTH_URL` | `https://console.megga.ai` | `wrangler.jsonc` |
| `ATELIER_URL` | l'atelier derrière la porte (la console ajoute `/atelier`) | `wrangler.jsonc` |
| `CONSOLE_INSCRIPTION` | `invitation` | le Worker |
| `CONSOLE_REVISION` | le commit déployé (`--tag`) | le Worker |
| `BETTER_AUTH_SECRET` | secret, tiré au hasard | `secrets.sh` |
| `CONSOLE_BASE_URL` | secret : l'adresse de la base Neon | `secrets.sh` |
| `ATELIER_JETON` | secret, facultatif : le jeton MEGGA de l'atelier | `secrets.sh` |

Sans `BETTER_AUTH_SECRET` ou sans `CONSOLE_BASE_URL`, le Worker ne démarre pas le conteneur et répond la page d'attente : la console n'écrit jamais dans un fichier du conteneur, perdu à la veille.

## Une seule fois (Julien)

1. **La base Neon.** Un projet à part, pour que la console ne garde pas éveillé le calcul des bases des clients (`docs/atelier.md`, « Installations hors Cloudflare ») : région AWS Francfort (`aws-eu-central-1`), Postgres 18. Garder l'adresse **sans regroupeur** de connexions (l'hôte sans `-pooler`), avec `sslmode=require` : la console tient ses propres connexions et ses transactions y posent leurs délais. Les tables se créent à la première requête.
2. **Cloudflare.** La zone `megga.ai` est sur le compte MEGGA Inc., en Workers Paid (obligatoire pour les conteneurs). Depuis son Mac, Docker lancé (wrangler construit l'image) :
   ```bash
   cd console/hebergement && npm ci && npx wrangler login && npx wrangler whoami
   ```

## Le déploiement

Depuis `main` à jour, après la fusion de la PR, Docker lancé :

```bash
cd console/hebergement && npx wrangler deploy --tag "$(git rev-parse --short HEAD)"
```

Le premier déploiement crée le Worker et son domaine. Tant que les secrets manquent, `console.megga.ai` montre la page d'attente.

Un workflow « déployer la console », comme celui du moteur, attendra le droit Workers Routes sur le jeton de Cloudflare posé dans GitHub (`docs/deploiement.md` dit qu'il ne l'a pas encore). D'ici là, le chemin sûr est ce Mac.

## Les secrets

```bash
console/hebergement/secrets.sh
```

- `BETTER_AUTH_SECRET` est tiré au hasard et remis à wrangler par un tube, sans s'afficher. Si le Worker en a déjà un, le script le garde : le remplacer déconnecte tout le monde. Pour le remplacer quand même : `secrets.sh --nouveau-secret`.
- `CONSOLE_BASE_URL` puis `ATELIER_JETON` se demandent en saisie masquée. Un champ vide passe son tour, et le secret déjà posé reste. Le script les reprend aussi de son environnement, ou de son entrée (une ligne chacun, dans cet ordre), sans les afficher.

Le conteneur reçoit les secrets à son démarrage. Pour qu'il prenne un secret changé alors qu'il tourne : redéployer (la même commande), ou attendre qu'il s'endorme.

Vérifier, sans session :

```bash
curl -s https://console.megga.ai/api/sante
```

La réponse est `{"ok":true,"revision":"<commit>"}`. Elle ne touche pas à la base. Après `secrets.sh`, la version créée n'a pas d'étiquette et la révision redevient `"inconnue"` : redéployer avec `--tag` pour retrouver le commit.

Les journaux d'invocation de Cloudflare sont coupés (`invocation_logs: false` dans `wrangler.jsonc`) : ils garderaient 7 jours l'adresse et les en-têtes des requêtes, donc le jeton d'une invitation. L'en-tête d'inscription s'appelle `x-megga-invitation-token`, pour que le masquage de Cloudflare le couvre si ces journaux revenaient. Une invitation créée avant ce déploiement et pas encore acceptée se retire, puis se refait.

## Les deux premiers superadmins

La commande joue les migrations de la base de production avec le `node_modules` de ce poste : la lancer depuis le commit déployé (`git checkout <étiquette>`, puis `npm ci`). Depuis `console/`, l'adresse de la base de production tapée en masqué, dans un sous-shell (rien ne reste exporté dans le terminal) :

```bash
npm ci
( read -rs CONSOLE_BASE_URL && export CONSOLE_BASE_URL && BETTER_AUTH_URL=https://console.megga.ai npm run admin:inviter -- <courriel> )
```

Deux fois : Julien, puis Thomas. Chacun ouvre son lien (valable 7 jours, une seule fois), crée son compte avec ce courriel (le nom et un mot de passe de 8 caractères au moins), puis rejoint l'administration. Le lien est le seul moyen de créer un compte : il ne s'envoie qu'à la personne invitée.

## Revenir en arrière

- **Couper l'accès** : retirer le domaine `console.megga.ai` du Worker (tableau de bord Cloudflare, Workers, `megga-console`, Paramètres, Domaines et routes). Plus rien n'arrive à la console. La base reste chez Neon, intacte.
- **Revenir à la version précédente** : redéployer le commit précédent, `git checkout <commit précédent>` puis `cd console/hebergement && npx wrangler deploy --tag <commit précédent>`. Pas `wrangler rollback` : il vise la version du Worker et ne ramène pas l'image du conteneur, qui a son propre déploiement progressif.
- **Tout retirer** : `npx wrangler delete` depuis `console/hebergement`. La base reste ; elle se supprime à part, chez Neon, si on le décide.
