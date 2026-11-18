// Où aller après la connexion : l'admin, la page d'une invitation, sinon la console.
// À part du composant client (connexion.tsx) pour que la page, côté serveur, puisse l'appeler aussi.

const INVITATION = /^\/admin\/invitation\/[A-Za-z0-9_-]{43}$/;

export function retourSur(v: unknown): string {
  return v === "/admin" || (typeof v === "string" && INVITATION.test(v)) ? v : "/";
}
