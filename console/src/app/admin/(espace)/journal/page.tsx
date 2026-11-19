import { X } from "lucide-react";
import Link from "next/link";
import { Pastille, type Etat } from "@/components/admin/pastille";
import { Tableau } from "@/components/admin/tableau";
import { Avatar } from "@/components/console/avatar";
import { gardePage } from "@/lib/admin/garde";
import { filtresDe, lireJournal, type FiltresJournal, type LigneJournal } from "@/lib/admin/journal";
import { TA } from "@/lib/admin/textes";
import { pret } from "@/lib/base";

// Le journal : quand, qui, quoi, sur quoi, le résultat. Les filtres et la page passent par l'adresse (filtresDe) ;
// un membre limité à une liste n'y lit que ses gestes et ceux qui touchent ses clients (lireJournal). Dans un cadre étroit,
// toutes les colonnes sauf « Quand » se replient sous lui, Détail compris : le tableau ne défile pas de côté.

/** L'adresse du journal avec ces filtres ; la page 1 ne s'écrit pas. */
function adresse(f: FiltresJournal): string {
  const q = new URLSearchParams();
  for (const cle of ["membre", "action", "client", "depuis", "jusqua"] as const) if (f[cle]) q.set(cle, f[cle]!);
  if (f.page > 1) q.set("page", String(f.page));
  const s = q.toString();
  return "/admin/journal" + (s ? "?" + s : "");
}

/** « ok », « refuse 403 » ou « erreur », en pastille. */
function resultat(r: string): { etat: Etat; texte: string } {
  if (r === "ok") return { etat: "ok", texte: TA.reussi };
  if (r.startsWith("refuse ")) return { etat: "warn", texte: TA.refuse(r.slice(7)) };
  if (r === "erreur") return { etat: "accent", texte: TA.erreur };
  return { etat: "faint", texte: r };
}

/** Un détail coupé à 2048 caractères n'est plus du JSON : il est relu comme texte, et montré tel quel. */
function detailTexte(d: unknown): string {
  if (d === null || d === undefined) return "";
  return typeof d === "string" ? d : JSON.stringify(d);
}

const lien = "font-semibold text-ink hover:underline";
/** Une cible d'un seul tenant dans le tableau large ; repliée sous « Quand » (cadre étroit), elle se coupe où il faut. */
const cibleRepliee = "whitespace-nowrap @max-5xl:whitespace-normal @max-5xl:wrap-anywhere";

