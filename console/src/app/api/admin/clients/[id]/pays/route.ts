import { Refus } from "@/lib/agents";
import { atelier } from "@/lib/admin/atelier";
import { garde } from "@/lib/admin/garde";
import { estPays } from "@/lib/admin/pays";
import { TA } from "@/lib/admin/textes";

// Le pays du client sur la carte du monde : un code ISO à deux lettres de la liste, ou null pour le retirer. Un réglage de
// l'atelier, pas une version : aucun conteneur n'est touché. Le journal garde le code choisi.
const choix = (corps: unknown) => (corps as { pays?: unknown } | null)?.pays;

export const PUT = garde(
  {
    droit: "clients.creer",
    client: (p: { id: string }) => p.id,
    action: "clients.pays",
    detail: (corps) => ({ pays: estPays(choix(corps)) ? choix(corps) : null }),
  },
  async ({ params, corps }) => {
    const pays = choix(corps);
    if (pays !== null && !estPays(pays)) throw new Refus(400, TA.paysInvalide);
    return atelier.reglerPays(params.id, pays);
  },
);
