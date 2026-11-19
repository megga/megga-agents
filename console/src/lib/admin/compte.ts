import { Refus } from "@/lib/agents";
import { estObjet } from "./champs";
import { TA } from "./textes";

// Les gestes de « Mon compte » (/api/admin/compte/...) : lire leurs corps, et ce que le journal en garde. Jamais un mot de
// passe, jamais les octets d'une photo au journal. Les écritures passent par l'API serveur de Better Auth, dans les routes.

export const NOM_MAX = 80;
/** La limite de Better Auth (maxPasswordLength par défaut) ; minPasswordLength est posé dans auth.ts. */
export const MOT_DE_PASSE_MIN = 8;
export const MOT_DE_PASSE_MAX = 128;

/** Le nom affiché : un texte, sans les espaces autour, de 1 à 80 caractères ; sinon 400. */
export function lireNom(corps: unknown): string {
  const nom = estObjet(corps) && typeof corps.nom === "string" ? corps.nom.trim() : "";
  if (!nom || [...nom].length > NOM_MAX) throw new Refus(400, TA.nomCompteManquant);
  return nom;
}

/** Ce que le journal garde d'un changement de nom : le nom, coupé à 80 caractères. */
export function detailNom(corps: unknown): { nom: string | null } {
  const nom = estObjet(corps) && typeof corps.nom === "string" ? corps.nom.trim() : null;
  return { nom: nom === null ? null : [...nom].slice(0, NOM_MAX).join("") };
}

/** Le corps d'une photo : { donnees (base64), type } ; les vérifications elles-mêmes sont dans photo.ts. */
export function lirePhotoEnvoyee(corps: unknown): { donnees: string; type: string } {
  if (!estObjet(corps) || typeof corps.donnees !== "string" || typeof corps.type !== "string") throw new Refus(400, TA.photoInvalide);
  return { donnees: corps.donnees, type: corps.type };
}

/** Ce que le journal garde d'une photo : son type annoncé et sa taille en octets, jamais ses données. */
export function detailPhoto(corps: unknown): { type: string | null; octets: number | null } {
  const type = estObjet(corps) && typeof corps.type === "string" ? corps.type.slice(0, 40) : null;
  const donnees = estObjet(corps) && typeof corps.donnees === "string" ? corps.donnees : null;
  const octets = donnees === null ? null : Math.max(0, Math.floor((donnees.length * 3) / 4) - (donnees.match(/=*$/)?.[0].length ?? 0));
  return { type, octets };
}

/** Le corps d'un changement de mot de passe : { actuel, nouveau }, le nouveau de 8 à 128 caractères ; sinon 400. */
export function lireMotsDePasse(corps: unknown): { actuel: string; nouveau: string } {
  const actuel = estObjet(corps) && typeof corps.actuel === "string" ? corps.actuel : "";
  const nouveau = estObjet(corps) && typeof corps.nouveau === "string" ? corps.nouveau : "";
  if (!actuel) throw new Refus(400, TA.ancienMotDePasseManquant);
  if (nouveau.length < MOT_DE_PASSE_MIN) throw new Refus(400, TA.motDePasseCourt);
  if (nouveau.length > MOT_DE_PASSE_MAX) throw new Refus(400, TA.motDePasseLong);
  return { actuel, nouveau };
}

/** Le code d'un refus de Better Auth (APIError : body.code), s'il en a un. */
function codeDe(e: unknown): string | undefined {
  const body = estObjet(e) ? (e as { body?: unknown }).body : undefined;
  return estObjet(body) && typeof body.code === "string" ? body.code : undefined;
}

const REFUS_MOT_DE_PASSE: Record<string, string> = {
  INVALID_PASSWORD: TA.ancienMotDePasseFaux,
  PASSWORD_TOO_SHORT: TA.motDePasseCourt,
  PASSWORD_TOO_LONG: TA.motDePasseLong,
  CREDENTIAL_ACCOUNT_NOT_FOUND: TA.sansMotDePasse,
};

/** Un refus de Better Auth au changement de mot de passe, dit en français (jamais son message anglais) ; le reste repart tel quel. */
export function refusMotDePasse(e: unknown): never {
  const texte = REFUS_MOT_DE_PASSE[codeDe(e) ?? ""];
  if (texte) throw new Refus(400, texte);
  throw e;
}
