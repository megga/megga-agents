import { Refus } from "@/lib/agents";
import { peutReglerAlertes } from "@/lib/admin/acces";
import { atelier } from "@/lib/admin/atelier";
import { garde } from "@/lib/admin/garde";
import { TA } from "@/lib/admin/textes";

// Retirer une destination d'alerte ; l'atelier refuse (409) tant qu'une règle l'utilise.
type P = { id: string };
const ID = /^[a-z0-9][a-z0-9-]{1,39}$/;

export const DELETE = garde(
  { droit: "alertes.regler", action: "alertes.destination_retiree", cible: (p: P) => (ID.test(p.id) ? p.id : null) },
  async ({ acces, params }) => {
    if (!peutReglerAlertes(acces)) throw new Refus(403, TA.sansDroit);
    if (!ID.test(params.id)) throw new Refus(404, TA.introuvable);
    return atelier.retirerDestination(params.id);
  },
);
