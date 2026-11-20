import { Refus } from "@/lib/agents";
import { atelier } from "@/lib/admin/atelier";
import { estObjet } from "@/lib/admin/champs";
import { garde } from "@/lib/admin/garde";
import { TA } from "@/lib/admin/textes";

// Une recharge achetée hors Stripe : un paquet de conversations et son prix, comptés dans le mois en cours du client. Le
// journal garde le nombre de conversations, jamais le prix.

export const POST = garde(
  {
    droit: "tarifs.regler",
    client: (p: { id: string }) => p.id,
    action: "recharge.ajouter",
    detail: (corps) => ({ conversations: estObjet(corps) && Number.isInteger(corps.conversations) ? corps.conversations : null }),
  },
  async ({ params, corps }) => {
    if (!estObjet(corps)) throw new Refus(400, TA.rechargeInvalide);
    return atelier.recharger(params.id, corps);
  },
);
