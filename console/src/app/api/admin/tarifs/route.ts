import { Refus } from "@/lib/agents";
import { atelier } from "@/lib/admin/atelier";
import { estObjet } from "@/lib/admin/champs";
import { garde } from "@/lib/admin/garde";
import { TA } from "@/lib/admin/textes";

// Régler les tarifs : le corps (les tarifs entiers) part tel quel à l'atelier, qui le valide et le garde ; la réponse est
// celle qu'il a gardée. Un refus de l'atelier rend sa phrase et ses messages champ par champ (garde, reponseRefus).
// Le journal se lit sans couts.voir : il ne garde que ce qui a été réglé, jamais un montant.

/** Ce que le journal garde d'une grille : la devise (des lettres seulement), les modèles réglés, voix et écoute réglées ou non. */
function reglage(corps: unknown) {
  if (!estObjet(corps)) return null;
  const devise = typeof corps.devise === "string" && /^[A-Za-z]{1,8}$/.test(corps.devise) ? corps.devise : null;
  const modeles = estObjet(corps.modeles) ? Object.keys(corps.modeles).sort() : [];
  return { devise, modeles, voix: corps.voix_par_1000_caracteres != null, ecoute: corps.par_vocal_entendu != null };
}

export const PUT = garde({ droit: "tarifs.regler", action: "tarifs.regler", detail: reglage }, async ({ corps }) => {
  if (!estObjet(corps)) throw new Refus(400, TA.tarifsInvalides);
  return atelier.reglerTarifs(corps);
});
