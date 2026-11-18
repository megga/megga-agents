import { Bandeau } from "@/components/admin/erreurs";
import { Tableau } from "@/components/admin/tableau";
import { Tuile } from "@/components/admin/tuile";
import { peut } from "@/lib/admin/acces";
import { atelier, ouRefus, RefusChamps, type Tarifs } from "@/lib/admin/atelier";
import { gardePage } from "@/lib/admin/garde";
import { lireSuivis, modelesSansTarif } from "@/lib/admin/suivi";
import { TA } from "@/lib/admin/textes";
import { FormTarifs } from "./tarifs";

// Les tarifs (couts.voir pour lire, tarifs.regler pour les changer) : la devise ; par modèle, l'entrée, la sortie, le cache
// lu et écrit, par million de jetons ; la voix pour 1000 caractères ; l'écoute par vocal. Les modèles vus sans tarif dans
// l'activité des 30 derniers jours (les seuls suivis des clients du périmètre, sans leurs alertes) sont signalés, et proposés
// à l'ajout à qui peut régler.

const prix = (n: number | null) =>
  n === null ? <span className="text-faint">{TA.sansTarifCourt}</span> : <span className="whitespace-nowrap tabular-nums">{TA.montant(n)}</span>;

/** Les tarifs en lecture seule (couts.voir sans tarifs.regler). */
function LectureTarifs({ tarifs: t, sansTarif }: { tarifs: Tarifs; sansTarif: string[] }) {
  return (
    <>
      <div className="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] gap-3">
        <Tuile titre={TA.devise} valeur={t.devise} />
      </div>
      <div className="flex flex-col gap-1">
        <h2 className="m-0 text-[17px] font-extrabold">{TA.parModele}</h2>
        <p className="m-0 text-[13.5px] text-muted-ink">{TA.parMillion(t.devise)}</p>
      </div>
      {sansTarif.length > 0 && <Bandeau etat="warn">{TA.sansTarif(sansTarif.join(", "))}</Bandeau>}
      <Tableau
        colonnes={[TA.modele, TA.entree, TA.sortie, TA.cacheLecture, TA.cacheEcriture]}
        vide={TA.videTarifs}
        replier={[1, 2, 3, 4]}
        lignes={Object.entries(t.modeles).map(([modele, x]) => [
          <b key="modele" className="font-bold break-all">{modele}</b>,
          ...[x.entree, x.sortie, x.cache_lecture, x.cache_ecriture].map((n, i) => <span key={i}>{prix(n)}</span>),
        ])}
      />
      <h2 className="m-0 text-[17px] font-extrabold">{TA.voixEtEcoute}</h2>
      <Tableau
        colonnes={[TA.poste, TA.tarifEn(t.devise)]}
        vide={TA.videTarifs}
        lignes={[
          [<span key="poste">{TA.tarifVoix}</span>, prix(t.voix_par_1000_caracteres)],
          [<span key="poste">{TA.tarifEcoute}</span>, prix(t.par_vocal_entendu)],
        ]}
      />
    </>
  );
}

export default async function PageTarifs() {
  const a = await gardePage("couts.voir");
  const titre = <h1 className="m-0 text-[26px] font-extrabold tracking-[-0.02em]">{TA.tarifs}</h1>;
  const [t, lu] = await Promise.all([ouRefus(atelier.tarifs()), ouRefus(lireSuivis(a, 30, atelier))]);
  if (t instanceof RefusChamps) {
    return (
      <>
        {titre}
        <Bandeau>{t.message}</Bandeau>
      </>
    );
  }
  // L'activité illisible n'empêche pas de lire ni de changer les tarifs : rien n'est alors proposé.
  const sansTarif = lu instanceof RefusChamps ? [] : modelesSansTarif(lu.lectures).filter((m) => !Object.hasOwn(t.modeles, m));
  return (
    <>
      {titre}
      {peut(a, "tarifs.regler") ? <FormTarifs tarifs={t} proposes={sansTarif} /> : <LectureTarifs tarifs={t} sansTarif={sansTarif} />}
    </>
  );
}

export const instant = false;
