"use client";

import { Menu as MenuPrimitive } from "@base-ui/react/menu";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { authClient } from "@/lib/auth-client";
import { T } from "@/lib/textes";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Avatar } from "./avatar";
import { HautBas } from "./icones";

// Le menu du compte, en bas du rail : la photo ou l'initiale, le thème, un lien facultatif (l'admin depuis la console, la
// console depuis l'admin), Mon compte (dans l'admin seulement), le retour au site public (dans un nouvel onglet), se
// déconnecter. Il sert aux deux rails.

/** Le site public de MEGGA. */
export const SITE = "https://megga.ai";

const entree = "rounded-[10px] px-2.5 py-2 text-[14px]";

export function Compte({ entreprise, lien, image, monCompte }: {
  entreprise: string;
  lien?: { href: string; texte: string };
  image?: string | null;
  monCompte?: string;
}) {
  const router = useRouter();
  const [theme, setTheme] = useState<string | null>(() => {
    if (typeof window === "undefined") return null;
    try {
      return localStorage.getItem("theme");
    } catch {
      return null;
    }
  });
  function choisirTheme(t: "clair" | "sombre" | null) {
    try {
      if (t) localStorage.setItem("theme", t);
      else localStorage.removeItem("theme");
    } catch {}
    setTheme(t);
    (window as unknown as { __theme?: () => void }).__theme?.();
  }
  async function sortir() {
    await authClient.signOut();
    // Un rechargement complet : rien de la session (conversations gardées en mémoire) ne reste dans la page.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.assign("/connexion");
  }
  const choix: [string | null, string][] = [["clair", T.themeClair], ["sombre", T.themeSombre], [null, T.themeAppareil]];
  return (
    <div className="sticky bottom-0 mt-auto w-full bg-side px-2.5 pt-2 pb-3 before:pointer-events-none before:absolute before:inset-x-0 before:-top-[18px] before:h-[18px] before:bg-linear-to-b before:from-transparent before:to-side">
      <DropdownMenu>
        <DropdownMenuTrigger
          aria-label={T.compteEtReglages}
          className="flex w-full min-w-0 items-center gap-2.5 rounded-[14px] px-2.5 py-2 text-left text-ink hover:bg-hover aria-expanded:bg-hover"
        >
          <Avatar nom={entreprise} image={image} taille={36} />
          <b className="truncate text-[14.5px] font-bold max-[760px]:hidden">{entreprise}</b>
          <HautBas className="ml-auto size-4 flex-none text-muted-ink max-[760px]:hidden" />
        </DropdownMenuTrigger>
        <DropdownMenuContent side="top" sideOffset={8} className="min-w-[230px] rounded-2xl p-1.5 shadow-[0_16px_40px_rgba(27,27,47,.18)]">
          <div className="mb-1 flex items-center gap-2.5 px-2.5 pt-1.5 pb-2 [border-bottom:var(--fin)_solid_var(--trait)]">
            <Avatar nom={entreprise} image={image} taille={30} />
            <b className="truncate text-[14.5px]">{entreprise}</b>
          </div>
          <div className="px-2.5 pt-1 text-[11.5px] font-bold tracking-[.06em] text-faint uppercase">{T.theme}</div>
          <div className="flex gap-1 px-1.5 pt-1 pb-1.5" role="group" aria-label={T.theme}>
            {choix.map(([v, nom]) => (
              <button
                key={nom}
                type="button"
                aria-pressed={theme === v}
                onClick={() => choisirTheme(v as "clair" | "sombre" | null)}
                className="rounded-full px-2.5 py-1 text-[12.5px] font-semibold text-ink hover:bg-hover aria-pressed:bg-ink aria-pressed:text-bg"
              >
                {nom}
              </button>
            ))}
          </div>
          <DropdownMenuSeparator />
          {lien && (
            <DropdownMenuItem onClick={() => router.push(lien.href)} className={entree}>
              {lien.texte}
            </DropdownMenuItem>
          )}
          <MenuPrimitive.LinkItem
            href={SITE}
            target="_blank"
            rel="noopener noreferrer"
            className={"flex cursor-default items-center text-ink outline-hidden select-none focus:bg-hover " + entree}
          >
            {T.retourSite}
          </MenuPrimitive.LinkItem>
          {monCompte && (
            <DropdownMenuItem onClick={() => router.push(monCompte)} className={entree}>
              {T.monCompte}
            </DropdownMenuItem>
          )}
          <DropdownMenuItem onClick={sortir} className={entree}>
            {T.seDeconnecter}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
