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
