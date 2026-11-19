import Link from "next/link";
import { Pastille } from "@/components/admin/pastille";
import { Tableau } from "@/components/admin/tableau";
import { Avatar } from "@/components/console/avatar";
import { filtresComptesDe, listerComptes, type FiltresComptes } from "@/lib/admin/comptes";
import { gardePage } from "@/lib/admin/garde";
import { TA } from "@/lib/admin/textes";
import { pret } from "@/lib/base";

// Les comptes de la console (comptes.voir, jamais un externe) : entreprise et courriel, inscription, dernière connexion, agents,
// messages sur 30 jours, état, membre de l'admin ou non. Lu ici, côté serveur, par pages de 50 ; la recherche (?q=) et la page
// (?page=) passent par l'adresse. Rien ne part au navigateur que ce tableau. Dans un cadre étroit, les colonnes secondaires se
// replient sous le compte.

/** L'adresse de la liste avec cette recherche et cette page ; la page 1 ne s'écrit pas. */
function adresse(f: FiltresComptes): string {
  const q = new URLSearchParams();
  if (f.q) q.set("q", f.q);
  if (f.page > 1) q.set("page", String(f.page));
  const s = q.toString();
  return "/admin/comptes" + (s ? "?" + s : "");
}

const lien = "font-semibold text-ink hover:underline";

export default async function PageComptes({ searchParams }: PageProps<"/admin/comptes">) {
  await gardePage("comptes.voir");
  const f = filtresComptesDe(await searchParams);
  const { comptes, pages, page } = await listerComptes(await pret(), f); // page : ramenée à la dernière si l'adresse va trop loin
  return (
    <>
      <h1 className="m-0 text-[26px] font-extrabold tracking-[-0.02em]">{TA.comptes}</h1>
      <form action="/admin/comptes" role="search" className="flex flex-wrap items-center gap-2">
        <input
          type="search"
          name="q"
          defaultValue={f.q}
          aria-label={TA.rechercherCompte}
          placeholder={TA.rechercherCompte}
          maxLength={100}
          className="trait h-10 min-w-0 flex-1 basis-56 rounded-xl bg-bg px-3 text-[14.5px] text-ink placeholder:text-faint"
        />
        <button type="submit" className="h-10 rounded-full bg-ink px-5 text-[14px] font-bold text-bg">
          {TA.rechercher}
        </button>
        {f.q && (
          <Link href="/admin/comptes" className="flex h-10 items-center px-2 text-[14px] font-semibold text-muted-ink hover:text-ink">
            {TA.effacerRecherche}
          </Link>
        )}
      </form>
      <Tableau
        colonnes={[TA.compte, TA.inscritLe, TA.derniereConnexion, TA.agents, TA.messages30j, TA.etat, TA.membreAdmin]}
        vide={f.q ? TA.aucunCompteTrouve : TA.videComptes}
        replier={[1, 2, 3, 4, 5, 6]}
        lignes={comptes.map((c) => [
          <div key="compte" className="flex min-w-0 items-center gap-2.5">
            <Avatar nom={c.entreprise || c.courriel} image={c.image} taille={32} />
            <div className="flex min-w-0 flex-col">
              <Link href={`/admin/comptes/${encodeURIComponent(c.id)}`} className="font-bold wrap-anywhere text-ink hover:underline">
                {c.entreprise || c.courriel}
              </Link>
              <span className="text-[13px] wrap-anywhere text-muted-ink">{c.courriel}</span>
            </div>
          </div>,
          <span key="inscrit" className="whitespace-nowrap">{TA.instant(c.inscritLe)}</span>,
          <span key="connexion" className="whitespace-nowrap">{c.derniereConnexion ? TA.instant(c.derniereConnexion) : TA.pasEncoreNotee}</span>,
          <span key="agents" className="tabular-nums">{TA.nombre(c.agents)}</span>,
          <span key="messages" className="tabular-nums">{TA.nombre(c.messages30j)}</span>,
          c.suspendu ? <Pastille key="etat" etat="accent" texte={TA.suspendu} /> : <Pastille key="etat" etat="ok" texte={TA.actif} />,
          <span key="membre">{c.membre ? TA.oui : TA.non}</span>,
        ])}
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
