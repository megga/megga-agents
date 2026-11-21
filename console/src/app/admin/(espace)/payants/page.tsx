import Link from "next/link";
import { Bandeau } from "@/components/admin/erreurs";
import { Onglets } from "@/components/admin/onglets";
import { Pastille, type Etat } from "@/components/admin/pastille";
import { Tableau } from "@/components/admin/tableau";
import { Tuile } from "@/components/admin/tuile";
import { atelier, ouRefus, RefusChamps, type StatutAbonnement } from "@/lib/admin/atelier";
import { gardePage } from "@/lib/admin/garde";
import { bornerPayants, ONGLETS_PAYANTS, partConsommee } from "@/lib/admin/payants";
import { TA } from "@/lib/admin/textes";

// Les clients payants (couts.voir) : leur mois en cours, d'après l'atelier (GET /abonnements). L'unité vendue est la
// conversation, une personne servie sur une journée. Le revenu est dans la devise des forfaits, le coût dans celle des
// tarifs ; la marge n'est donnée que si ce sont les mêmes. Bornés au périmètre du membre, les plus près de l'enveloppe vide
// d'abord.

const COULEUR: Record<StatutAbonnement, Etat> = { actif: "ok", essai: "faint", retard: "accent", parti: "faint" };

export default async function PagePayants() {
  const a = await gardePage("couts.voir");
  const titre = <h1 className="m-0 text-[26px] font-extrabold tracking-[-0.02em]">{TA.clientsPayants}</h1>;
  const [lu, liste] = await Promise.all([ouRefus(atelier.payants()), ouRefus(atelier.clients())]);
  if (lu instanceof RefusChamps) {
    return (
      <>
        {titre}
        <Bandeau>{lu.message}</Bandeau>
      </>
    );
  }
  const v = bornerPayants(a, lu);
  const t = v.totaux;
  const forfaits = new Map(v.catalogue.forfaits.map((f) => [f.id, f]));
  // Le nom de l'atelier : un client hors relevé (installé chez lui) n'en a pas dans le relevé.
  const noms = new Map(liste instanceof RefusChamps ? [] : liste.clients.map((c) => [c.id, c.entreprise]));
  const coutDevise = v.devise_couts ?? v.devise;
  return (
    <>
      {titre}
      <Onglets onglets={ONGLETS_PAYANTS} actif="/admin/payants" />
      {!v.releve_lisible && <Bandeau etat="warn">{TA.releveIllisiblePayants}</Bandeau>}
      {v.releve_lisible && t.marge === null && v.devise_couts && <Bandeau etat="warn">{TA.devisesDifferentes(v.devise, v.devise_couts)}</Bandeau>}
      <div className="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] gap-3">
        <Tuile titre={TA.statutsAbonnement.actif} valeur={TA.nombre(t.actif)} />
        <Tuile titre={TA.statutsAbonnement.essai} valeur={TA.nombre(t.essai)} />
        <Tuile titre={TA.statutsAbonnement.retard} valeur={TA.nombre(t.retard)} etat={t.retard > 0 ? "accent" : undefined} />
        <Tuile titre={TA.revenuDuMois} valeur={TA.montantEn(t.revenu, v.devise)} />
        {t.marge !== null && <Tuile titre={TA.margeDuMois} valeur={TA.montantEn(t.marge, v.devise)} etat={t.marge < 0 ? "accent" : undefined} />}
        <Tuile titre={TA.prochesEnveloppe} valeur={TA.nombre(t.proches)} etat={t.proches > 0 ? "warn" : undefined} />
      </div>
      <Tableau
        colonnes={[TA.client, TA.forfait, TA.statut, TA.conversations, TA.revenu, TA.coutEn(coutDevise), TA.marge, TA.multiple]}
        vide={TA.videPayants}
        replier={[1, 4, 5, 6, 7]}
        lignes={v.clients.map((l) => {
          const f = forfaits.get(l.abonnement.forfait);
          const part = partConsommee(l);
          const multiple = l.cout > 0 && l.marge !== null ? Math.round((l.revenu / l.cout) * 10) / 10 : null;
          return [
            <Link key="client" href={`/admin/clients/${encodeURIComponent(l.client)}`} className="font-bold text-ink hover:underline">
              {l.entreprise || noms.get(l.client) || l.client}
            </Link>,
            <span key="forfait" className="whitespace-nowrap">
              {f ? `${f.nom}, ${TA.rythmes[l.abonnement.rythme].toLowerCase()}` : <span className="text-warn">{TA.forfaitRetire}</span>}
            </span>,
            <span key="statut" className="flex flex-wrap gap-1">
              <Pastille etat={COULEUR[l.abonnement.statut]} texte={TA.statutsAbonnement[l.abonnement.statut]} />
              {l.stripe && !l.stripe.relie && l.abonnement.statut !== "parti" && <Pastille etat="faint" texte={TA.sansStripe} />}
              {l.stripe?.recharge_en_cours && <Pastille etat="warn" texte={TA.rechargeEnCours} />}
            </span>,
            <span key="conversations" className="flex flex-wrap items-center gap-2 tabular-nums">
              <span className="whitespace-nowrap">{TA.conversationsSur(l.consommees, l.enveloppe)}{part !== null && ` (${part} %)`}</span>
              {l.proche && <Pastille etat="warn" texte={TA.bientotVide} />}
            </span>,
            <span key="revenu" className="whitespace-nowrap tabular-nums">{TA.montant(l.revenu)}</span>,
            <span key="cout" className="whitespace-nowrap tabular-nums">{TA.montant(l.cout)}</span>,
            <span key="marge" className={"whitespace-nowrap tabular-nums " + (l.marge !== null && l.marge < 0 ? "font-semibold text-marque" : "")}>
              {l.marge === null ? TA.inconnu : TA.montant(l.marge)}
            </span>,
            <span key="multiple" className={"whitespace-nowrap tabular-nums " + (multiple !== null && multiple < v.catalogue.multiplicateur ? "font-semibold text-warn" : "")}>
              {multiple === null ? TA.inconnu : TA.multipleDe(multiple)}
            </span>,
          ];
        })}
      />
    </>
  );
}

export const instant = false;
