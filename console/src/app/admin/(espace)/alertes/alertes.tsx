import Link from "next/link";
import { Pastille } from "@/components/admin/pastille";
import { Tableau } from "@/components/admin/tableau";
import type { Alerte, Jours } from "@/lib/admin/atelier";
import { estEnCours, texteGenre } from "@/lib/admin/suivi";
import { TA } from "@/lib/admin/textes";

// Le tableau des alertes, partagé par l'écran Alertes (tous les clients du périmètre) et l'onglet Alertes d'un client :
// quoi (dit en clair, en cours ou résolue), quand, le client (sur l'écran de tous), le détail. Déjà triées par l'appelant.

/** En cours : un souci qui dure ; résolue : une panne de conteneur, avec son heure ; un fait passé n'a pas d'état. */
function EtatAlerte({ alerte }: { alerte: Alerte }) {
  if (estEnCours(alerte)) return <Pastille etat="accent" texte={TA.enCours} />;
  if (alerte.resolue) return <Pastille etat="ok" texte={TA.resolueLe(TA.moment(alerte.resolue))} />;
  return null;
}

export function TableauAlertes({ alertes, jours, clients }: {
  alertes: (Alerte & { client: string })[];
  jours: Jours;
  /** Les clients (identifiant, nom montré) : leur colonne n'apparaît que sur l'écran de tous. */
  clients?: Map<string, string>;
}) {
  const colonnes = [TA.quoi, TA.quand, ...(clients ? [TA.client] : []), TA.detail];
  return (
    <Tableau
      colonnes={colonnes}
      vide={TA.videAlertes}
      replier={colonnes.map((_, i) => i).slice(1)}
      lignes={alertes.map((a) => [
        <span key="quoi" className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <b className="font-bold">{texteGenre(a.genre)}</b>
          <EtatAlerte alerte={a} />
        </span>,
        <span key="quand" className="whitespace-nowrap">{TA.moment(a.quand)}</span>,
        ...(clients
          ? [
              <Link key="client" href={`/admin/clients/${encodeURIComponent(a.client)}/alertes?jours=${jours}`} className="font-semibold text-ink hover:underline">
                {clients.get(a.client) ?? a.client}
              </Link>,
            ]
          : []),
        <span key="detail" className="text-[13px] break-words text-muted-ink">{a.detail}</span>,
      ])}
    />
  );
}
