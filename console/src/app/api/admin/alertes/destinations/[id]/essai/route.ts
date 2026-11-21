import { Refus } from "@/lib/agents";
import { peutReglerAlertes } from "@/lib/admin/acces";
import { atelier } from "@/lib/admin/atelier";
import { garde } from "@/lib/admin/garde";
import { TA } from "@/lib/admin/textes";

// Un message d'essai vers une destination d'alerte, envoyé par l'atelier.
type P = { id: string };
const ID = /^[a-z0-9][a-z0-9-]{1,39}$/;

export const POST = garde(
  { droit: "alertes.regler", action: "alertes.essai", cible: (p: P) => (ID.test(p.id) ? p.id : null) },
  async ({ acces, params }) => {
    if (!peutReglerAlertes(acces)) throw new Refus(403, TA.sansDroit);
    if (!ID.test(params.id)) throw new Refus(404, TA.introuvable);
    return atelier.essayerDestination(params.id);
  },
);
