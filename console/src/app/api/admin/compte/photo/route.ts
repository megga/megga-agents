import { detailPhoto, lirePhotoEnvoyee } from "@/lib/admin/compte";
import { gardeMembre } from "@/lib/admin/garde";
import { poserPhoto, retirerPhoto } from "@/lib/admin/photo";
import { auth } from "@/lib/auth";

// Sa propre photo de profil. PUT { donnees (base64), type } : vérifiée et rangée (photo.ts), puis le champ image du compte
// (Better Auth) pointe vers elle. DELETE : retirée, le compte revient à son initiale. Le journal garde le type et la taille,
// jamais les données.
export const PUT = gardeMembre({ action: "compte.photo", detail: detailPhoto }, async ({ acces, corps, requete, db }) => {
  const { donnees, type } = lirePhotoEnvoyee(corps);
  const image = await poserPhoto(db, acces.utilisateur, donnees, type);
  await auth().api.updateUser({ body: { image }, headers: requete.headers });
  return { image };
});

export const DELETE = gardeMembre({ action: "compte.photoRetiree", detail: () => null }, async ({ acces, requete, db }) => {
  await retirerPhoto(db, acces.utilisateur);
  await auth().api.updateUser({ body: { image: null }, headers: requete.headers });
});
