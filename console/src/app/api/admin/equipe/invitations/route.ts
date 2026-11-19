import { garde } from "@/lib/admin/garde";
import { creerInvitation } from "@/lib/admin/invitations";

// Inviter : le lien (/admin/invitation/<jeton>) n'est rendu qu'ici, une fois ; le journal ne garde que le corps, sans jeton.
export const POST = garde({ droit: "equipe.gerer", action: "invitations.creer" }, async ({ acces, corps, db }) => {
  const { invitation, lien } = await creerInvitation(db, acces, corps);
  return Response.json({ invitation, lien }, { status: 201 });
});
