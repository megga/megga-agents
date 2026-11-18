"use client";

import Link from "next/link";
import { useState } from "react";
import { champ } from "@/components/admin/formulaire";
import { Pastille, type Etat } from "@/components/admin/pastille";
import { Tableau } from "@/components/admin/tableau";
import { Input } from "@/components/ui/input";
import type { EtatClient } from "@/lib/admin/suivi";
import { TA } from "@/lib/admin/textes";

// La liste des clients du moteur, déjà bornée au périmètre côté serveur : la recherche se fait ici, dans le navigateur
// (entreprise, agent, identifiant). Dans un cadre étroit, les colonnes se replient sous l'entreprise.

export type LigneClient = {
  id: string;
  entreprise: string | null;
  agent: string | null;
  version: string;
  etat: EtatClient;
  installation: { etat: Etat; texte: string };
};

/** L'état d'un client en pastilles : le service, l'écart, la main de MEGGA, le conteneur s'il est connu. */
export function PastillesEtat({ etat }: { etat: EtatClient }) {
  return (
    <span className="flex flex-wrap gap-1">
      {etat.service === "en_service" ? <Pastille etat="ok" texte={TA.enService} /> : <Pastille etat="faint" texte={TA.jamaisEnService} />}
      {etat.ecart && <Pastille etat="warn" texte={TA.ecart} />}
      {etat.tenuParMegga && <Pastille etat="faint" texte={TA.tenuParMegga} />}
      {etat.conteneur === "demarre" && <Pastille etat="ok" texte={TA.conteneurDemarre} />}
      {etat.conteneur === "arrete" && <Pastille etat="accent" texte={TA.conteneurArrete} />}
    </span>
  );
}

const trouve = (l: LigneClient, q: string) => [l.entreprise, l.agent, l.id].some((v) => v?.toLocaleLowerCase("fr").includes(q));

export function Clients({ lignes }: { lignes: LigneClient[] }) {
  const [recherche, setRecherche] = useState("");
  const q = recherche.trim().toLocaleLowerCase("fr");
  const vues = q ? lignes.filter((l) => trouve(l, q)) : lignes;
  return (
    <>
      <Input
        type="search"
        aria-label={TA.rechercherClient}
        placeholder={TA.rechercherClient}
        value={recherche}
        onChange={(e) => setRecherche(e.target.value)}
        className={champ + " max-w-[360px]"}
      />
      <Tableau
        colonnes={[TA.entreprise, TA.agent, TA.identifiant, TA.version, TA.etat, TA.installation]}
        vide={lignes.length ? TA.aucunClientTrouve : TA.videClients}
        replier={[1, 2, 3, 4, 5]}
        lignes={vues.map((l) => [
          <Link key="entreprise" href={`/admin/clients/${encodeURIComponent(l.id)}`} className="font-bold text-ink hover:underline">
            {l.entreprise || l.id}
          </Link>,
          <span key="agent">{l.agent ?? ""}</span>,
          <span key="id" className="whitespace-nowrap text-muted-ink">{l.id}</span>,
          <span key="version" className="whitespace-nowrap">{l.version}</span>,
          <PastillesEtat key="etat" etat={l.etat} />,
          <Pastille key="installation" etat={l.installation.etat} texte={l.installation.texte} />,
        ])}
      />
    </>
  );
}
