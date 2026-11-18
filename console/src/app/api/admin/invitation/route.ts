import { gardeSession } from "@/lib/admin/garde";
import { accepterInvitation } from "@/lib/admin/invitations";

// Rejoindre l'admin par une invitation : une session au courriel invité suffit. Corps : { jeton } (masqué au journal).
export const POST = gardeSession({ action: "invitations.accepter" }, async ({ compte, corps, db }) => {
  const jeton = (corps as { jeton?: unknown } | null)?.jeton;
  return { membre: accepterInvitation(db, typeof jeton === "string" ? jeton : "", compte) };
});
