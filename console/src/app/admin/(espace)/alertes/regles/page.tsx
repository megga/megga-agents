import { Bandeau } from "@/components/admin/erreurs";
import { OngletsAlertes } from "@/components/admin/alertes";
import { Tableau } from "@/components/admin/tableau";
import { notFound } from "next/navigation";
import { peutReglerAlertes, voitReglesAlertes } from "@/lib/admin/acces";
import { atelier, ouRefus, RefusChamps, type AlertesEnvoyees, type RegleAlerte } from "@/lib/admin/atelier";
import { gardePage } from "@/lib/admin/garde";
import { TA } from "@/lib/admin/textes";
import { FormRegles, GererDestinations } from "./regles";

// Les règles et les destinations des alertes envoyées (atelier, GET /alertes). Elles valent pour tous les clients : se lisent
// avec clients.voir sur un périmètre complet, se règlent avec alertes.regler sur un périmètre complet. L'adresse d'un webhook arrive déjà masquée.

const seuils = (r: RegleAlerte) => `${r.comparaison} ${r.alerte}` + (r.avertissement == null ? "" : `, ${TA.etatsAlerte.avertissement.toLowerCase()} ${r.avertissement}`);

function Lecture({ d }: { d: AlertesEnvoyees }) {
  return (
    <>
      <Tableau
        colonnes={[TA.regle, TA.mesure, TA.seuils, TA.fenetre, TA.rappel, TA.destinations]}
        vide={TA.videRegles}
        replier={[1, 2, 3, 4, 5]}
        lignes={d.regles.map((r) => [
          <span key="nom" className="flex flex-wrap items-center gap-2"><b className="font-bold">{r.nom}</b>{r.en_pause && <span className="text-faint">{TA.enPause}</span>}</span>,
          <span key="mesure">{d.mesures[r.mesure]?.libelle ?? r.mesure}</span>,
          <span key="seuils" className="whitespace-nowrap tabular-nums">{seuils(r)}</span>,
          <span key="fenetre">{TA.fenetreJours(r.fenetre_jours)}</span>,
          <span key="rappel">{TA.rappelHeures(r.rappel_heures)}</span>,
          <span key="destinations">{r.destinations.join(", ") || TA.inconnu}</span>,
        ])}
      />
      <h2 className="m-0 text-[17px] font-extrabold">{TA.destinations}</h2>
      <Tableau
        colonnes={[TA.identifiant, TA.genre, TA.adresse]}
        vide={TA.videDestinations}
        lignes={d.destinations.map((x) => [
          <b key="id" className="font-bold">{x.id}</b>,
          <span key="genre">{TA.genresDestination[x.genre] ?? x.genre}</span>,
          <span key="adresse" className="break-all">{x.adresse}</span>,
        ])}
      />
    </>
  );
}

export default async function PageReglesAlertes() {
  const a = await gardePage("clients.voir");
  if (!voitReglesAlertes(a)) notFound();
  const titre = <h1 className="m-0 text-[26px] font-extrabold tracking-[-0.02em]">{TA.alertes}</h1>;
  const d = await ouRefus(atelier.alertesEnvoyees());
  const onglets = <OngletsAlertes actif="/admin/alertes/regles" regles />;
  if (d instanceof RefusChamps) {
    return (
      <>
        {titre}
        {onglets}
        <Bandeau>{d.message}</Bandeau>
      </>
    );
  }
  return (
    <>
      {titre}
      {onglets}
      {d.proposees && <Bandeau etat="faint">{TA.reglesProposees}</Bandeau>}
      {peutReglerAlertes(a) ? (
        <>
          <FormRegles regles={d.regles} mesures={d.mesures} destinations={d.destinations} fenetreMax={d.fenetre_max} />
          <GererDestinations destinations={d.destinations} />
        </>
      ) : (
        <Lecture d={d} />
      )}
    </>
  );
}

export const instant = false;
