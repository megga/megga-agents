import { garde } from "@/lib/admin/garde";
import { retirerInvitation } from "@/lib/admin/invitations";

// Retirer une invitation en attente (204) : son lien ne vaut plus rien.
export const DELETE = garde(
  { droit: "equipe.gerer", action: "invitations.retirer", cible: (p: { id: string }) => `invitation:${p.id}` },
  async ({ acces, params, db }) => {
    retirerInvitation(db, acces, params.id);
  },
);
