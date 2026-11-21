import { Refus } from "@/lib/agents";
import { peutReglerForfaits } from "@/lib/admin/acces";
import { atelier } from "@/lib/admin/atelier";
import { estObjet } from "@/lib/admin/champs";
import { garde } from "@/lib/admin/garde";
import { TA } from "@/lib/admin/textes";

// Régler le catalogue des forfaits : il part entier à l'atelier, qui le valide et refuse de retirer un forfait encore pris.
// Réservé à un périmètre complet : un forfait vaut pour tous les clients. Le journal garde les identifiants, jamais un prix.

const ID = /^[a-z0-9][a-z0-9-]{1,39}$/;

function resume(corps: unknown) {
  if (!estObjet(corps) || !Array.isArray(corps.forfaits)) return null;
  return { forfaits: corps.forfaits.slice(0, 20).map((f) => (estObjet(f) && typeof f.id === "string" && ID.test(f.id) ? f.id : null)) };
}

export const PUT = garde({ droit: "tarifs.regler", action: "forfaits.regler", detail: resume }, async ({ acces, corps }) => {
  if (!peutReglerForfaits(acces)) throw new Refus(403, TA.sansDroit);
  if (!estObjet(corps)) throw new Refus(400, TA.forfaitsInvalides);
  return atelier.reglerForfaits(corps);
});
