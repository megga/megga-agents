import { Refus } from "@/lib/agents";
import { peutReglerAlertes } from "@/lib/admin/acces";
import { atelier } from "@/lib/admin/atelier";
import { estObjet } from "@/lib/admin/champs";
import { garde } from "@/lib/admin/garde";
import { TA } from "@/lib/admin/textes";

// Régler les alertes envoyées : la liste entière des règles part telle quelle à l'atelier, qui la valide et la garde.
// Réservé à un périmètre complet : une règle vaut pour tous les clients. Le journal garde l'identifiant et la mesure de
// chaque règle, rien d'autre.

const ID = /^[a-z0-9][a-z0-9-]{1,39}$/;
const MESURE = /^[a-z_]{1,30}$/;

function resume(corps: unknown) {
  if (!Array.isArray(corps)) return null;
  return corps.slice(0, 20).map((r) =>
    estObjet(r) ? { id: typeof r.id === "string" && ID.test(r.id) ? r.id : null, mesure: typeof r.mesure === "string" && MESURE.test(r.mesure) ? r.mesure : null } : null);
}

export const PUT = garde({ droit: "alertes.regler", action: "alertes.regles", detail: resume }, async ({ acces, corps }) => {
  if (!peutReglerAlertes(acces)) throw new Refus(403, TA.sansDroit);
  if (!Array.isArray(corps)) throw new Refus(400, TA.reglesInvalides);
  return atelier.reglerAlertes(corps);
});
