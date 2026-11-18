import { notFound } from "next/navigation";
import { Bandeau } from "@/components/admin/erreurs";
import { ChoixPeriode } from "@/components/admin/periode";
import { Tableau } from "@/components/admin/tableau";
import { Tuile } from "@/components/admin/tuile";
import { atelier, ouRefus, RefusChamps, type Activite, type Couts } from "@/lib/admin/atelier";
import { gardePage } from "@/lib/admin/garde";
import { joursDe, sansCouts } from "@/lib/admin/suivi";
import { TA } from "@/lib/admin/textes";

// L'onglet Suivi d'un client : l'activité de la période (tours, échecs, secours, personnes, rappels, voix et vocaux), puis
// les tours et les jetons par modèle ; avec couts.voir, les coûts. Ils sont retirés sans ce droit avant tout affichage.

/** Ce que le journal du noyau a compté sur la période (un nombre de fois, ou une quantité). */
const note = (x: Activite, genre: string, champ: "nombre" | "quantite") => x.journal?.[genre]?.[champ] ?? 0;

/** Les coûts de la période : par poste, le total, la devise ; ce qui n'a pas de tarif est signalé, jamais compté à zéro. */
function BlocCouts({ couts }: { couts: Couts }) {
  const titre = <h2 className="m-0 text-[17px] font-extrabold">{TA.couts}</h2>;
  if ("erreur" in couts) {
    return (
      <>
        {titre}
        <Bandeau etat="warn">{couts.erreur}</Bandeau>
      </>
    );
  }
  const postes = Object.entries(couts.postes);
  const montant = (n: number, gras = false) => <span className={"whitespace-nowrap tabular-nums" + (gras ? " font-extrabold" : "")}>{TA.montant(n)}</span>;
  return (
    <>
      {titre}
      {couts.sans_tarif.length > 0 && <Bandeau etat="warn">{TA.sansTarif(couts.sans_tarif.map(TA.nomPoste).join(", "))}</Bandeau>}
      <Tableau
        colonnes={[TA.poste, TA.coutEn(couts.devise)]}
        vide={TA.aucunPoste}
        lignes={
          postes.length
            ? [
                ...postes.map(([poste, n]) => [<b key="poste" className="font-bold break-all">{TA.nomPoste(poste)}</b>, montant(n)]),
                [<b key="poste" className="font-extrabold">{TA.total}</b>, montant(couts.total, true)],
              ]
            : []
        }
      />
    </>
  );
}

export default async function PageSuivi({ params, searchParams }: PageProps<"/admin/clients/[id]">) {
  const { id } = await params;
  const a = await gardePage("clients.voir", id);
  const jours = joursDe((await searchParams).jours);
  const r = await ouRefus(atelier.suivi(id, jours));
  const periode = <ChoixPeriode jours={jours} chemin={`/admin/clients/${encodeURIComponent(id)}`} />;
  if (r instanceof RefusChamps) {
    // Un 404 du suivi pour un client que l'atelier connaît : jamais mis en service (la porte ne le connaît pas), pas une panne.
    if (r.statut === 404) {
      if ((await ouRefus(atelier.client(id))) instanceof RefusChamps) notFound();
      return <Bandeau etat="faint">{TA.jamaisSansActivite}</Bandeau>;
    }
    return <Bandeau>{r.message}</Bandeau>; // sans période : la changer n'y ferait rien
  }
  const { activite: x, couts } = sansCouts(r, a);
  const tuiles = [
    { titre: TA.tours, valeur: x.tours },
    { titre: TA.dontApi, valeur: x.tours_api ?? 0 },
    { titre: TA.echecs, valeur: x.tours_en_echec, etat: x.tours_en_echec > 0 ? ("warn" as const) : undefined },
    { titre: TA.secours, valeur: x.secours },
    { titre: TA.personnes, valeur: x.personnes },
    { titre: TA.rappelsEnAttente, valeur: x.rappels_en_attente ?? 0 },
    { titre: TA.voixCaracteres, valeur: note(x, "voix_caracteres", "quantite") },
    { titre: TA.vocauxEntendus, valeur: note(x, "vocal_entendu", "nombre") },
    { titre: TA.vocauxDits, valeur: note(x, "voix_caracteres", "nombre") }, // un par vocal dit (noyau/autour.py)
  ];
  return (
    <>
      {periode}
      <div className="grid grid-cols-[repeat(auto-fill,minmax(128px,1fr))] gap-3">
        {tuiles.map((t) => (
          <Tuile key={t.titre} titre={t.titre} valeur={TA.nombre(t.valeur)} etat={t.etat} />
        ))}
      </div>
      <h2 className="m-0 text-[17px] font-extrabold">{TA.parModele}</h2>
      <Tableau
        colonnes={[TA.modele, TA.tours, TA.entree, TA.sortie, TA.cacheLecture, TA.cacheEcriture]}
        vide={TA.aucunModele}
        replier={[2, 3, 4, 5]}
        lignes={Object.entries(x.modeles ?? {}).map(([modele, m]) => [
          <b key="modele" className="font-bold break-all">{modele}</b>,
          ...[m.tours, m.entree, m.sortie, m.cache_lecture, m.cache_ecriture].map((n, i) => (
            <span key={i} className="whitespace-nowrap tabular-nums">{TA.nombre(n ?? 0)}</span>
          )),
        ])}
      />
      {couts && <BlocCouts couts={couts} />}
    </>
  );
}

export const instant = false;
