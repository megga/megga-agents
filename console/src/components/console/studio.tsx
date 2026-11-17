"use client";

import { useEffect, useRef, useState } from "react";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { COULEURS, YEUX } from "@/lib/mascotte/couleurs";
import { METIERS } from "@/lib/metiers";
import { T } from "@/lib/textes";
import { Mallette, Oeil, Palette } from "./icones";
import { Tete } from "./tete";
import type { AgentVu } from "./types";

type Onglet = "couleur" | "yeux" | "metier";
const PRENOM_MAX = 20;

/** Le Studio de la maquette : prénom, couleur, yeux, métier. L'agent est en service dès « Créer ». */
export function Studio({ ouvert, onFermer, onCree, onErreur }: {
  ouvert: boolean;
  onFermer: () => void;
  onCree: (a: AgentVu) => void;
  onErreur: (message: string) => void;
}) {
  const [prenom, setPrenom] = useState("");
  const [couleur, setCouleur] = useState(0);
  const [yeux, setYeux] = useState(0);
  const [metier, setMetier] = useState<number | null>(null);
  const [onglet, setOnglet] = useState<Onglet>("couleur");
  const [envoi, setEnvoi] = useState(false);
  const [secoue, setSecoue] = useState<"prenom" | "metier" | null>(null);
  const champ = useRef<HTMLInputElement>(null);

  // Le Studio repart de zéro à chaque ouverture (la console change sa clé) ; le prénom prend la main à la souris.
  useEffect(() => {
    if (!ouvert || !window.matchMedia?.("(pointer: fine)").matches) return;
    const t = setTimeout(() => champ.current?.focus(), 250);
    return () => clearTimeout(t);
  }, [ouvert]);

  function refuser(quoi: "prenom" | "metier") {
    setSecoue(null);
    requestAnimationFrame(() => setSecoue(quoi));
    if (quoi === "prenom") champ.current?.focus();
    else setOnglet("metier");
  }

  async function creer() {
    if (!prenom.trim()) return refuser("prenom");
    if (metier === null) return refuser("metier");
    setEnvoi(true);
    try {
      const r = await fetch("/api/agents", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prenom, metier: METIERS[metier].id, couleur, yeux }),
      });
      const corps = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(corps.erreur || T.erreurGenerale);
      onCree(corps.agent);
    } catch (e) {
      onErreur(e instanceof Error ? e.message : T.erreurGenerale);
      setEnvoi(false);
    }
  }

  const teinte = COULEURS[couleur][1][0];

  return (
    <Dialog open={ouvert} onOpenChange={(o) => !o && onFermer()}>
      <DialogContent
        showCloseButton={false}
        aria-label={T.creerUnAgent}
        className="block h-[min(660px,calc(100dvh-48px))] w-[min(980px,calc(100%-48px))] max-w-none overflow-hidden rounded-[32px] bg-bg p-0 shadow-[0_30px_90px_rgba(15,16,20,.25)] sm:max-w-none max-[760px]:h-[calc(100dvh-32px)] max-[760px]:rounded-3xl"
      >
        <DialogTitle className="sr-only">{T.creerUnAgent}</DialogTitle>
        <div className="absolute inset-x-5 top-[18px] z-[5] flex items-center">
          <button type="button" onClick={onFermer} aria-label={T.fermer} className="grid size-10 place-items-center rounded-full bg-side text-[20px] leading-none text-muted-ink hover:text-ink">
            ×
          </button>
          <button type="button" onClick={creer} disabled={envoi} className="ml-auto rounded-full bg-marque px-[22px] py-2.5 text-[14.5px] font-bold text-on-marque disabled:opacity-60">
            {T.creer}
          </button>
        </div>

        <div className="absolute inset-0 flex flex-col items-center justify-center gap-0.5 pb-[150px] max-[760px]:pb-[170px]">
          <input
            ref={champ}
            value={prenom}
            maxLength={PRENOM_MAX}
            autoComplete="off"
            placeholder={T.sonPrenom}
            aria-label={T.prenomAgent}
            onChange={(e) => setPrenom(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && creer()}
            onAnimationEnd={() => setSecoue(null)}
            className={
              "w-[min(380px,80%)] rounded-[14px] border-0 bg-transparent px-2.5 py-0.5 text-center text-[34px] font-extrabold tracking-[-0.02em] text-ink outline-none placeholder:text-faint hover:bg-side focus:bg-side focus-visible:outline-none max-[760px]:text-[26px] " +
              (secoue === "prenom" ? "secoue" : "")
            }
          />
          {metier !== null && (
            <button type="button" onClick={() => setOnglet("metier")} className="mb-1.5 rounded-full px-3 py-1 text-[15px] font-semibold text-muted-ink hover:bg-side hover:text-ink">
              {METIERS[metier].nom} ›
            </button>
          )}
          <div className="flex flex-col items-center" role="img" aria-label={T.apercuAgent} style={{ ["--teinte" as string]: teinte }}>
            <Tete couleur={couleur} yeux={yeux} className="flotte w-[300px] max-[760px]:w-[180px]" />
            <div className="sol -mt-1.5 h-4 w-[46%] rounded-[50%] bg-[rgba(27,27,47,.12)] [[data-theme=douce]_&]:bg-black/45" />
          </div>
        </div>

        <div className="absolute bottom-[100px] left-1/2 z-[4] flex w-[min(820px,calc(100%-40px))] -translate-x-1/2 flex-wrap items-center justify-center gap-2.5 px-3.5 py-2 max-[760px]:bottom-[92px] max-[760px]:w-full max-[760px]:flex-nowrap max-[760px]:justify-start max-[760px]:overflow-x-auto">
          {onglet === "couleur" &&
            COULEURS.map(([nom, c], i) => (
              <Rond key={nom} titre={nom} fond={c[0]} actif={couleur === i} i={i} onClick={() => setCouleur(i)} />
            ))}
          {onglet === "yeux" &&
            YEUX.map(([nom, c], i) => (
              <Rond key={nom} titre={`${T.yeux} ${nom.toLowerCase()}`} fond={c[1]} actif={yeux === i} i={i} onClick={() => setYeux(i)} />
            ))}
          {onglet === "metier" &&
            METIERS.map((m, i) => (
              <button
                key={m.id}
                type="button"
                title={m.sous}
                aria-pressed={metier === i}
                onClick={() => setMetier(i)}
                style={{ animationDelay: `${i * 28}ms` }}
                className="monte flex-none rounded-full bg-side px-[15px] py-[9px] text-[14px] font-semibold whitespace-nowrap hover:bg-hover aria-pressed:bg-ink aria-pressed:text-bg"
              >
                {m.nom}
              </button>
            ))}
        </div>

        <nav aria-label={T.reglages} className="absolute bottom-6 left-1/2 z-[4] flex -translate-x-1/2 gap-1 rounded-[22px] bg-side p-1.5">
          <Dock nom={T.couleur} actif={onglet === "couleur"} onClick={() => setOnglet("couleur")} icone={<Palette className="size-[22px]" />} />
          <Dock nom={T.yeux} actif={onglet === "yeux"} onClick={() => setOnglet("yeux")} icone={<Oeil className="size-[22px]" />} />
          <Dock
            nom={T.metier}
            actif={onglet === "metier"}
            onClick={() => setOnglet("metier")}
            icone={<Mallette className="size-[22px]" />}
            secoue={secoue === "metier"}
            onFin={() => setSecoue(null)}
          />
        </nav>
      </DialogContent>
    </Dialog>
  );
}

