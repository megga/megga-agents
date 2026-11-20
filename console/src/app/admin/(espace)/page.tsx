import Link from "next/link";
import { Barres } from "@/components/admin/barres";
import { Bandeau } from "@/components/admin/erreurs";
import { Pastille, type Etat } from "@/components/admin/pastille";
import { ChoixPeriode } from "@/components/admin/periode";
import { Tableau } from "@/components/admin/tableau";
import { Tuile } from "@/components/admin/tuile";
import { peut, type Acces } from "@/lib/admin/acces";
import { atelier, ouRefus, RefusChamps, type Jours } from "@/lib/admin/atelier";
import { totauxConsole } from "@/lib/admin/comptes";
import { gardePage } from "@/lib/admin/garde";
import { agregerReleves, type Sante } from "@/lib/admin/releves";
import { joursDe } from "@/lib/admin/suivi";
import { TA } from "@/lib/admin/textes";
import { pret } from "@/lib/base";

// La vue d'ensemble. Le bloc du moteur (clients.voir) : la période, les tuiles, les tours et le coût jour par jour, la santé de
// chaque client, la pire d'abord ; tout vient du relevé chiffré (une lecture pour tous les clients, aucun conteneur réveillé,
// jamais une conversation), borné au périmètre du membre. Avec couts.voir, le coût. Le bloc de la console (comptes.voir,
// jamais un externe) : ses tuiles et ses barres, à la même période, mise alors en tête de page.

const COULEUR: Record<Sante, Etat> = { silencieux: "accent", panne: "accent", ecart: "warn", echecs: "warn", ok: "ok" };

/** periode : le choix de la période, quand le bloc Console ne l'a pas déjà mis en tête de page. */
async function BlocMoteur({ jours, a, periode }: { jours: Jours; a: Acces; periode: boolean }) {
  const r = await ouRefus(atelier.releves(jours));
  if (r instanceof RefusChamps) return <Bandeau>{r.message}</Bandeau>; // sans période : la changer n'y ferait rien
  const v = agregerReleves(r, a);
  const voitCouts = peut(a, "couts.voir");
  const cout = v.tuiles.cout;
  return (
    <>
      {periode && <ChoixPeriode jours={jours} chemin="/admin" />}
      <div className="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] gap-3">
        <Tuile titre={TA.clientsEnService} valeur={TA.nombre(v.tuiles.enService)} />
        <Tuile titre={TA.aSurveiller} valeur={TA.nombre(v.tuiles.aSurveiller)} etat={v.tuiles.aSurveiller > 0 ? "accent" : "ok"} />
        <Tuile titre={TA.tours} valeur={TA.nombre(v.tuiles.tours)} />
        <Tuile titre={TA.echecs} valeur={TA.nombre(v.tuiles.echecs)} etat={v.tuiles.echecs > 0 ? "warn" : undefined} />
        {cout && <Tuile titre={TA.cout} valeur={TA.montantEn(cout.total, cout.devise)} />}
      </div>
      {v.sansTarif.length > 0 && <Bandeau etat="warn">{TA.sansTarif(v.sansTarif.map(TA.nomPoste).join(", "))}</Bandeau>}
      <Barres
        jours={v.parJour.map((j) => ({ jour: j.jour, valeurs: cout ? [j.tours, j.cout] : [j.tours] }))}
        legendes={cout ? [TA.toursParJour, TA.coutParJour(cout.devise)] : [TA.toursParJour]}
      />
      <h2 className="m-0 text-[17px] font-extrabold">{TA.sante}</h2>
      <Tableau
        colonnes={[TA.client, TA.sante, TA.tours, TA.echecs, TA.secours, TA.reponseMoyenne, ...(voitCouts && cout ? [TA.coutEn(cout.devise)] : [])]}
        vide={TA.videSante}
        replier={voitCouts ? [2, 3, 4, 5, 6] : [2, 3, 4, 5]}
        lignes={v.lignes.map((l) => [
          <Link key="client" href={`/admin/clients/${encodeURIComponent(l.client)}?jours=${jours}`} className="font-bold text-ink hover:underline">
            {l.entreprise || l.client}
          </Link>,
          <Pastille key="sante" etat={COULEUR[l.sante]} texte={TA.santes[l.sante]} />,
          ...[l.tours, l.echecs, l.secours].map((n, i) => (
            <span key={i} className={"tabular-nums " + (i === 1 && n > 0 ? "font-semibold text-warn" : "")}>{TA.nombre(n)}</span>
          )),
          <span key="reponse" className="whitespace-nowrap tabular-nums">{l.reponse === null ? TA.inconnu : TA.secondes(l.reponse)}</span>,
          ...(l.cout !== undefined ? [<span key="cout" className="whitespace-nowrap tabular-nums">{TA.montant(l.cout)}</span>] : []),
        ])}
      />
    </>
  );
}

/**
 * La console (comptes.voir) : comptes et agents en tout, messages de la période ; inscriptions et messages par jour (jours
 * de Zurich). Sous le titre, ce que le bloc compte pour la période choisie.
 */
async function BlocConsole({ jours }: { jours: Jours }) {
  const t = await totauxConsole(await pret(), jours);
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
