import { lireMotsDePasse, refusMotDePasse } from "@/lib/admin/compte";
import { gardeMembre } from "@/lib/admin/garde";
import { auth } from "@/lib/auth";

// Son propre mot de passe. POST { actuel, nouveau } : l'actuel est exigé, le nouveau fait 8 caractères au moins. Les autres
// sessions restent ouvertes (Déconnecter les autres appareils est un geste à part). Rien du corps au journal.
export const POST = gardeMembre({ action: "compte.motDePasse", detail: () => null }, async ({ corps, requete }) => {
  const { actuel, nouveau } = lireMotsDePasse(corps);
  await auth()
    .api.changePassword({ body: { currentPassword: actuel, newPassword: nouveau, revokeOtherSessions: false }, headers: requete.headers })
    .catch(refusMotDePasse);
  return { ok: true };
});
