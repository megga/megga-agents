import { atelier } from "@/lib/admin/atelier";
import { garde } from "@/lib/admin/garde";

// Le lien de paiement Stripe de l'abonnement du client (Checkout), à lui envoyer : il y saisit sa carte. Le journal ne
// garde pas l'adresse.
export const POST = garde({ droit: "tarifs.regler", client: (p: { id: string }) => p.id, action: "stripe.lien" }, async ({ params }) =>
  atelier.lienPaiement(params.id),
);
