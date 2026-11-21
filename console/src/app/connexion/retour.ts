// Où aller après la connexion : l'admin, la page d'invitation, sinon la console.
// Jamais un jeton d'invitation : il partirait vers Google ou Microsoft (callbackURL) et serait gardé en clair dans l'état OAuth.
// La page d'invitation range son jeton dans sessionStorage avant la connexion ; /admin/invitation l'y relit.
// À part du composant client (connexion.tsx) pour que la page, côté serveur, puisse l'appeler aussi.

export function retourSur(v: unknown, parDefaut: "/" | "/admin" = "/"): string {
  return v === "/admin" || v === "/admin/invitation" ? v : parDefaut;
}
