import { gardeSession } from "@/lib/admin/garde";
import { accepterInvitation } from "@/lib/admin/invitations";

// Rejoindre l'admin par une invitation : une session au courriel invité suffit. Corps : { jeton }.
// Tout compte peut appeler cette route : le journal n'en garde que le jeton, masqué.
const jetonDe = (corps: unknown) => (corps as { jeton?: unknown } | null)?.jeton;

export const POST = gardeSession({ action: "invitations.accepter", detail: (corps) => ({ jeton: jetonDe(corps) }) }, async ({ compte, corps, db }) => {
  const jeton = jetonDe(corps);
  return { membre: accepterInvitation(db, typeof jeton === "string" ? jeton : "", compte) };
});
