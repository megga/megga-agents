import Link from "next/link";
import { Barres } from "@/components/admin/barres";
import { Bandeau } from "@/components/admin/erreurs";
import { Pastille } from "@/components/admin/pastille";
import { ChoixPeriode } from "@/components/admin/periode";
import { Tableau } from "@/components/admin/tableau";
import { Tuile } from "@/components/admin/tuile";
import { peut, type Acces } from "@/lib/admin/acces";
import { atelier, ouRefus, RefusChamps, type Jours } from "@/lib/admin/atelier";
import { totauxConsole } from "@/lib/admin/comptes";
import { gardePage } from "@/lib/admin/garde";
import { agreger, joursDe, lireTout, texteGenre, type Souci } from "@/lib/admin/suivi";
import { TA } from "@/lib/admin/textes";
import { base } from "@/lib/base";

// La vue d'ensemble. Le bloc du moteur (clients.voir) : la période, les tuiles, « À surveiller », « Activité par client »,
// tout borné au périmètre du membre (lireTout ne lit que ses clients). Un client injoignable est dit, les autres restent.
// Avec couts.voir, la tuile et la colonne du coût, ce qui n'a pas de tarif et les clients dont le coût est illisible (absents
// du total). Le bloc de la console (comptes.voir, jamais un externe) : ses tuiles et ses barres, à la même période, mise alors
// en tête de page. Sans aucun des deux droits, la page n'a que son titre.

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

/** periode : le choix de la période, quand le bloc Console ne l'a pas déjà mis en tête de page. */
async function BlocMoteur({ jours, a, periode }: { jours: Jours; a: Acces; periode: boolean }) {
  const r = await ouRefus(lireTout(a, jours, atelier));
  if (r instanceof RefusChamps) return <Bandeau>{r.message}</Bandeau>; // sans période : la changer n'y ferait rien
  const v = agreger(r.lectures, a);
  const voitCouts = peut(a, "couts.voir");
  const cout = v.tuiles.cout; // seulement avec couts.voir et au moins un coût lisible (agreger)
  const noms = new Map(r.lectures.map((l) => [l.client.id, l.client.entreprise || l.client.id]));
  const lien = (id: string, onglet = "") => (
    <Link href={`/admin/clients/${encodeURIComponent(id)}${onglet}?jours=${jours}`} className="font-bold text-ink hover:underline">
      {noms.get(id) ?? id}
    </Link>
  );
  return (
    <>
      {periode && <ChoixPeriode jours={jours} chemin="/admin" />}
      {v.injoignables.length > 0 && <Bandeau etat="warn">{TA.injoignables(v.injoignables.map((id) => noms.get(id)).join(", "))}</Bandeau>}
      {v.coutsIllisibles.length > 0 && <Bandeau etat="warn">{TA.coutsIllisibles(v.coutsIllisibles.map((id) => noms.get(id)).join(", "))}</Bandeau>}
      <div className="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] gap-3">
        <Tuile titre={TA.clientsEnService} valeur={TA.nombre(v.tuiles.enService)} />
        <Tuile titre={TA.soucisEnCours} valeur={TA.nombre(v.tuiles.soucisEnCours)} etat={v.tuiles.soucisEnCours > 0 ? "accent" : "ok"} />
        <Tuile titre={TA.tours} valeur={TA.nombre(v.tuiles.tours)} />
        <Tuile titre={TA.personnes} valeur={TA.nombre(v.tuiles.personnes)} />
        {voitCouts && <Tuile titre={TA.cout} valeur={cout ? TA.montantEn(cout.total, cout.devise) : TA.inconnu} />}
      </div>
      {!!cout?.sansTarif.length && <Bandeau etat="warn">{TA.sansTarif(cout.sansTarif.map(TA.nomPoste).join(", "))}</Bandeau>}
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
        colonnes={[TA.client, TA.tours, TA.personnes, TA.echecs, TA.secours, ...(voitCouts ? [cout ? TA.coutEn(cout.devise) : TA.cout] : [])]}
        vide={TA.videActivite}
        replier={voitCouts ? [1, 2, 3, 4, 5] : [1, 2, 3, 4]}
        lignes={v.activite.map((x) => [
          <span key="client">{lien(x.client)}</span>,
          ...[x.tours, x.personnes, x.echecs, x.secours].map((n, i) => (
            <span key={i} className={"tabular-nums " + (i === 2 && n > 0 ? "font-semibold text-warn" : "")}>{TA.nombre(n)}</span>
          )),
          ...(voitCouts ? [<span key="cout" className="whitespace-nowrap tabular-nums">{x.cout === undefined ? TA.inconnu : TA.montant(x.cout)}</span>] : []),
        ])}
      />
    </>
  );
}

/**
 * La console (comptes.voir) : comptes et agents en tout, messages de la période ; inscriptions et messages par jour (jours
 * de Zurich). Sous le titre, ce que le bloc compte pour la période choisie.
 */
function BlocConsole({ jours }: { jours: Jours }) {
  const t = totauxConsole(base(), jours);
  return (
    <>
      <div className="flex flex-col gap-1">
        <h2 className="m-0 text-[17px] font-extrabold">{TA.console}</h2>
        <p className="m-0 text-[13px] text-muted-ink">{TA.periodeConsole(jours)}</p>
      </div>
      <div className="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] gap-3">
        <Tuile titre={TA.comptes} valeur={TA.nombre(t.comptes)} />
        <Tuile titre={TA.agents} valeur={TA.nombre(t.agents)} />
        <Tuile titre={TA.messages} valeur={TA.nombre(t.messages)} />
      </div>
      <Barres jours={t.parJour.map((j) => ({ jour: j.jour, valeurs: [j.inscriptions, j.messages] }))} legendes={[TA.inscriptions, TA.messages]} />
    </>
  );
}

export default async function VueEnsemble({ searchParams }: PageProps<"/admin">) {
  const a = await gardePage();
  const titre = <h1 className="m-0 text-[26px] font-extrabold tracking-[-0.02em]">{TA.vueEnsemble}</h1>;
  const moteur = peut(a, "clients.voir");
  const comptes = peut(a, "comptes.voir"); // jamais à un externe (droitsEffectifs)
  if (!moteur && !comptes) return titre;
  const jours = joursDe((await searchParams).jours);
  return (
    <>
      {titre}
      {comptes && <ChoixPeriode jours={jours} chemin="/admin" />}
      {moteur && <BlocMoteur jours={jours} a={a} periode={!comptes} />}
      {comptes && <BlocConsole jours={jours} />}
    </>
  );
}

export const instant = false;
