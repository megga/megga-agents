import { notFound } from "next/navigation";
import { TableauAlertes } from "@/components/admin/alertes";
import { Bandeau } from "@/components/admin/erreurs";
import { ChoixPeriode } from "@/components/admin/periode";
import { atelier, ouRefus, RefusChamps } from "@/lib/admin/atelier";
import { gardePage } from "@/lib/admin/garde";
import { joursDe, trierAlertes } from "@/lib/admin/suivi";
import { TA } from "@/lib/admin/textes";

// L'onglet Alertes d'un client : celles de la période, les soucis en cours d'abord, puis la plus récente. Jamais mis en
// service, il n'en a pas : l'atelier dirait « conteneur injoignable » d'un conteneur qui n'existe pas encore.
export default async function PageAlertesClient({ params, searchParams }: PageProps<"/admin/clients/[id]/alertes">) {
  const { id } = await params;
  await gardePage("clients.voir", id);
  const jours = joursDe((await searchParams).jours);
  const c = await ouRefus(atelier.client(id));
  if (c instanceof RefusChamps && c.statut === 404) notFound();
  if (!(c instanceof RefusChamps) && c.version_en_service == null) return <Bandeau etat="faint">{TA.jamaisSansAlerte}</Bandeau>;
  const r = await ouRefus(atelier.alertes(id, jours));
  const periode = <ChoixPeriode jours={jours} chemin={`/admin/clients/${encodeURIComponent(id)}/alertes`} />;
  if (r instanceof RefusChamps) {
    if (r.statut === 404) notFound();
    return <Bandeau>{r.message}</Bandeau>; // sans période : la changer n'y ferait rien
  }
  return (
    <>
      {periode}
      <TableauAlertes alertes={trierAlertes(r.alertes.map((a) => ({ ...a, client: id })), "quand")} jours={jours} />
    </>
  );
}

export const instant = false;
