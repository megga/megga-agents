import { atelier } from "@/lib/admin/atelier";
import { garde } from "@/lib/admin/garde";

// Le portail Stripe du client : sa carte, ses factures, sa résiliation. Le journal ne
// garde pas l'adresse.
export const POST = garde({ droit: "tarifs.regler", client: (p: { id: string }) => p.id, action: "stripe.portail" }, async ({ params }) =>
  atelier.portailPaiement(params.id),
);
