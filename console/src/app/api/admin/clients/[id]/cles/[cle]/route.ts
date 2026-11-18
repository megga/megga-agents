import { Refus } from "@/lib/agents";
import { atelier } from "@/lib/admin/atelier";
import { garde } from "@/lib/admin/garde";
import { TA } from "@/lib/admin/textes";

// Retirer une clé d'un logiciel, tout de suite, par son identifiant (12 caractères hexadécimaux, celui que la liste montre,
// jamais la clé elle-même) ; la réponse de l'atelier telle quelle.
type P = { id: string; cle: string };
const IDENTIFIANT = /^[0-9a-f]{12}$/;

export const DELETE = garde(
  {
    droit: "acces.gerer",
    client: (p: P) => p.id,
    action: "acces.cle_retiree",
    detail: (_, p) => ({ id: IDENTIFIANT.test(p.cle) ? p.cle : null }),
  },
  async ({ params }) => {
    if (!IDENTIFIANT.test(params.cle)) throw new Refus(400, TA.cleInvalide);
    return atelier.retirerCle(params.id, params.cle);
  },
);
