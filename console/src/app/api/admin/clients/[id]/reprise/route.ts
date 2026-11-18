import { Refus } from "@/lib/agents";
import { atelier } from "@/lib/admin/atelier";
import { garde } from "@/lib/admin/garde";
import { TA } from "@/lib/admin/textes";

// Reprendre la main sur un agent ({ gere_par_megga: true }) ou la rendre au client (false). Un vrai booléen seulement :
// sans lui, l'atelier reprendrait la main par défaut, ce que le membre n'a pas demandé.
const choix = (corps: unknown) => (corps as { gere_par_megga?: unknown } | null)?.gere_par_megga;

export const POST = garde(
  {
    droit: "clients.piloter",
    client: (p: { id: string }) => p.id,
    action: "clients.reprise",
    detail: (corps) => ({ gere_par_megga: typeof choix(corps) === "boolean" ? choix(corps) : null }),
  },
  async ({ params, corps }) => {
    const gere = choix(corps);
    if (typeof gere !== "boolean") throw new Refus(400, TA.repriseInvalide);
    return atelier.reprise(params.id, { gere_par_megga: gere });
  },
);
