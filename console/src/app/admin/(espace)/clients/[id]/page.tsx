import { notFound } from "next/navigation";
import { Bandeau } from "@/components/admin/erreurs";
import { ChoixPeriode } from "@/components/admin/periode";
import { Tableau } from "@/components/admin/tableau";
import { Tuile } from "@/components/admin/tuile";
import { atelier, ouRefus, RefusChamps, type Activite } from "@/lib/admin/atelier";
import { gardePage } from "@/lib/admin/garde";
import { joursDe, sansCouts } from "@/lib/admin/suivi";
import { TA } from "@/lib/admin/textes";

// L'onglet Suivi d'un client : l'activité de la période (tours, échecs, secours, personnes, rappels, voix et vocaux), puis
// les tours et les jetons par modèle. Les coûts sont retirés sans couts.voir avant tout affichage.

/** Ce que le journal du noyau a compté sur la période (un nombre de fois, ou une quantité). */
const note = (x: Activite, genre: string, champ: "nombre" | "quantite") => x.journal?.[genre]?.[champ] ?? 0;

export default async function PageSuivi({ params, searchParams }: PageProps<"/admin/clients/[id]">) {
  const { id } = await params;
  const a = await gardePage("clients.voir", id);
  const jours = joursDe((await searchParams).jours);
  const r = await ouRefus(atelier.suivi(id, jours));
  const periode = <ChoixPeriode jours={jours} chemin={`/admin/clients/${encodeURIComponent(id)}`} />;
  if (r instanceof RefusChamps) {
    if (r.statut === 404) notFound();
    return (
      <>
        {periode}
        <Bandeau>{r.message}</Bandeau>
      </>
    );
  }
  const x = sansCouts(r, a).activite;
  const tuiles = [
    { titre: TA.tours, valeur: x.tours },
    { titre: TA.dontApi, valeur: x.tours_api ?? 0 },
    { titre: TA.echecs, valeur: x.tours_en_echec, etat: x.tours_en_echec > 0 ? ("warn" as const) : undefined },
    { titre: TA.secours, valeur: x.secours },
    { titre: TA.personnes, valeur: x.personnes },
    { titre: TA.rappelsEnAttente, valeur: x.rappels_en_attente ?? 0 },
    { titre: TA.voixCaracteres, valeur: note(x, "voix_caracteres", "quantite") },
    { titre: TA.vocauxEntendus, valeur: note(x, "vocal_entendu", "nombre") },
    { titre: TA.vocauxDits, valeur: note(x, "vocal_dit", "nombre") },
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
    </>
  );
}

export const instant = false;
