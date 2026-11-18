import { notFound } from "next/navigation";
import { ongletsClient } from "@/lib/admin/acces";
import { atelier, ouRefus, RefusChamps } from "@/lib/admin/atelier";
import { gardePage } from "@/lib/admin/garde";
import { etatClient } from "@/lib/admin/suivi";
import { PastillesEtat } from "../clients";
import { OngletsClient } from "./onglets";

// La fiche d'un client : son en-tête (entreprise, agent, identifiant, état) et ses onglets. Hors périmètre ou inconnu de
// l'atelier : 404. L'atelier injoignable : l'en-tête se contente de l'identifiant, la page dit pourquoi.
export default async function FicheClient({ children, params }: LayoutProps<"/admin/clients/[id]">) {
  const { id } = await params;
  const a = await gardePage("clients.voir", id);
  const [c, catalogue] = await Promise.all([ouRefus(atelier.client(id)), ouRefus(atelier.catalogue())]);
  if (c instanceof RefusChamps && c.statut === 404) notFound();
  const lu = c instanceof RefusChamps ? null : c;
  const zone = typeof lu?.config?.zone === "string" ? lu.config.zone : null;
  // Hors Cloudflare : une zone que la porte ne sert pas ; sans configuration en service, une installation enregistrée.
  const horsCloudflare = zone !== null && !(catalogue instanceof RefusChamps) ? !catalogue.zones_porte.includes(zone) : !!lu?.installation;
  return (
    <>
      <header className="flex min-w-0 flex-col gap-1.5">
        <h1 className="m-0 truncate text-[26px] font-extrabold tracking-[-0.02em]">{lu?.entreprise || id}</h1>
        <p className="m-0 flex flex-wrap gap-x-3 text-[14px] text-muted-ink">
          {lu?.nom_agent && <span className="font-semibold text-ink">{lu.nom_agent}</span>}
          <span>{id}</span>
        </p>
        {lu && <PastillesEtat etat={etatClient(lu)} />}
      </header>
      <OngletsClient onglets={ongletsClient(a, id, horsCloudflare)} />
      {children}
    </>
  );
}

export const instant = false;
