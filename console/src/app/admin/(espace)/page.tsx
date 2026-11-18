import { gardePage } from "@/lib/admin/garde";
import { TA } from "@/lib/admin/textes";

// La vue d'ensemble : son titre pour l'instant ; les tuiles et les tableaux viennent avec le client de l'atelier.
export default async function VueEnsemble() {
  await gardePage();
  return <h1 className="m-0 text-[26px] font-extrabold tracking-[-0.02em]">{TA.vueEnsemble}</h1>;
}

export const instant = false;