export default async function PageJournal({ searchParams }: PageProps<"/admin/journal">) {
  const a = await gardePage("journal.voir");
  const f = filtresDe(await searchParams);
  const { lignes, pages, page } = await lireJournal(await pret(), a, f); // page : ramenée à la dernière si l'adresse va trop loin
  const avec = (changer: Partial<FiltresJournal>) => adresse({ ...f, page: 1, ...changer });
  const qui = (l: LigneJournal) =>
    l.qui ? (
      <span key="qui" className="flex items-center gap-2">
        <Avatar nom={l.courriel ?? l.qui} image={l.image} taille={24} />
        <Link href={avec({ membre: l.qui })} title={TA.filtrerSur} className={lien + " whitespace-nowrap"}>
          {l.courriel ?? l.qui}
        </Link>
      </span>
    ) : (
      <span key="qui" className="whitespace-nowrap text-muted-ink">{TA.leServeur}</span>
    );
  const cible = (c: string | null) =>
    c?.startsWith("client:") ? (
      <Link key="cible" href={avec({ client: c.slice(7) })} title={TA.filtrerSur} className={lien + " " + cibleRepliee}>
        {c}
      </Link>
    ) : (
      <span key="cible" className={cibleRepliee}>{c ?? ""}</span>
    );

  const membreFiltre = f.membre && (lignes.find((l) => l.qui === f.membre)?.courriel ?? f.membre);
  const actifs = [
    f.membre && { texte: TA.filtreSur(TA.filtreMembre, membreFiltre || f.membre), sans: avec({ membre: undefined }) },
    f.action && { texte: TA.filtreSur(TA.filtreAction, TA.actionsJournal[f.action] ?? f.action), sans: avec({ action: undefined }) },
    f.client && { texte: TA.filtreSur(TA.filtreClient, f.client), sans: avec({ client: undefined }) },
  ].filter((x): x is { texte: string; sans: string } => !!x);

  return (
    <>
      <h1 className="m-0 text-[26px] font-extrabold tracking-[-0.02em]">{TA.journal}</h1>

      <form action="/admin/journal" className="flex flex-wrap items-end gap-3">
        {(["membre", "action", "client"] as const).map((cle) => f[cle] && <input key={cle} type="hidden" name={cle} value={f[cle]} />)}
        <label className="flex flex-col gap-1.5 text-[13px] font-semibold text-muted-ink">
          {TA.depuis}
          <input type="date" name="depuis" defaultValue={f.depuis} className="trait h-10 rounded-xl bg-bg px-3 text-[14.5px] text-ink" />
        </label>
        <label className="flex flex-col gap-1.5 text-[13px] font-semibold text-muted-ink">
          {TA.jusqua}
          <input type="date" name="jusqua" defaultValue={f.jusqua} className="trait h-10 rounded-xl bg-bg px-3 text-[14.5px] text-ink" />
        </label>
        <button type="submit" className="h-10 rounded-full bg-ink px-5 text-[14px] font-bold text-bg">
          {TA.filtrer}
        </button>
        {(actifs.length > 0 || f.depuis || f.jusqua) && (
          <Link href="/admin/journal" className="flex h-10 items-center px-2 text-[14px] font-semibold text-muted-ink hover:text-ink">
            {TA.effacerFiltres}
          </Link>
        )}
      </form>

      {actifs.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {actifs.map((x) => (
            <Link key={x.texte} href={x.sans} className="trait inline-flex items-center gap-1.5 rounded-full bg-bg px-3 py-1 text-[13px] font-semibold text-ink hover:bg-hover">
              {x.texte}
              <X aria-hidden className="size-3.5 text-muted-ink" />
            </Link>
          ))}
        </div>
      )}

      <Tableau
        colonnes={[TA.quand, TA.qui, TA.quoi, TA.surQuoi, TA.resultat, TA.detail]}
        vide={TA.videJournal}
        replier={[1, 2, 3, 4, 5]}
        lignes={lignes.map((l) => {
          const r = resultat(l.resultat);
          return [
            <span key="quand" className="whitespace-nowrap">{TA.instant(l.quand)}</span>,
            qui(l),
            <Link key="quoi" href={avec({ action: l.action })} title={TA.filtrerSur} className={lien + " whitespace-nowrap"}>
              {TA.actionsJournal[l.action] ?? l.action}
            </Link>,
            cible(l.cible),
            <Pastille key="resultat" etat={r.etat} texte={r.texte} />,
            <span key="detail" className="block max-w-[340px] min-w-[200px] text-[12.5px] wrap-anywhere text-muted-ink">{detailTexte(l.detail)}</span>,
          ];
        })}
      />

      {pages > 1 && (
        <nav className="flex flex-wrap items-center gap-3 text-[14px]">
          {page > 1 && (
            <Link href={adresse({ ...f, page: page - 1 })} className={"trait rounded-full bg-bg px-3.5 py-1.5 " + lien}>
              {TA.pagePrecedente}
            </Link>
          )}
          <span className="text-muted-ink">{TA.pageSur(page, pages)}</span>
          {page < pages && (
            <Link href={adresse({ ...f, page: page + 1 })} className={"trait rounded-full bg-bg px-3.5 py-1.5 " + lien}>
              {TA.pageSuivante}
            </Link>
          )}
        </nav>
      )}
    </>
  );
}

export const instant = false;
