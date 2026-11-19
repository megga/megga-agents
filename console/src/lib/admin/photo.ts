import { randomBytes } from "node:crypto";
import { Refus } from "@/lib/agents";
import type { Base } from "@/lib/donnees/base";
import { TA } from "./textes";

// La photo de profil d'un compte, rangée dans la base de la console (compte_photo) et servie par
// /api/compte/photo/<utilisateur> à qui est connecté. Le navigateur la recadre et la réduit ; ici, seules des images WebP,
// JPEG ou PNG passent, d'après leurs premiers octets (jamais d'après le seul type annoncé), et 200 Ko au plus.

export const PHOTO_MAX_OCTETS = 200 * 1024;
export type TypePhoto = "image/webp" | "image/jpeg" | "image/png";

const octetsDe = (s: string) => [...s].map((c) => c.charCodeAt(0));
const commencePar = (o: Uint8Array, signature: number[], depuis = 0) => signature.every((x, i) => o[depuis + i] === x);

/** La signature de chaque type admis : ce que ses premiers octets doivent être. */
const SIGNATURES: Record<TypePhoto, (o: Uint8Array) => boolean> = {
  "image/webp": (o) => commencePar(o, octetsDe("RIFF")) && commencePar(o, octetsDe("WEBP"), 8),
  "image/jpeg": (o) => commencePar(o, [0xff, 0xd8, 0xff]),
  "image/png": (o) => commencePar(o, [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
};

const estType = (t: string): t is TypePhoto => Object.hasOwn(SIGNATURES, t);

/** Le type de l'image : 413 au-delà de la limite, 400 si le type n'est pas admis ou si les octets ne sont pas ceux qu'il annonce. */
export function verifierImage(octets: Uint8Array, typeAnnonce: string): TypePhoto {
  if (octets.length > PHOTO_MAX_OCTETS) throw new Refus(413, TA.photoTropLourde);
  if (!estType(typeAnnonce) || !SIGNATURES[typeAnnonce](octets)) throw new Refus(400, TA.photoInvalide);
  return typeAnnonce;
}

const BASE64 = /^[A-Za-z0-9+/]*={0,2}$/;
/** La longueur en base64 de PHOTO_MAX_OCTETS octets : au-delà, la photo est trop lourde sans même la décoder. */
const BASE64_MAX = Math.ceil(PHOTO_MAX_OCTETS / 3) * 4;

/** Le base64 strict (Buffer.from l'accepte trop largement) : sinon, 400 ; plus long que la limite ne le permet, 413 sans le décoder. */
function decoder(donnees: unknown): Uint8Array {
  if (typeof donnees !== "string" || !donnees) throw new Refus(400, TA.photoInvalide);
  if (donnees.length > BASE64_MAX) throw new Refus(413, TA.photoTropLourde);
  if (donnees.length % 4 !== 0 || !BASE64.test(donnees)) throw new Refus(400, TA.photoInvalide);
  return new Uint8Array(Buffer.from(donnees, "base64"));
}

/** L'adresse de la photo d'un compte, à mettre dans le champ image de Better Auth ; la version change avec la photo. */
export const adressePhoto = (utilisateur: string, version: string) => `/api/compte/photo/${encodeURIComponent(utilisateur)}?v=${version}`;

/** Décode, vérifie, range (remplace la précédente) ; rend l'adresse de la photo. */
export async function poserPhoto(b: Base, utilisateur: string, donneesBase64: string, typeAnnonce: string, maintenant = new Date()): Promise<string> {
  const octets = decoder(donneesBase64);
  const type = verifierImage(octets, typeAnnonce);
  const version = randomBytes(6).toString("hex");
  await b.ecrire(
    `INSERT INTO compte_photo (utilisateur, type, donnees, version, modifiee_le) VALUES (?, ?, ?, ?, ?)
     ON CONFLICT (utilisateur) DO UPDATE SET type = excluded.type, donnees = excluded.donnees, version = excluded.version,
     modifiee_le = excluded.modifiee_le`,
    utilisateur, type, Buffer.from(octets).toString("base64"), version, maintenant.toISOString(),
  );
  return adressePhoto(utilisateur, version);
}

export async function retirerPhoto(b: Base, utilisateur: string): Promise<void> {
  await b.ecrire("DELETE FROM compte_photo WHERE utilisateur = ?", utilisateur);
}

/** Le champ image du compte (Better Auth) : l'adresse de sa photo, ou null. */
export async function imageDe(b: Base, utilisateur: string): Promise<string | null> {
  return (await b.un<{ image: string | null }>('SELECT image FROM "user" WHERE id = ?', utilisateur))?.image ?? null;
}

export async function lirePhoto(b: Base, utilisateur: string): Promise<{ type: TypePhoto; octets: Uint8Array } | undefined> {
  const l = await b.un<{ type: string; donnees: string }>("SELECT type, donnees FROM compte_photo WHERE utilisateur = ?", utilisateur);
  if (!l || !estType(l.type)) return undefined;
  return { type: l.type, octets: new Uint8Array(Buffer.from(l.donnees, "base64")) };
}
