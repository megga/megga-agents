import { Refus } from "@/lib/agents";
import { atelier, type Corps } from "@/lib/admin/atelier";
import { garde } from "@/lib/admin/garde";
import { TA } from "@/lib/admin/textes";

// Régler les tarifs : le corps (les tarifs entiers) part tel quel à l'atelier, qui le valide et le garde ; la réponse est
// celle qu'il a gardée. Un refus de l'atelier rend sa phrase et ses messages champ par champ (garde, reponseRefus).
const estObjet = (v: unknown): v is Corps => !!v && typeof v === "object" && !Array.isArray(v);

export const PUT = garde({ droit: "tarifs.regler", action: "tarifs.regler" }, async ({ corps }) => {
  if (!estObjet(corps)) throw new Refus(400, TA.tarifsInvalides);
  return atelier.reglerTarifs(corps);
});
