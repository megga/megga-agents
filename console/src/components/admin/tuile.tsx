import { TEXTE_ETAT, type Etat } from "./pastille";

// Une tuile : un titre et un chiffre, la couleur d'un état si le chiffre en porte un.

export function Tuile({ titre, valeur, etat }: { titre: string; valeur: string; etat?: Etat }) {
  return (
    <div className="trait flex min-w-0 flex-col gap-1 rounded-2xl bg-bg px-4 pt-3 pb-3.5">
      <span className="truncate text-[12.5px] font-semibold text-muted-ink">{titre}</span>
      <b className={"truncate text-[26px] leading-tight font-extrabold tracking-[-0.02em] " + (etat ? TEXTE_ETAT[etat] : "text-ink")}>{valeur}</b>
    </div>
  );
}
