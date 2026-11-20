"use client";

import { useState } from "react";
import { authClient } from "@/lib/auth-client";
import { metier } from "@/lib/metiers";
import { T } from "@/lib/textes";
import { ContextMenu, ContextMenuContent, ContextMenuItem, ContextMenuTrigger } from "@/components/ui/context-menu";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Activite, Epingle, HautBas, Loupe, Plus } from "./icones";
import { Tete } from "./tete";
import type { AgentVu } from "./types";

type Props = {
  agents: AgentVu[];
  actif: string | null;
  vue: "activite" | null;
  onActivite: () => void;
  nouveau: string | null;
  apercus: Record<string, string>;
  entreprise: string;
  onChoisir: (id: string) => void;
  onNouvel: () => void;
  onChercher: () => void;
  onEpingler: (a: AgentVu) => void;
};

export function Rail(p: Props) {
  const epingles = p.agents.filter((a) => a.epingle);
  return (
    <nav aria-label="Vos agents" className="trait-r relative flex w-[304px] flex-none flex-col gap-2 overflow-y-auto bg-side pt-4 [scrollbar-width:none] max-[760px]:w-[76px]">
      <div className="flex flex-none justify-between px-3.5 pb-1 max-[760px]:flex-col max-[760px]:items-center max-[760px]:gap-2 max-[760px]:px-0">
        <button type="button" onClick={p.onChercher} aria-label={T.chercherAgent} title={`${T.chercherAgent} (⌘ K)`} className="trait grid size-11 place-items-center rounded-[14px] bg-bg text-ink hover:border-trait-fort">
          <Loupe className="size-5" />
        </button>
        <button type="button" onClick={p.onNouvel} aria-label={T.nouvelAgent} title={T.nouvelAgent} className="trait grid size-11 place-items-center rounded-[14px] bg-bg text-ink hover:border-trait-fort">
          <Plus className="size-5" />
        </button>
      </div>

      {p.agents.length > 0 && (
        <>
          <div className="flex flex-none flex-col gap-px self-stretch px-2.5 pb-1 max-[760px]:items-center max-[760px]:px-0">
            <button
              type="button"
              onClick={p.onActivite}
              aria-current={p.vue === "activite" ? "page" : undefined}
              title={T.activite}
              className={
                "flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-left text-[14.5px] font-semibold text-ink max-[760px]:size-11 max-[760px]:justify-center max-[760px]:p-0 " +
                (p.vue === "activite" ? "bg-bg shadow-doux" : "hover:bg-hover")
              }
            >
              <Activite className="size-[19px] flex-none text-muted-ink" />
              <span className="max-[760px]:hidden">{T.activite}</span>
            </button>
          </div>
          <TitreRail>{T.epingles}</TitreRail>
          {epingles.length ? (
            <div className="grid grid-cols-3 gap-2 px-3 pt-0.5 pb-1 max-[760px]:hidden">
              {epingles.map((a) => (
                <MenuAgent key={a.id} agent={a} onEpingler={p.onEpingler}>
                <button
                  type="button"
                  onClick={() => p.onChoisir(a.id)}
                  aria-current={p.actif === a.id || undefined}
                  className={
                    "flex flex-col items-center gap-[3px] rounded-[18px] px-1 pt-2.5 pb-2 " +
                    (p.actif === a.id ? "bg-bg shadow-doux" : "trait hover:bg-hover")
                  }
                >
                  <Tete couleur={a.couleur} yeux={a.yeux} className="w-14" />
                  <b className="max-w-full truncate text-[13px]">{a.prenom}</b>
                </button>
                </MenuAgent>
              ))}
            </div>
          ) : (
            <p className="max-[760px]:hidden px-3 pt-0.5 pb-1.5 text-center text-[13px] text-faint">{T.videEpingles}</p>
          )}

          <TitreRail>{T.conversations}</TitreRail>
          <div className="flex w-full flex-none flex-col">
            {/* Un agent épinglé quitte la liste (jamais deux fois la même information), sauf sur téléphone,
                où les tuiles des épinglés ne s'affichent pas : il y reste, sinon on ne le trouverait plus. */}
            {p.agents.map((a) => (
              <LigneAgent key={a.id} agent={a} {...p} />
            ))}
          </div>
        </>
      )}

      <Compte entreprise={p.entreprise} />
    </nav>
  );
}

function TitreRail({ children }: { children: React.ReactNode }) {
  return <div className="max-[760px]:hidden flex-none self-stretch px-[22px] pt-2 text-[11.5px] font-bold tracking-[.06em] text-faint uppercase">{children}</div>;
}

