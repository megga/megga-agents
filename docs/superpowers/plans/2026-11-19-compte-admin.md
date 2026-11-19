# Mon compte, dans l'admin : plan de construction

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** une page « Mon compte » dans l'admin (photo, nom, mot de passe, appareils connectés) et un lien « Retour au site » dans le menu du compte.

**Architecture:** la photo, recadrée et réduite dans le navigateur, est rangée dans une table de la console (`compte_photo`) et servie par une route qui exige une session ; le champ `image` de Better Auth pointe vers elle. Les gestes passent par une garde nouvelle, `gardeMembre` (membre en cours, sans droit particulier), et par l'API serveur de Better Auth. Un composant `Avatar` unique montre la photo ou l'initiale.

**Tech Stack:** Next 16, Better Auth 1.7.25, l'interface `Base` (`console/src/lib/donnees/`, SQLite ou Postgres), Vitest 5, Playwright 1.65.1. Aucune dépendance nouvelle.

**Spec:** `docs/superpowers/specs/2026-11-19-compte-admin-design.md`

## Global Constraints

- Textes visibles en français, dans `T` (`console/src/lib/textes.ts`) ou `TA` (`console/src/lib/admin/textes.ts`), sans point médian ni tiret long ; seuls les jetons de `console/src/app/globals.css`.
- Photo : 256 × 256, `image/webp` (repli `image/jpeg`), acceptée seulement en `image/webp`, `image/jpeg` ou `image/png` après vérification de la signature des premiers octets, 200 Ko au plus (`200 * 1024` octets décodés).
- Servir la photo : session exigée (401 sinon), 404 sans photo, en-têtes `Cache-Control: private, max-age=31536000, immutable`, `X-Content-Type-Options: nosniff`, `Content-Security-Policy: default-src 'none'`.
- Mot de passe : au moins 8 caractères, l'ancien exigé.
- Chaque geste est noté au journal, sans mot de passe ni données d'image dans le détail.
- Le courriel n'est pas modifiable ; la double authentification n'est pas dans ce lot.
- « Retour au site » : `https://megga.ai`, `target="_blank"`, `rel="noopener noreferrer"`.
- Les essais passent sur les deux moteurs (`CONSOLE_ESSAI_MOTEUR=postgres` avec un Postgres Docker local), aucune attente d'un essai existant ne change. Jamais de connexion à Neon.
- Node : `export PATH="$HOME/.local/share/fnm/node-versions/v24.19.0/installation/bin:$PATH"`. Commits en français (`feat(admin) : …`), terminés par `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Un fichier déguisé en image** (un SVG ou un HTML nommé `.png`, un type annoncé `image/png` sur d'autres octets) : refusé 400, rien n'est rangé (tâche 1, `refuse des octets qui ne sont pas l'image annoncée`).
2. **La photo d'un autre compte par son adresse, sans session** : 401 (tâche 1, `exige une session pour servir une photo`).
3. **Un non-membre connecté qui appelle les routes de `/api/admin/compte`** : 404, et rien au journal, comme les autres routes de l'admin (tâche 2, `refuse un compte qui n'est pas membre`).
4. **Un mauvais ancien mot de passe** : refus en français, le mot de passe ne change pas, le journal note le refus sans valeur (tâche 2, `refuse un ancien mot de passe faux`).
5. **« Déconnecter les autres appareils »** ne touche ni la session en cours ni celles d'un autre compte (tâche 2, `déconnecte seulement les autres sessions de ce compte`).

---

### Task 1: La photo, rangée et servie

**Files:**
- Modify: `console/src/lib/admin/tables.ts` (la table `compte_photo`)
- Create: `console/src/lib/admin/photo.ts`
- Create: `console/src/app/api/compte/photo/[utilisateur]/route.ts`
- Test: `console/tests/admin/photo.test.ts`

**Interfaces:**
- Produces (`photo.ts`) :
  - `export const PHOTO_MAX_OCTETS = 200 * 1024;`
  - `export type TypePhoto = "image/webp" | "image/jpeg" | "image/png";`
  - `export function verifierImage(octets: Uint8Array, typeAnnonce: string): TypePhoto` — lève `Refus(413, TA.photoTropLourde)` au-delà de la limite, `Refus(400, TA.photoInvalide)` si le type n'est pas l'un des trois ou si la signature ne correspond pas (WebP : `RIFF` …`WEBP` ; JPEG : `FF D8 FF` ; PNG : `89 50 4E 47 0D 0A 1A 0A`).
  - `export async function poserPhoto(b: Base, utilisateur: string, donneesBase64: string, typeAnnonce: string, maintenant?: Date): Promise<string>` — décode, vérifie, range (remplace), rend l'adresse `/api/compte/photo/<utilisateur>?v=<version>` (version : 12 caractères hexadécimaux tirés au hasard).
  - `export async function retirerPhoto(b: Base, utilisateur: string): Promise<void>`
  - `export async function lirePhoto(b: Base, utilisateur: string): Promise<{ type: TypePhoto; octets: Uint8Array } | undefined>`
- Table : `compte_photo (utilisateur TEXT PRIMARY KEY, type TEXT NOT NULL, donnees TEXT NOT NULL, version TEXT NOT NULL, modifiee_le TEXT NOT NULL)`, créée dans `creerTablesAdmin` comme les autres.

- [ ] **Step 1: Écrire les essais** (`describe.each` sur les moteurs, comme `tests/admin/tables.test.ts`) :
  - `range et relit une photo WebP` : `poserPhoto` d'un WebP minimal valide rend une adresse qui commence par `/api/compte/photo/u1?v=` ; `lirePhoto` rend `type: "image/webp"` et les mêmes octets.
  - `refuse des octets qui ne sont pas l'image annoncée` : `<svg …>` annoncé `image/png` → `Refus` 400 ; `image/svg+xml` → 400 ; `lirePhoto` rend `undefined`.
  - `refuse une photo trop lourde` : `PHOTO_MAX_OCTETS + 1` octets à signature PNG → 413.
  - `remplace puis retire` : deux `poserPhoto` rendent deux versions différentes ; `retirerPhoto` puis `lirePhoto` → `undefined`.
  - Route : `exige une session pour servir une photo` (401 sans `x-essai-qui`, même mock de session que `tests/admin/equipe-routes.test.ts`) ; `sert la photo avec ses en-têtes` (200, `content-type`, et les trois en-têtes des contraintes) ; `rend 404 sans photo`.
