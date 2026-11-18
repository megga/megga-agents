import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { DROITS_EXTERNE } from "@/lib/admin/droits";
import { TA } from "@/lib/admin/textes";

// Les pièces de formulaire de l'admin : les classes d'un champ et de son étiquette, le périmètre et la fin d'accès d'un
// membre ou d'une invitation, le périmètre tel qu'un membre le voit, ce qu'un externe garde.

export const champ = "h-10 rounded-xl bg-bg px-3 text-[14.5px] text-ink placeholder:text-faint";
export const etiquette = "text-[13px] font-semibold text-muted-ink";
/** Une zone de texte sur plusieurs lignes (du JSON, une clé publique), aux contours d'un champ. */
export const zoneTexte =
  "trait min-h-28 w-full min-w-0 rounded-xl bg-bg px-3 py-2 text-[14px] text-ink outline-none placeholder:text-faint focus-visible:border-trait-fort";

/** Un rôle proposé dans un formulaire. */
export type RoleChoix = { id: string; nom: string };

/** Le périmètre d'un autre tel que le membre le voit (perimetreVu, côté serveur). */
export type Vu = "tous" | { clients: string[]; autres: number };

/** Le périmètre tel que le membre le voit : les clients qu'il partage, les autres comptés. */
export function PerimetreVu({ p }: { p: Vu }) {
  if (p === "tous") return <span className="whitespace-nowrap">{TA.tousLesClients}</span>;
  if (!p.clients.length) return <span className="text-muted-ink">{p.autres ? TA.nClients(p.autres) : TA.aucunClient}</span>;
  return (
    <span className="block max-w-[260px]">
      {p.clients.join(", ")}
      {p.autres > 0 && <span className="text-muted-ink"> {TA.etAutres(p.autres)}</span>}
    </span>
  );
}

/** Le corps d'un périmètre : « tous », ou les identifiants tapés, séparés par des virgules ou des espaces. */
export function perimetreDe(mode: "tous" | "liste", liste: string): "tous" | string[] {
  return mode === "tous" ? "tous" : liste.split(/[\s,;]+/).filter(Boolean);
}

/** « Tous les clients » n'est permis ni à un externe, ni par un membre limité à une liste. */
export const tousPossible = (externe: boolean, tousPermis: boolean) => tousPermis && !externe;

/**
 * Le périmètre et la fin d'accès d'un membre ou d'une invitation. tous : « tous les clients » est-il permis
 * (tousPossible) ; sinon, la liste seule, et le corps se fait avec perimetreDe("liste", …).
 */
export function ChampsAcces(p: {
  id: string;
  tous: boolean;
  mode: "tous" | "liste";
  liste: string;
  fin: string;
  onMode: (m: "tous" | "liste") => void;
  onListe: (v: string) => void;
  onFin: (v: string) => void;
}) {
  const { tous } = p;
  const mode = tous ? p.mode : "liste";
  return (
    <>
      <fieldset className="m-0 flex flex-col gap-1.5 border-0 p-0">
        <legend className={etiquette + " mb-1.5"}>{TA.perimetre}</legend>
        <div className="flex flex-wrap gap-x-4 gap-y-1.5 text-[14px]">
          <label className="flex items-center gap-2">
            <input type="radio" name={p.id + "-mode"} checked={mode === "tous"} disabled={!tous} onChange={() => p.onMode("tous")} className="accent-marque" />
            <span className={tous ? "" : "text-faint"}>{TA.tousLesClients}</span>
          </label>
          <label className="flex items-center gap-2">
            <input type="radio" name={p.id + "-mode"} checked={mode === "liste"} onChange={() => p.onMode("liste")} className="accent-marque" />
            {TA.uneListe}
          </label>
        </div>
        {mode === "liste" && (
          <>
            <Input aria-label={TA.uneListe} value={p.liste} onChange={(e) => p.onListe(e.target.value)} className={champ} />
            <span className="text-[12.5px] text-faint">{TA.perimetreAide}</span>
          </>
        )}
      </fieldset>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor={p.id + "-fin"} className={etiquette}>{TA.finAcces}</Label>
        <Input id={p.id + "-fin"} type="date" value={p.fin} onChange={(e) => p.onFin(e.target.value)} className={champ} />
        <span className="text-[12.5px] text-faint">{TA.finAccesAide}</span>
      </div>
    </>
  );
}

/** Ce qu'un externe garde, quel que soit son rôle : à l'invitation, et quand on change le rôle d'un externe. */
export function ExterneGarde() {
  return (
    <div className="rounded-xl bg-side px-3.5 py-2.5 text-[13.5px] text-muted-ink">
      <p className="m-0">{TA.externeGarde}</p>
      <ul className="m-0 mt-1 pl-5">
        {DROITS_EXTERNE.map((d) => (
          <li key={d}>{TA.nomsDroits[d]}</li>
        ))}
      </ul>
    </div>
  );
}
