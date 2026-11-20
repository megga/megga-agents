"use client";

import { Bell, Coins, CreditCard, LayoutGrid, ScrollText, Server, ShieldCheck, Store, Users, type LucideIcon } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Compte } from "@/components/console/compte";
import { Tete } from "@/components/console/tete";
import { TA } from "@/lib/admin/textes";

// Le rail de l'admin, aux formes de celui de la console : la tête de la mascotte, les entrées que les droits du membre
// ouvrent (entreesRail, côté serveur), le menu du compte en bas. Sous 760 px, les icônes seules.

const ICONES: Record<string, LucideIcon> = {
  "/admin": LayoutGrid,
  "/admin/clients": Store,
  "/admin/alertes": Bell,
  "/admin/installations": Server,
  "/admin/comptes": Users,
  "/admin/payants": CreditCard,
  "/admin/tarifs": Coins,
  "/admin/equipe": ShieldCheck,
  "/admin/journal": ScrollText,
};

/** /admin n'est actif que sur la vue d'ensemble ; une autre entrée l'est aussi sur ses sous-pages. */
function actif(chemin: string, href: string): boolean {
  return href === "/admin" ? chemin === href : chemin === href || chemin.startsWith(href + "/");
}

/** consoleAgents : la console des agents est branchée (AGENTS_URL) ; sinon, pas de retour vers elle. image : la photo du membre. */
export function RailAdmin({ entrees, nom, image, consoleAgents }: {
  entrees: { href: string; texte: string }[];
  nom: string;
  image: string | null;
  consoleAgents: boolean;
}) {
  const chemin = usePathname();
  return (
    <nav aria-label={TA.railAdmin} className="trait-r relative flex w-[304px] flex-none flex-col gap-2 overflow-y-auto bg-side pt-4 [scrollbar-width:none] max-[760px]:w-[76px]">
      <div className="flex flex-none items-center gap-3 px-[22px] pb-1 max-[760px]:justify-center max-[760px]:px-0">
        <Tete couleur={0} yeux={0} className="w-[46px] flex-none" />
        <b className="truncate text-[16px] font-extrabold tracking-[-0.01em] max-[760px]:hidden">{TA.administration}</b>
      </div>
      <div className="flex w-full flex-none flex-col gap-0.5 px-2.5 max-[760px]:px-2">
        {entrees.map((e) => {
          const on = actif(chemin, e.href);
          const Icone = ICONES[e.href] ?? LayoutGrid;
          return (
            <Link
              key={e.href}
              href={e.href}
              title={e.texte}
              aria-current={on ? "page" : undefined}
              className={
                "flex w-full items-center gap-3 rounded-2xl px-3 py-2.5 text-[15px] max-[760px]:justify-center max-[760px]:px-0 " +
                (on ? "bg-bg font-extrabold text-ink shadow-doux" : "font-bold text-muted-ink hover:bg-hover hover:text-ink")
              }
            >
              <Icone aria-hidden className="size-5 flex-none" strokeWidth={1.9} />
              <span className="truncate max-[760px]:sr-only">{e.texte}</span>
            </Link>
          );
        })}
      </div>
      <Compte entreprise={nom} image={image} monCompte="/admin/compte" lien={consoleAgents ? { href: "/", texte: TA.retourConsole } : undefined} />
    </nav>
  );
}