- [ ] **Step 2: Lancer** `cd console && npx vitest run tests/admin/photo.test.ts` : échec, le module n'existe pas.
- [ ] **Step 3: Écrire** la table, `photo.ts`, et la route (`GET` seulement ; session par `sessionDe`, base par `pret()`).
- [ ] **Step 4: Lancer** l'essai sur SQLite puis sur Postgres : tout passe ; puis `npm run typecheck && npm run lint && npm test`.
- [ ] **Step 5: Commit** `feat(admin) : la photo de profil, rangée dans la base et servie à qui est connecté`.

### Task 2: Les gestes du compte

**Files:**
- Modify: `console/src/lib/admin/garde.ts` (ajouter `gardeMembre`)
- Create: `console/src/app/api/admin/compte/photo/route.ts` (`PUT`, `DELETE`)
- Create: `console/src/app/api/admin/compte/route.ts` (`PATCH` : le nom)
- Create: `console/src/app/api/admin/compte/mot-de-passe/route.ts` (`POST`)
- Create: `console/src/app/api/admin/compte/sessions/route.ts` (`DELETE` : les autres appareils)
- Modify: `console/src/lib/admin/textes.ts` (les messages et les libellés des actions du journal)
- Test: `console/tests/admin/compte-routes.test.ts`

