"use client";

import { usePathname } from "next/navigation";
import { Onglets } from "@/components/admin/onglets";

// Les onglets de la fiche d'un client (ongletsClient, côté serveur) : la mise en page ne se rejoue pas à la navigation,
// l'onglet actif se lit donc ici, dans l'adresse. Le plus long qui la commence (Conversations pour le fil d'une personne).
export function OngletsClient({ onglets }: { onglets: { href: string; texte: string }[] }) {
  const chemin = usePathname();
  const actif = onglets
    .map((o) => o.href)
    .filter((h) => chemin === h || chemin.startsWith(h + "/"))
    .sort((x, y) => y.length - x.length)[0];
  return <Onglets onglets={onglets} actif={actif ?? ""} />;
}
