import type { EtatClient } from "@/lib/admin/suivi";
import { TA } from "@/lib/admin/textes";

// Un état en une pastille : un point de couleur et un mot. Les quatre couleurs d'état des jetons, rien d'autre.

export type Etat = "ok" | "warn" | "accent" | "faint";

/** La couleur d'un état, en classes des jetons (aussi pour la valeur d'une tuile). */
export const TEXTE_ETAT: Record<Etat, string> = { ok: "text-ok", warn: "text-warn", accent: "text-marque", faint: "text-faint" };
const POINT: Record<Etat, string> = { ok: "bg-ok", warn: "bg-warn", accent: "bg-marque", faint: "bg-faint" };

export function Pastille({ etat, texte }: { etat: Etat; texte: string }) {
  return (
    <span className="trait inline-flex max-w-full items-center gap-1.5 rounded-full bg-bg px-2.5 py-0.5 text-[12.5px] font-semibold whitespace-nowrap text-ink">
      <span aria-hidden className={"size-2 flex-none rounded-full " + POINT[etat]} />
      <span className="truncate">{texte}</span>
    </span>
  );
}

/** L'état d'un client du moteur en pastilles : le service, l'écart, la main de MEGGA, le conteneur s'il est connu. */
export function PastillesEtat({ etat }: { etat: EtatClient }) {
  return (
    <span className="flex flex-wrap gap-1">
      {etat.service === "en_service" ? <Pastille etat="ok" texte={TA.enService} /> : <Pastille etat="faint" texte={TA.jamaisEnService} />}
      {etat.ecart && <Pastille etat="warn" texte={TA.ecart} />}
      {etat.tenuParMegga && <Pastille etat="faint" texte={TA.tenuParMegga} />}
      {etat.conteneur === "demarre" && <Pastille etat="ok" texte={TA.conteneurDemarre} />}
      {etat.conteneur === "arrete" && <Pastille etat="accent" texte={TA.conteneurArrete} />}
    </span>
  );
}