**Interfaces:**
- Consumes : `poserPhoto`, `retirerPhoto` (tâche 1).
- Produces :
  - `export function gardeMembre<P extends Record<string, string>>(regle: Omit<Regle<P>, "droit" | "client">, traiter: (c: Contexte<P>) => Promise<unknown>): Gestionnaire<P>` — même ordre que `garde` (session 401, membre en cours 404 sans rien au journal, origine 403 hors GET), sans exiger de droit. `garde` ne change pas.
  - Actions du journal : `compte.photo`, `compte.photoRetiree`, `compte.nom`, `compte.motDePasse`, `compte.autresAppareils`, avec leurs libellés dans `TA` (là où les autres actions ont les leurs).
  - Corps : photo `{ donnees: string (base64), type: string }` ; nom `{ nom: string }` (1 à 80 caractères après `trim`) ; mot de passe `{ actuel: string, nouveau: string }`.
  - Better Auth, côté serveur, avec les en-têtes de la requête : `auth().api.updateUser({ body: { image | name }, headers })`, `auth().api.changePassword({ body: { currentPassword, newPassword, revokeOtherSessions: false }, headers })`, `auth().api.revokeOtherSessions({ headers })`. Un refus de Better Auth (mot de passe faux, trop court) devient un `Refus` avec un texte de `TA`, jamais son message anglais.
  - `detail` du journal : rien pour le mot de passe ; `{ nom }` pour le nom ; `{ type, octets }` pour la photo.

