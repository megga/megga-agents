import "server-only";
import { createHmac } from "node:crypto";

// La clé opaque d'une personne dans l'adresse d'un fil de conversation : le numéro n'y paraît jamais (ni dans l'historique
// du navigateur, ni dans un journal d'accès, ni dans le préchargement d'un lien). La page du fil retrouve la personne en
// relisant la liste des conversations du client et en comparant les clés.

/** Une clé : 16 caractères hexadécimaux. */
export const CLE_PERSONNE = /^[0-9a-f]{16}$/;

function secretDesCles(): string {
  const secret = process.env.BETTER_AUTH_SECRET;
  if (!secret) throw new Error("BETTER_AUTH_SECRET manquant : la clé d'une personne en dépend");
  return secret;
}

/** Les 16 premiers caractères hexadécimaux de HMAC-SHA256 de « <client>:<personne> » sous le secret (BETTER_AUTH_SECRET). */
export function clePersonne(client: string, personne: string, secret: string = secretDesCles()): string {
  return createHmac("sha256", secret).update(`${client}:${personne}`).digest("hex").slice(0, 16);
}
