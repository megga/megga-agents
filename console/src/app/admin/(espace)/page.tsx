import Link from "next/link";
import { Bandeau } from "@/components/admin/erreurs";
import { Pastille } from "@/components/admin/pastille";
import { ChoixPeriode } from "@/components/admin/periode";
import { Tableau } from "@/components/admin/tableau";
import { Tuile } from "@/components/admin/tuile";
import { peut, type Acces } from "@/lib/admin/acces";
import { atelier, ouRefus, RefusChamps, type Jours } from "@/lib/admin/atelier";
import { gardePage } from "@/lib/admin/garde";
import { agreger, joursDe, lireTout, texteGenre, type Souci } from "@/lib/admin/suivi";
import { TA } from "@/lib/admin/textes";

// La vue d'ensemble. Le bloc du moteur (clients.voir) : la période, les tuiles, « À surveiller », « Activité par client »,
// tout borné au périmètre du membre (lireTout ne lit que ses clients). Un client injoignable est dit, les autres restent.
// Sans clients.voir, la page n'a que son titre.

/** Les soucis d'un client, un par genre : ceux en cours d'abord, puis les plus nombreux. */
function parGenre(soucis: Souci[]): { genre: string; enCours: boolean; nombre: number }[] {
  const groupes = new Map<string, { genre: string; enCours: boolean; nombre: number }>();
  for (const s of soucis) {
    const cle = `${s.enCours}:${s.genre}`;
    const g = groupes.get(cle) ?? { genre: s.genre, enCours: s.enCours, nombre: 0 };
    g.nombre++;
    groupes.set(cle, g);
  }
  return [...groupes.values()].sort((a, b) => Number(b.enCours) - Number(a.enCours) || b.nombre - a.nombre);
}

async function BlocMoteur({ jours, a }: { jours: Jours; a: Acces }) {
  const r = await ouRefus(lireTout(a, jours, atelier));
  if (r instanceof RefusChamps) return <Bandeau>{r.message}</Bandeau>; // sans période : la changer n'y ferait rien
  const v = agreger(r.lectures, a);
  const noms = new Map(r.lectures.map((l) => [l.client.id, l.client.entreprise || l.client.id]));
  const lien = (id: string, onglet = "") => (
    <Link href={`/admin/clients/${encodeURIComponent(id)}${onglet}?jours=${jours}`} className="font-bold text-ink hover:underline">
      {noms.get(id) ?? id}
    </Link>
  );
  return (
    <>
      <ChoixPeriode jours={jours} chemin="/admin" />
      {v.injoignables.length > 0 && <Bandeau etat="warn">{TA.injoignables(v.injoignables.map((id) => noms.get(id)).join(", "))}</Bandeau>}
      <div className="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] gap-3">
        <Tuile titre={TA.clientsEnService} valeur={TA.nombre(v.tuiles.enService)} />
        <Tuile titre={TA.soucisEnCours} valeur={TA.nombre(v.tuiles.soucisEnCours)} etat={v.tuiles.soucisEnCours > 0 ? "accent" : "ok"} />
        <Tuile titre={TA.tours} valeur={TA.nombre(v.tuiles.tours)} />
        <Tuile titre={TA.personnes} valeur={TA.nombre(v.tuiles.personnes)} />
      </div>
      <h2 className="m-0 text-[17px] font-extrabold">{TA.aSurveiller}</h2>
      <Tableau
        colonnes={[TA.client, TA.soucis]}
        vide={TA.videASurveiller}
        replier={[1]}
        lignes={v.aSurveiller.map((x) => [
          <span key="client">{lien(x.client, "/alertes")}</span>,
          <span key="soucis" className="flex flex-wrap gap-1">
            {parGenre(x.soucis).map((g) => (
              <Pastille key={`${g.enCours}:${g.genre}`} etat={g.enCours ? "accent" : "warn"} texte={TA.avecNombre(texteGenre(g.genre), g.nombre)} />
            ))}
          </span>,
        ])}
      />
      <h2 className="m-0 text-[17px] font-extrabold">{TA.activiteParClient}</h2>
      <Tableau
        colonnes={[TA.client, TA.tours, TA.personnes, TA.echecs, TA.secours]}
        vide={TA.videActivite}
        replier={[1, 2, 3, 4]}
        lignes={v.activite.map((x) => [
          <span key="client">{lien(x.client)}</span>,
          ...[x.tours, x.personnes, x.echecs, x.secours].map((n, i) => (
            <span key={i} className={"tabular-nums " + (i === 2 && n > 0 ? "font-semibold text-warn" : "")}>{TA.nombre(n)}</span>
          )),
        ])}
      />
    </>
  );
}

export default async function VueEnsemble({ searchParams }: PageProps<"/admin">) {
  const a = await gardePage();
  const titre = <h1 className="m-0 text-[26px] font-extrabold tracking-[-0.02em]">{TA.vueEnsemble}</h1>;
  if (!peut(a, "clients.voir")) return titre;
  const jours = joursDe((await searchParams).jours);
  return (
    <>
      {titre}
      <BlocMoteur jours={jours} a={a} />
    </>
  );
}

export const instant = false;