- [ ] **Step 1: Écrire les essais** (même montage que `equipe-routes.test.ts` ; pour le mot de passe et les sessions, une vraie base d'essai avec un compte créé par `auth().api.signUpEmail` en mode inscription ouverte, et des sessions réelles) :
  - `pose la photo et met à jour l'image du compte` ; `retire la photo` (l'image du compte revient à `null`) ; `note la photo au journal sans ses données`.
  - `change le nom` ; `refuse un nom vide`.
  - `change le mot de passe` (se connecter avec le nouveau réussit, avec l'ancien échoue) ; `refuse un ancien mot de passe faux` (400, `TA`, le mot de passe ne change pas, le journal note `refuse` sans valeur) ; `refuse un nouveau mot de passe de moins de 8 caractères`.
  - `déconnecte seulement les autres sessions de ce compte` : trois sessions pour le compte, une pour un autre ; après, il reste la session en cours et celle de l'autre compte.
  - `refuse un compte qui n'est pas membre` : 404 sur chaque route, aucune ligne au journal.
- [ ] **Step 2: Lancer** `npx vitest run tests/admin/compte-routes.test.ts` : échec.
- [ ] **Step 3: Écrire** `gardeMembre`, les quatre routes et les textes.
- [ ] **Step 4: Lancer** l'essai sur les deux moteurs, puis `npm run typecheck && npm run lint && npm test`.
- [ ] **Step 5: Commit** `feat(admin) : les gestes de Mon compte (photo, nom, mot de passe, autres appareils)`.

### Task 3: La page « Mon compte », l'avatar, le menu

**Files:**
- Create: `console/src/app/admin/(espace)/compte/page.tsx`, `console/src/app/admin/(espace)/compte/compte.tsx` (les formulaires, côté client)
- Create: `console/src/components/console/avatar.tsx`
- Create: `console/src/lib/navigateur.ts`
- Modify: `console/src/components/console/compte.tsx` (le menu : avatar, « Mon compte », « Retour au site »)
- Modify: `console/src/components/admin/rail.tsx` (passer l'image et l'entrée « Mon compte »), `console/src/components/console/rail.tsx` s'il passe le nom au menu (l'image aussi)
- Modify: `console/src/lib/textes.ts`, `console/src/lib/admin/textes.ts`
- Test: `console/tests/navigateur.test.ts`, `console/tests/avatar.test.ts`

**Interfaces:**
- Produces :
  - `export function Avatar({ nom, image, taille }: { nom: string; image?: string | null; taille: number }): JSX.Element` — la photo (`<img alt="">` aux coins de l'initiale actuelle) ou l'initiale (la fonction `initiale` de `compte.tsx` y déménage).
  - `export function navigateurDe(agent: string | null): string` — « Chrome sur macOS », « Safari sur iPhone », « Firefox sur Windows », « Edge sur Windows »… ; `TA.navigateurInconnu` sinon.
  - `Compte` reçoit `image?: string | null`, `monCompte?: string` (l'adresse `/admin/compte`, passée par le rail de l'admin seulement) ; il montre toujours « Retour au site ».
- La page : `gardePage()` sans droit ; lit le compte (nom, courriel, image) et ses sessions (`auth().api.listSessions({ headers })`), marque celle en cours. Quatre blocs : Photo (choisir, aperçu, retirer), Nom, Mot de passe (actuel, nouveau, confirmation identique côté client), Appareils connectés (liste, bouton « Déconnecter les autres appareils » derrière la confirmation de `components/admin/confirmation.tsx`). Le courriel est affiché en lecture seule.
- Le recadrage : un `<canvas>` 256 × 256, recadrage carré au centre, `toBlob("image/webp", 0.85)`, repli `image/jpeg` si le résultat n'est pas du WebP ; envoi en base64 par `components/admin/envoyer.ts`. Après succès, `router.refresh()`.

- [ ] **Step 1: Écrire les essais** : `navigateurDe` sur six agents réels courants et `null` ; `Avatar` rend l'image quand elle existe, l'initiale sinon (rendu serveur avec `renderToStaticMarkup`, comme les autres essais de page).
- [ ] **Step 2: Lancer** `npx vitest run tests/navigateur.test.ts tests/avatar.test.ts` : échec.
- [ ] **Step 3: Écrire** l'avatar, `navigateurDe`, la page, ses formulaires et le menu.
- [ ] **Step 4: Lancer** `npm run typecheck && npm run lint && npm test` ; ouvrir la page en local (`npm run dev`, un compte superadmin par `npm run admin:inviter`) en clair et en sombre, à 1280 et 390 px de large, et vérifier qu'aucune couleur n'est hors des jetons.
- [ ] **Step 5: Commit** `feat(admin) : la page Mon compte, l'avatar et le retour au site`.

### Task 4: Les photos dans l'équipe, les comptes et le journal ; le parcours

**Files:**
- Modify: `console/src/lib/admin/membres.ts`, `console/src/lib/admin/comptes.ts`, `console/src/lib/admin/journal.ts` (lire `u.image` avec le reste)
- Modify: `console/src/app/admin/(espace)/equipe/membres.tsx`, `console/src/app/admin/(espace)/comptes/page.tsx` (et la fiche `comptes/[id]`), `console/src/app/admin/(espace)/journal/page.tsx`
- Modify: `console/e2e/admin.spec.ts`
- Test: les essais existants de ces pages et modules, plus le parcours

**Interfaces:**
- Consumes : `Avatar` (tâche 3), les routes (tâche 2).
- Produces : `Membre.image`, la ligne de compte `image`, `LigneJournal.image` (de qui a agi ; `null` pour le serveur), lus par jointure sur `"user"`.

- [ ] **Step 1: Ajouter aux essais existants** : un membre, un compte et une ligne de journal rendent `image` quand le compte en a une, `null` sinon.
- [ ] **Step 2: Ajouter au parcours** `e2e/admin.spec.ts` : le superadmin ouvre « Mon compte » par le menu, change son nom (le menu le montre), envoie une photo (un PNG fabriqué dans l'essai, `setInputFiles`), la voit dans le menu et dans la liste de l'équipe, change son mot de passe, se déconnecte et se reconnecte avec le nouveau ; « Retour au site » a `href="https://megga.ai"` et `target="_blank"`.
- [ ] **Step 3: Écrire** les lectures et l'affichage.
- [ ] **Step 4: Lancer** `npm run typecheck && npm run lint && npm test` sur les deux moteurs, puis `npx playwright test --config playwright.local.config.ts` : tout passe.
- [ ] **Step 5: Commit** `feat(admin) : les photos de l'équipe dans l'équipe, les comptes et le journal`.
