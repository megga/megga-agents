import { gardeMembre } from "@/lib/admin/garde";
import { auth } from "@/lib/auth";

// Déconnecter ses autres appareils : toutes ses sessions sauf celle de cette requête se ferment. Celles des autres comptes
// ne sont jamais touchées (Better Auth ne lit que les sessions du compte de la session en cours).
export const DELETE = gardeMembre({ action: "compte.autresAppareils", detail: () => null }, async ({ requete }) => {
  await auth().api.revokeOtherSessions({ headers: requete.headers });
  return { ok: true };
});
