import { Refus } from "@/lib/agents";
import { atelier } from "@/lib/admin/atelier";
import { estObjet } from "@/lib/admin/champs";
import { garde } from "@/lib/admin/garde";
import { TA } from "@/lib/admin/textes";

// L'abonnement d'un client : son forfait, son rythme, son statut, son début, son seuil de recharge ; l'atelier le valide.
// Le retirer ne sert qu'après une erreur de saisie. Le journal garde le forfait, le rythme et le statut, jamais un montant.

const MOT = /^[a-z0-9-]{1,40}$/;
const mot = (v: unknown) => (typeof v === "string" && MOT.test(v) ? v : null);

const client = (p: { id: string }) => p.id;

export const PUT = garde(
  {
    droit: "tarifs.regler",
    client,
    action: "abonnement.regler",
    detail: (corps) => (estObjet(corps) ? { forfait: mot(corps.forfait), rythme: mot(corps.rythme), statut: mot(corps.statut) } : null),
  },
  async ({ params, corps }) => {
    if (!estObjet(corps)) throw new Refus(400, TA.abonnementInvalide);
    return atelier.reglerAbonnement(params.id, corps);
  },
);

export const DELETE = garde({ droit: "tarifs.regler", client, action: "abonnement.retirer" }, async ({ params }) =>
  atelier.retirerAbonnement(params.id),
);
