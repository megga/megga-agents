import { T } from "@/lib/textes";

// Le code d'une erreur de connexion en une phrase de T : celui que Better Auth rend au formulaire, ou celui de ?error= au retour
// de Google ou Microsoft (errorCallbackURL). Le texte reçu n'est jamais montré tel quel : un code inconnu donne la phrase
// générale. À part du composant client (connexion.tsx) pour que la page, côté serveur, puisse l'appeler aussi.

export function messageErreur(code: unknown): string {
  if (typeof code !== "string" || !code) return T.erreurGenerale;
  if (code === "INVALID_EMAIL_OR_PASSWORD" || code === "INVALID_EMAIL" || code === "INVALID_PASSWORD") return T.erreurIdentifiants;
  if (code.startsWith("USER_ALREADY_EXISTS")) return T.erreurDejaInscrit;
  if (code === "PASSWORD_TOO_SHORT") return T.erreurMotDePasse;
  if (code === "BANNED_USER") return T.compteSuspendu;
  // L'inscription sur invitation : par courriel (auth.ts), ou au retour de Google ou Microsoft (disableSignUp).
  if (code === "INSCRIPTION_SUR_INVITATION" || code === "signup_disabled") return T.inscriptionSurInvitation;
  return T.erreurGenerale;
}
