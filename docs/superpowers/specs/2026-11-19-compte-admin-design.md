# Mon compte, dans l'admin : conception

Le 19.11.2026. Demande de Thomas, une fois la console en ligne sur `https://console.megga.ai` : « il manque une page de gestion et personnalisation du compte admin » (son exemple : ajouter une photo de profil) et « un bouton de retour sur le site ». Petite évolution, empilée sur la PR #70 (la mise en ligne).

## L'intention

Un membre de l'admin règle son propre compte sans passer par Julien ni par une commande, et l'équipe se reconnaît à l'écran. Depuis l'admin, on revient au site public en un geste.

## Les buts

1. Une page « Mon compte » à `/admin/compte`, ouverte à tout membre en cours, sans droit particulier. On y arrive par une entrée « Mon compte » du menu du compte (en bas du rail), au-dessus de « Se déconnecter ».
2. **Photo de profil** (demande de Thomas) : envoyer une image, la recadrer en carré, la retirer. Elle remplace l'initiale dans le menu du compte, et apparaît partout où l'admin nomme un membre ou un compte : l'équipe, les invitations acceptées, les comptes, le journal. Sans photo, l'initiale reste.
3. **Nom affiché** : le modifier.
4. **Mot de passe** : le changer en redonnant l'ancien (au moins 8 caractères, comme à l'inscription).
5. **Courriel** : affiché, non modifiable. Le changer suppose de vérifier la nouvelle adresse, et la console n'envoie pas de courriels.
6. **Appareils connectés** : les sessions ouvertes du compte (date, navigateur lu dans l'agent utilisateur, celle-ci marquée), et « Déconnecter les autres appareils ».
7. **Retour au site** : une entrée « Retour au site » du menu du compte, vers `https://megga.ai`, dans un nouvel onglet. Elle s'ajoute au lien existant vers la console des agents quand celui-ci est montré.

Thomas a validé cette liste le 19.11.2026 ; sa propre demande est la photo et le retour au site, le reste est une proposition de Claude qu'il a acceptée.

## Hors du périmètre

- La double authentification (à décider avec Julien).
- Changer de courriel, supprimer son compte.
- Une photo pour les comptes des clients dans la console des agents (la page est celle de l'admin ; le menu partagé montre la photo partout où elle existe, mais seule l'admin propose de la changer).
- Le thème : il reste dans le menu, tel qu'aujourd'hui.

## Ce qui serait un échec

- Une photo qui n'est pas une image (un fichier HTML ou SVG servi comme image, un script), ou qui dépasse la limite et remplit la base.
- La photo d'un compte lisible par quelqu'un qui n'est pas connecté.
- Un mot de passe changé sans redonner l'ancien, ou des sessions d'un autre compte touchées.
- Un geste qui ne laisse pas de trace au journal (photo, nom, mot de passe, autres appareils déconnectés).
- Une couleur, une police ou un contour hors des jetons de `globals.css` ; un texte hors de `T`/`TA`, avec un point médian ou un tiret long.

## Les approches (où ranger la photo)

| Voie | Ce qu'elle donne | Ce qu'elle coûte |
|---|---|---|
| **A. Dans la base de la console** (choisie par Thomas) | Rien de neuf à exploiter ; sauvegardée avec la base ; marche en local, dans les essais et en ligne. | Quelques dizaines de Ko par membre dans Postgres. |
| B. Dans R2 chez Cloudflare | La base ne grossit pas. | Un service et une clé de plus, une pièce de plus pour le local et les essais : trop pour quelques photos. |
| C. Gravatar | Aucun stockage. | Un tiers prévenu à chaque page, une photo qu'on ne choisit pas dans la console. Écartée. |

## La conception

**La photo.** Le navigateur recadre l'image choisie en carré (au centre), la réduit à 256 × 256 et l'encode en WebP (JPEG si le navigateur ne sait pas). Le serveur n'accepte que `image/webp`, `image/jpeg` ou `image/png`, vérifie la signature des premiers octets (pas seulement le type annoncé), et refuse au-delà de 200 Ko. Elle est rangée dans une table de la console, `compte_photo (utilisateur TEXT PRIMARY KEY, type TEXT, donnees TEXT en base64, version TEXT, modifiee_le TEXT)`, créée comme les autres tables (`preparer`, sous les deux moteurs). Le champ `image` de Better Auth reçoit l'adresse `/api/compte/photo/<utilisateur>?v=<version>`.

**Servir la photo.** `GET /api/compte/photo/<utilisateur>` : seulement avec une session ; rend l'image avec son type, `Cache-Control: private, max-age=31536000, immutable` (la version change avec la photo), `X-Content-Type-Options: nosniff`, et `Content-Security-Policy: default-src 'none'`. 404 sans photo.

**Les gestes.** Par des routes `/api/admin/compte/...` gardées par `gardeSession` (membre en cours), chacune notée au journal sans valeur sensible : poser ou retirer la photo, changer le nom, changer le mot de passe, déconnecter les autres appareils. Le nom, le mot de passe et les sessions passent par Better Auth (`updateUser`, `changePassword`, `listSessions`, `revokeOtherSessions`), côté serveur.

**L'affichage.** Un seul composant d'avatar (photo, sinon initiale), utilisé par le menu du compte et par les tableaux de l'admin qui nomment un membre ou un compte.

## Laissé au constructeur

- Le découpage en routes et en composants, les noms.
- Le recadrage : un simple recadrage au centre suffit ; un réglage du cadrage à la souris est un plus, pas une obligation.
- La lecture du navigateur dans l'agent utilisateur (quelques cas courants, sinon « Navigateur inconnu »).
- Les textes exacts, dans `T` et `TA`.

## Les choix de Claude, à corriger

- La page dans l'admin seulement, à `/admin/compte`.
- La photo visible de toute personne connectée à la console (comme le nom), pas seulement des membres.
- 256 × 256, WebP, 200 Ko au plus.
- Le lien « Retour au site » vers `https://megga.ai`, dans un nouvel onglet.
