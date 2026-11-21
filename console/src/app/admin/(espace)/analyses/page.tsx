import Link from "next/link";
import { Barres } from "@/components/admin/barres";
import { Bandeau } from "@/components/admin/erreurs";
import { ChoixPeriode } from "@/components/admin/periode";
import { Tableau } from "@/components/admin/tableau";
import { Tuile } from "@/components/admin/tuile";
import { analyser } from "@/lib/admin/analyses";
import { atelier, ouRefus, RefusChamps } from "@/lib/admin/atelier";
import { gardePage } from "@/lib/admin/garde";
import { joursDe } from "@/lib/admin/suivi";
import { TA } from "@/lib/admin/textes";

// Les analyses (clients.voir), d'après le relevé chiffré, pour la période choisie : conversations, tours, vocaux et coût jour
// par jour ; les jetons et le coût par modèle ; la voix et l'écoute ; puis chaque client et le coût d'une conversation. Bornées
// au périmètre du membre ; les coûts seulement avec couts.voir. Jamais une conversation lue.

const nombre = (n: number) => <span className="whitespace-nowrap tabular-nums">{TA.nombre(n)}</span>;
const montant = (n: number | null | undefined) =>
  <span className="whitespace-nowrap tabular-nums">{n == null ? TA.inconnu : TA.montant(n)}</span>;

export default async function PageAnalyses({ searchParams }: PageProps<"/admin/analyses">) {
  const a = await gardePage("clients.voir");
  const jours = joursDe((await searchParams).jours);
  const titre = <h1 className="m-0 text-[26px] font-extrabold tracking-[-0.02em]">{TA.analyses}</h1>;
  const periode = <ChoixPeriode jours={jours} chemin="/admin/analyses" />;
  const r = await ouRefus(atelier.releves(jours));
  if (r instanceof RefusChamps) {
    return (
      <>
        {titre}
        <Bandeau>{r.message}</Bandeau>
      </>
    );
  }
  const v = analyser(r, a);
  const cout = v.tuiles.cout;
  return (
    <>
      {titre}
      {periode}
      <div className="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] gap-3">
        <Tuile titre={TA.conversations} valeur={TA.nombre(v.tuiles.conversations)} />
        <Tuile titre={TA.tours} valeur={TA.nombre(v.tuiles.tours)} />
        <Tuile titre={TA.dontApi} valeur={TA.nombre(v.tuiles.toursApi)} />
        <Tuile titre={TA.vocauxEntendus} valeur={TA.nombre(v.tuiles.vocauxEntendus)} />
        <Tuile titre={TA.vocauxDits} valeur={TA.nombre(v.tuiles.vocauxDits)} />
        {cout && <Tuile titre={TA.cout} valeur={TA.montantEn(cout.total, cout.devise)} />}
        {cout && cout.parConversation !== null && <Tuile titre={TA.coutParConversation} valeur={TA.montantEn(cout.parConversation, cout.devise)} />}
      </div>
      <Barres
        jours={v.parJour.map((j) => ({ jour: j.jour, valeurs: cout ? [j.conversations, j.tours, j.vocaux, j.cout] : [j.conversations, j.tours, j.vocaux] }))}
        legendes={[TA.conversationsParJour, TA.toursParJour, TA.vocauxParJour, ...(cout ? [TA.coutParJour(cout.devise)] : [])]}
      />
      <h2 className="m-0 text-[17px] font-extrabold">{TA.parModele}</h2>
      <Tableau
        colonnes={[TA.modele, TA.tours, TA.entree, TA.sortie, TA.cacheLecture, ...(cout ? [TA.coutEn(cout.devise)] : [])]}
        vide={TA.videModeles}
        replier={cout ? [2, 3, 4, 5] : [2, 3, 4]}
        lignes={v.modeles.map((m) => [
          <b key="modele" className="font-bold break-all">{m.modele}</b>,
          nombre(m.tours), nombre(m.entree), nombre(m.sortie), nombre(m.cacheLecture),
          ...(cout ? [montant(m.cout)] : []),
        ])}
      />
      {cout && v.autresPostes.length > 0 && (
        <>
          <h2 className="m-0 text-[17px] font-extrabold">{TA.voixEtEcoute}</h2>
          <Tableau
            colonnes={[TA.poste, TA.coutEn(cout.devise)]}
            vide={TA.aucunPoste}
            lignes={v.autresPostes.map((p) => [<span key="poste">{TA.nomPoste(p.poste)}</span>, montant(p.cout)])}
          />
        </>
      )}
      <h2 className="m-0 text-[17px] font-extrabold">{TA.parClient}</h2>
      <Tableau
        colonnes={[TA.client, TA.conversations, TA.tours, ...(cout ? [TA.coutEn(cout.devise), TA.coutParConversationEn(cout.devise)] : [])]}
        vide={TA.videParClient}
        replier={cout ? [2, 3, 4] : [2]}
        lignes={v.clients.map((c) => [
          <Link key="client" href={`/admin/clients/${encodeURIComponent(c.client)}?jours=${jours}`} className="font-bold text-ink hover:underline">
            {c.entreprise || c.client}
          </Link>,
          nombre(c.conversations), nombre(c.tours),
          ...(cout ? [montant(c.cout), montant(c.coutParConversation)] : []),
        ])}
      />
    </>
  );
}

export const instant = false;
