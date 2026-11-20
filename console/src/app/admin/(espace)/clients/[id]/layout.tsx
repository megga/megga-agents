import { notFound } from "next/navigation";
import { PastillesEtat } from "@/components/admin/pastille";
import { ongletsClient, peut } from "@/lib/admin/acces";
import { atelier, ouRefus, RefusChamps, type ClientAtelier } from "@/lib/admin/atelier";
import { gardePage } from "@/lib/admin/garde";
import { nomPays, paysTries } from "@/lib/admin/pays";
import { etatClient, horsCloudflare, zoneClient } from "@/lib/admin/suivi";
import { OngletsClient } from "./onglets";
import { ChoixPays } from "./pays";

/** La configuration de la dernière version, quand aucune n'est en service (pour sa zone) ; sinon rien à lire. */
async function derniereConfig(id: string, c: (ClientAtelier & { config: Record<string, unknown> | null }) | null) {
  if (!c || c.config || c.derniere_version == null) return null;
  const v = await ouRefus(atelier.version(id, c.derniere_version));
  return v instanceof RefusChamps ? null : (v.config ?? null);
}

// La fiche d'un client : son en-tête (entreprise, agent, identifiant, pays, état) et ses onglets. Hors périmètre ou inconnu de
// l'atelier : 404. L'atelier injoignable : l'en-tête se contente de l'identifiant, la page dit pourquoi.
export default async function FicheClient({ children, params }: LayoutProps<"/admin/clients/[id]">) {
  const { id } = await params;
  const a = await gardePage("clients.voir", id);
  const [c, catalogue] = await Promise.all([ouRefus(atelier.client(id)), ouRefus(atelier.catalogue())]);
  if (c instanceof RefusChamps && c.statut === 404) notFound();
  const lu = c instanceof RefusChamps ? null : c;
  // Hors Cloudflare : la zone de la version en service, sinon de la dernière, que la porte ne sert pas.
  const zone = zoneClient(lu?.config, await derniereConfig(id, lu));
  const estHorsCloudflare = horsCloudflare(zone, catalogue instanceof RefusChamps ? null : catalogue.zones_porte);
  return (
    <>
      <header className="flex min-w-0 flex-col gap-1.5">
        <h1 className="m-0 truncate text-[26px] font-extrabold tracking-[-0.02em]">{lu?.entreprise || id}</h1>
        <p className="m-0 flex flex-wrap gap-x-3 text-[14px] text-muted-ink">
          {lu?.nom_agent && <span className="font-semibold text-ink">{lu.nom_agent}</span>}
          <span>{id}</span>
          {lu && peut(a, "clients.creer") ? <ChoixPays id={id} pays={lu.pays ?? null} liste={paysTries()} /> : lu?.pays && <span>{nomPays(lu.pays)}</span>}
        </p>
        {lu && <PastillesEtat etat={etatClient(lu)} />}
      </header>
      <OngletsClient onglets={ongletsClient(a, id, estHorsCloudflare)} />
      {children}
    </>
  );
}

export const instant = false;
