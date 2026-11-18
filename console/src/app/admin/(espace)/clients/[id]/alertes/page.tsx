import { notFound } from "next/navigation";
import { Bandeau } from "@/components/admin/erreurs";
import { ChoixPeriode } from "@/components/admin/periode";
import { atelier, ouRefus, RefusChamps } from "@/lib/admin/atelier";
import { gardePage } from "@/lib/admin/garde";
import { joursDe, trierAlertes } from "@/lib/admin/suivi";
import { TableauAlertes } from "../../../alertes/alertes";

// L'onglet Alertes d'un client : celles de la période, les soucis en cours d'abord, puis la plus récente.
export default async function PageAlertesClient({ params, searchParams }: PageProps<"/admin/clients/[id]/alertes">) {
  const { id } = await params;
  await gardePage("clients.voir", id);
  const jours = joursDe((await searchParams).jours);
  const r = await ouRefus(atelier.alertes(id, jours));
  const periode = <ChoixPeriode jours={jours} chemin={`/admin/clients/${encodeURIComponent(id)}/alertes`} />;
  if (r instanceof RefusChamps) {
    if (r.statut === 404) notFound();
    return (
      <>
        {periode}
        <Bandeau>{r.message}</Bandeau>
      </>
    );
  }
  return (
    <>
      {periode}
      <TableauAlertes alertes={trierAlertes(r.alertes.map((a) => ({ ...a, client: id })), "quand")} jours={jours} />
    </>
  );
}

export const instant = false;