function Rond({ titre, fond, actif, i, onClick }: { titre: string; fond: string; actif: boolean; i: number; onClick: () => void }) {
  return (
    <button
      type="button"
      title={titre}
      aria-label={titre}
      aria-pressed={actif}
      onClick={onClick}
      style={{ background: fond, animationDelay: `${i * 28}ms` }}
      className="monte size-11 flex-none rounded-full p-0 shadow-[inset_0_0_0_var(--fin)_rgba(0,0,0,.08)] transition-transform hover:scale-[1.08] aria-pressed:shadow-[0_0_0_3px_var(--bg),0_0_0_calc(3px+var(--fin))_var(--ink)]"
    />
  );
}

function Dock({ nom, actif, onClick, icone, secoue, onFin }: {
  nom: string;
  actif: boolean;
  onClick: () => void;
  icone: React.ReactNode;
  secoue?: boolean;
  onFin?: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={actif}
      onClick={onClick}
      onAnimationEnd={onFin}
      className={
        "flex min-w-[74px] flex-col items-center gap-[3px] rounded-2xl px-4 py-2 text-[12px] font-bold text-muted-ink aria-pressed:bg-bg aria-pressed:text-ink aria-pressed:shadow-[0_1px_4px_rgba(0,0,0,.08)] max-[760px]:min-w-0 max-[760px]:px-2.5 " +
        (secoue ? "secoue" : "")
      }
    >
      {icone}
      {nom}
    </button>
  );
}
