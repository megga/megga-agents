import { notFound } from "next/navigation";
import { Bandeau } from "@/components/admin/erreurs";
import { peut } from "@/lib/admin/acces";
import { atelier, ouRefus, RefusChamps, type Corps } from "@/lib/admin/atelier";
import { gardePage } from "@/lib/admin/garde";
import { TA } from "@/lib/admin/textes";
import { Cles, Jetons, Main, type CleVue } from "./acces";

// L'onglet Accès d'un client (acces.gerer, ou clients.piloter pour la main) : qui tient l'agent, reprendre ou rendre la main ;
// ses jetons (aucune route ne les liste) ; les clés de ses logiciels. Hors Cloudflare, ou jamais mis en service, l'atelier
// refuse de lister et de créer une clé (409) : sa phrase tient lieu de liste.

/** Une clé de la liste de l'atelier, sans rien d'autre que ce que l'écran montre. */
function cleVue(c: Corps): CleVue {
  const instant = (v: unknown) => (typeof v === "number" ? TA.moment(v) : null);
  return {
    id: String(c.id ?? ""),
    logiciel: String(c.logiciel ?? ""),
    parMinute: typeof c.par_minute === "number" ? c.par_minute : null,
    creeLe: instant(c.cree) ?? TA.inconnu,
    retireeLe: instant(c.retiree),
  };
}

export default async function PageAcces({ params }: PageProps<"/admin/clients/[id]/acces">) {
  const { id } = await params;
  const a = await gardePage(undefined, id);
  const piloter = peut(a, "clients.piloter");
  const gerer = peut(a, "acces.gerer");
  if (!piloter && !gerer) notFound();
  const [c, cles] = await Promise.all([ouRefus(atelier.client(id)), gerer ? ouRefus(atelier.cles(id)) : null]);
  if (c instanceof RefusChamps) {
    if (c.statut === 404) notFound();
    return <Bandeau>{c.message}</Bandeau>;
  }
  return (
    <>
      {piloter && <Main id={id} gere={c.gere_par_megga} />}
      {gerer && <Jetons id={id} />}
      {gerer &&
        (cles instanceof RefusChamps ? (
          <section className="flex flex-col gap-3">
            <h2 className="m-0 text-[18px] font-extrabold">{TA.clesLogiciels}</h2>
            <Bandeau etat={cles.statut === 409 ? "faint" : "accent"}>{cles.message}</Bandeau>
          </section>
        ) : (
          cles && <Cles id={id} cles={cles.cles.map(cleVue)} />
        ))}
    </>
  );
}

export const instant = false;
