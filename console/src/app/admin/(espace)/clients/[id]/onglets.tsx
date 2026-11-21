"use client";

import { usePathname, useSearchParams } from "next/navigation";
import { avecPeriode, Onglets } from "@/components/admin/onglets";

// Les onglets de la fiche d'un client (ongletsClient, côté serveur) : la mise en page ne se rejoue pas à la navigation,
// l'onglet actif et la période se lisent donc ici, dans l'adresse. L'actif : le plus long qui la commence. Suivi et
// Alertes gardent la période (?jours=).
export function OngletsClient({ onglets }: { onglets: { href: string; texte: string; periode: boolean }[] }) {
  const chemin = usePathname();
  const liens = avecPeriode(onglets, useSearchParams().get("jours"));
  const actif = onglets
    .map((o, i) => ({ href: o.href, i }))
    .filter((o) => chemin === o.href || chemin.startsWith(o.href + "/"))
    .sort((x, y) => y.href.length - x.href.length)[0];
  return <Onglets onglets={liens} actif={actif ? liens[actif.i].href : ""} />;
}
