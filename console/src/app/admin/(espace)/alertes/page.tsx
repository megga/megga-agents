import { Bandeau } from "@/components/admin/erreurs";
import { Onglets } from "@/components/admin/onglets";
import { ChoixPeriode } from "@/components/admin/periode";
import { atelier, ouRefus, RefusChamps } from "@/lib/admin/atelier";
import { gardePage } from "@/lib/admin/garde";
import { joursDe, lireTout, trierAlertes } from "@/lib/admin/suivi";
import { TA } from "@/lib/admin/textes";
import { TableauAlertes } from "./alertes";

// Les alertes de tous les clients du périmètre sur la période, les soucis en cours d'abord ; triées par date, par client
// ou par genre (?tri=). Un client injoignable est dit en tête ; les autres restent.

const TRIS = [
  { tri: "quand", texte: TA.parDate },
  { tri: "client", texte: TA.parClient },
  { tri: "genre", texte: TA.parGenre },
] as const;

type Tri = (typeof TRIS)[number]["tri"];

export default async function PageAlertes({ searchParams }: PageProps<"/admin/alertes">) {
  const a = await gardePage("clients.voir");
  const p = await searchParams;
  const jours = joursDe(p.jours);
  const tri: Tri = TRIS.find((t) => t.tri === p.tri)?.tri ?? "quand";
  const titre = <h1 className="m-0 text-[26px] font-extrabold tracking-[-0.02em]">{TA.alertes}</h1>;
  const r = await ouRefus(lireTout(a, jours, atelier));
  if (r instanceof RefusChamps) {
    return (
      <>
        {titre}
        <Bandeau>{r.message}</Bandeau>
      </>
    );
  }
  const noms = new Map(r.lectures.map((l) => [l.client.id, l.client.entreprise || l.client.id]));
  const injoignables = r.lectures.filter((l) => l.erreur).map((l) => noms.get(l.client.id));
  const alertes = trierAlertes(r.lectures.flatMap((l) => (l.alertes ?? []).map((x) => ({ ...x, client: l.client.id }))), tri);
  const adresse = (j: number, t: Tri) => `/admin/alertes?jours=${j}${t === "quand" ? "" : `&tri=${t}`}`;
  return (
    <>
      {titre}
      <div className="flex flex-wrap items-center gap-3">
        <ChoixPeriode jours={jours} chemin={tri === "quand" ? "/admin/alertes" : `/admin/alertes?tri=${tri}`} />
        <Onglets onglets={TRIS.map((t) => ({ href: adresse(jours, t.tri), texte: t.texte }))} actif={adresse(jours, tri)} />
      </div>
      {injoignables.length > 0 && <Bandeau etat="warn">{TA.injoignables(injoignables.join(", "))}</Bandeau>}
      <TableauAlertes alertes={alertes} jours={jours} clients={noms} />
    </>
  );
}

export const instant = false;
