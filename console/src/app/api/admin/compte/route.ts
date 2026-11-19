import { detailNom, lireNom } from "@/lib/admin/compte";
import { gardeMembre } from "@/lib/admin/garde";
import { auth } from "@/lib/auth";

// Son propre nom affiché. PATCH { nom } : 1 à 80 caractères, sans les espaces autour ; noté au journal. Le courriel ne change pas.
export const PATCH = gardeMembre({ action: "compte.nom", detail: detailNom }, async ({ corps, requete }) => {
  const nom = lireNom(corps);
  await auth().api.updateUser({ body: { name: nom }, headers: requete.headers });
  return { nom };
});
