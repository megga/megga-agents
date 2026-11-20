import Link from "next/link";
import { Onglets } from "./onglets";
import { Pastille, type Etat } from "./pastille";
import { Tableau } from "./tableau";
import type { Alerte, AlertesEnvoyees, EtatAlerte, Jours } from "@/lib/admin/atelier";
import { estEnCours, texteGenre } from "@/lib/admin/suivi";
import { TA } from "@/lib/admin/textes";

// Le tableau des alertes, partagé par l'écran Alertes (tous les clients du périmètre) et l'onglet Alertes d'un client :
// quoi (dit en clair, en cours ou résolue), quand, le client (sur l'écran de tous), le détail. Déjà triées par l'appelant.
// Côté serveur seulement (il lit suivi.ts).

/** En cours : un souci qui dure ; résolue : une panne de conteneur, avec son heure ; un fait passé n'a pas d'état. */
function EtatAlerte({ alerte }: { alerte: Alerte }) {
  if (estEnCours(alerte)) return <Pastille etat="accent" texte={TA.enCours} />;
  if (alerte.resolue) return <Pastille etat="ok" texte={TA.resolueLe(TA.moment(alerte.resolue))} />;
  return null;
}

export function TableauAlertes({ alertes, jours, avecClient = false }: {
  alertes: (Alerte & { client: string; nom?: string })[];
  jours: Jours;
  /** La colonne du client (son nom montré, sinon son identifiant) : sur l'écran de tous seulement. */
  avecClient?: boolean;
}) {
  const colonnes = [TA.quoi, TA.quand, ...(avecClient ? [TA.client] : []), TA.detail];
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
        ...(avecClient
          ? [
              <Link key="client" href={`/admin/clients/${encodeURIComponent(a.client)}/alertes?jours=${jours}`} className="font-semibold text-ink hover:underline">
                {a.nom ?? a.client}
              </Link>,
            ]
          : []),
        <span key="detail" className="text-[13px] break-words text-muted-ink">{a.detail}</span>,
      ])}
    />
  );
}

/** Les deux écrans des alertes : ce qui s'est passé, et les règles et envois. */
export function OngletsAlertes({ actif, regles }: { actif: string; regles: boolean }) {
  if (!regles) return null;
  return <Onglets onglets={[{ href: "/admin/alertes", texte: TA.alertes }, { href: "/admin/alertes/regles", texte: TA.reglesEtEnvois }]} actif={actif} />;
}

const ETAT_PASTILLE: Record<EtatAlerte["etat"], Etat> = { ok: "ok", avertissement: "warn", alerte: "accent", sans_donnees: "faint" };

/** Une valeur mesurée, dite avec son unité (oui ou non, %, nombre). */
function valeurDe(v: number | null, unite: string | undefined): string {
  if (v == null) return TA.inconnu;
  if (unite === "oui ou non") return v ? "oui" : "non";
  return TA.nombre(v) + (unite === "%" ? " %" : "");
}

/**
 * Les règles hors du bon état (alerte, avertissement, sans données), pour les clients que le membre voit ; noms : le nom de
 * chaque client. Rien quand tout va bien.
 */
export function EnAlerte({ envoyees, voit, noms }: { envoyees: AlertesEnvoyees; voit: (client: string) => boolean; noms: Map<string, string> }) {
  const regles = new Map(envoyees.regles.map((r) => [r.id, r]));
  const lignes = envoyees.etats
    .filter((e) => e.etat !== "ok" && voit(e.client))
    .sort((x, y) => (x.etat === "alerte" ? 0 : 1) - (y.etat === "alerte" ? 0 : 1) || y.depuis - x.depuis);
  if (!lignes.length) return null;
  return (
    <>
      <h2 className="m-0 text-[17px] font-extrabold">{TA.enAlerte}</h2>
      <Tableau
        colonnes={[TA.regle, TA.client, TA.valeur, TA.depuis]}
        vide={TA.videEnAlerte}
        replier={[2, 3]}
        lignes={lignes.map((e) => {
          const r = regles.get(e.regle);
          return [
            <span key="regle" className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <b className="font-bold">{r?.nom ?? e.regle}</b>
              <Pastille etat={ETAT_PASTILLE[e.etat]} texte={TA.etatsAlerte[e.etat] ?? e.etat} />
            </span>,
            <Link key="client" href={`/admin/clients/${encodeURIComponent(e.client)}`} className="font-semibold text-ink hover:underline">
              {noms.get(e.client) ?? e.client}
            </Link>,
            <span key="valeur" className="tabular-nums">{valeurDe(e.valeur, r ? envoyees.mesures[r.mesure]?.unite : undefined)}</span>,
            <span key="depuis" className="whitespace-nowrap">{TA.moment(e.depuis)}</span>,
          ];
        })}
      />
    </>
  );
}
