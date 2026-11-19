// L'adresse d'une photo de profil, la seule forme que le champ image d'un compte peut prendre : /api/compte/photo/<id>?v=<12
// caractères hexadécimaux>, servie par la console à qui est connecté. Partagée par le serveur (auth.ts refuse toute autre
// écriture du champ) et par l'écran (Avatar n'affiche rien d'autre) : jamais une adresse d'ailleurs ni une data: URI.
// Sans dépendance au serveur : Avatar l'importe aussi côté navigateur.

const ADRESSE = /^\/api\/compte\/photo\/([^/?#]+)\?v=[0-9a-f]{12}$/;

/** L'adresse de la photo d'un compte, pour une version donnée. */
export const adressePhoto = (utilisateur: string, version: string) => `/api/compte/photo/${encodeURIComponent(utilisateur)}?v=${version}`;

/** image est-elle l'adresse d'une photo de la console (de ce compte-là, si utilisateur est donné) ? */
export function estAdressePhoto(image: unknown, utilisateur?: string): image is string {
  if (typeof image !== "string" || image.length > 512) return false;
  const m = ADRESSE.exec(image);
  return !!m && (utilisateur === undefined || m[1] === encodeURIComponent(utilisateur));
}