function LigneAgent({ agent: a, actif, nouveau, apercus, onChoisir, onEpingler }: Props & { agent: AgentVu }) {
  const on = actif === a.id;
  const m = metier(a.metier);
  const apercu = apercus[a.id] ?? T.apercuAccueil(a.prenom, m?.qui ?? "");
  return (
    <MenuAgent agent={a} onEpingler={onEpingler}>
    <div className={"group relative w-full px-2.5 max-[760px]:px-0" + (a.epingle ? " min-[761px]:hidden" : "")}>
      <button
        type="button"
        onClick={() => onChoisir(a.id)}
        title={a.prenom}
        aria-current={on || undefined}
        className={
          "flex w-full items-center gap-3 rounded-2xl px-2.5 py-2 text-left max-[760px]:justify-center max-[760px]:px-1 " +
          (on ? "bg-bg shadow-doux" : "hover:bg-hover") +
          (nouveau === a.id ? " nouveau" : "")
        }
      >
        <Tete couleur={a.couleur} yeux={a.yeux} className="w-[50px] flex-none" />
        <span className="flex min-w-0 flex-1 flex-col gap-px max-[760px]:hidden">
          <b className={"text-[15px] " + (on ? "font-extrabold" : "font-bold")}>{a.prenom}</b>
          <span className="truncate text-[13px] text-muted-ink">{apercu}</span>
        </span>
      </button>
      <button
        type="button"
        onClick={() => onEpingler(a)}
        aria-label={a.epingle ? T.desepingler : T.epinglerEnHaut}
        title={a.epingle ? T.desepingler : T.epinglerEnHaut}
        className={
          "max-[760px]:hidden absolute top-1/2 right-5 grid size-[30px] -translate-y-1/2 place-items-center rounded-[9px] bg-bg opacity-0 shadow-doux transition-opacity group-hover:opacity-100 focus-visible:opacity-100 " +
          (a.epingle ? "text-marque" : "text-muted-ink hover:text-ink")
        }
      >
        <Epingle className="size-4" />
      </button>
    </div>
    </MenuAgent>
  );
}

function MenuAgent({ agent: a, onEpingler, children }: { agent: AgentVu; onEpingler: (a: AgentVu) => void; children: React.ReactElement }) {
  return (
    <ContextMenu>
      <ContextMenuTrigger render={children} />
      <ContextMenuContent className="min-w-[230px] rounded-2xl p-1.5 shadow-[0_16px_40px_rgba(27,27,47,.18)]">
        <div className="mb-1 flex items-center gap-2.5 px-2.5 pt-1.5 pb-2 [border-bottom:var(--fin)_solid_var(--trait)]">
          <Tete couleur={a.couleur} yeux={a.yeux} className="w-[30px]" />
          <b className="text-[14.5px]">{a.prenom}</b>
        </div>
        <ContextMenuItem onClick={() => onEpingler(a)} className="rounded-[10px] px-2.5 py-2 text-[14px]">
          {a.epingle ? T.desepingler : T.epinglerEnHaut}
        </ContextMenuItem>
      </ContextMenuContent>
    </ContextMenu>
  );
}

function initiale(nom: string): string {
  return ([...nom.trim()][0] ?? "M").toUpperCase();
}

function Compte({ entreprise }: { entreprise: string }) {
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
          <span className="grid size-9 flex-none place-items-center rounded-[11px] bg-ink text-[14px] font-extrabold text-bg">{initiale(entreprise)}</span>
          <b className="truncate text-[14.5px] font-bold max-[760px]:hidden">{entreprise}</b>
          <HautBas className="ml-auto size-4 flex-none text-muted-ink max-[760px]:hidden" />
        </DropdownMenuTrigger>
        <DropdownMenuContent side="top" sideOffset={8} className="min-w-[230px] rounded-2xl p-1.5 shadow-[0_16px_40px_rgba(27,27,47,.18)]">
          <div className="mb-1 flex items-center gap-2.5 px-2.5 pt-1.5 pb-2 [border-bottom:var(--fin)_solid_var(--trait)]">
            <span className="grid size-[30px] flex-none place-items-center rounded-[9px] bg-ink text-[12.5px] font-extrabold text-bg">{initiale(entreprise)}</span>
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
          <DropdownMenuItem onClick={sortir} className="rounded-[10px] px-2.5 py-2 text-[14px]">
            {T.seDeconnecter}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
