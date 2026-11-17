"use client";

import { useMemo, useState } from "react";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { metier } from "@/lib/metiers";
import { T } from "@/lib/textes";
import { Tete } from "./tete";
import type { AgentVu } from "./types";

function sansAccents(s: string) {
  return s.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();
}

/** Chercher un agent (⌘ K), comme la maquette. Repart de zéro à chaque ouverture (la console change sa clé). */
export function Palette({ ouvert, agents, onFermer, onChoisir }: {
  ouvert: boolean;
  agents: AgentVu[];
  onFermer: () => void;
  onChoisir: (id: string) => void;
}) {
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(0);
  const res = useMemo(() => {
    const k = sansAccents(q.trim());
    return agents.filter((a) => !k || sansAccents(a.prenom + " " + (metier(a.metier)?.nom ?? "")).includes(k));
  }, [q, agents]);

  function aller(id: string) {
    onFermer();
    onChoisir(id);
  }

  return (
    <Dialog open={ouvert} onOpenChange={(o) => !o && onFermer()}>
      <DialogContent
        showCloseButton={false}
        className="top-[12vh] block w-[min(560px,calc(100%-32px))] max-w-none translate-y-0 gap-0 overflow-hidden rounded-[20px] bg-bg p-0 shadow-[0_20px_60px_rgba(0,0,0,.25)] sm:max-w-none"
      >
        <DialogTitle className="sr-only">{T.chercherAgent}</DialogTitle>
        <input
          autoFocus
          value={q}
          placeholder={T.chercherPlaceholder}
          aria-label={T.chercherAgent}
          onChange={(e) => {
            setQ(e.target.value);
            setSel(0);
          }}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") setSel((s) => Math.min(s + 1, res.length - 1));
            else if (e.key === "ArrowUp") setSel((s) => Math.max(s - 1, 0));
            else if (e.key === "Enter" && res[sel]) aller(res[sel].id);
            else return;
            e.preventDefault();
          }}
          className="w-full border-0 bg-transparent px-5 py-4 text-[17px] text-ink outline-none [border-bottom:var(--fin)_solid_var(--trait)] placeholder:text-faint focus-visible:outline-none"
        />
        <div className="max-h-[50vh] overflow-auto p-2">
          {res.length === 0 && <p className="m-0 px-3 py-2.5 text-muted-ink">{T.aucunResultat}</p>}
          {res.map((a, i) => (
            <button
              key={a.id}
              type="button"
              onMouseEnter={() => setSel(i)}
              onClick={() => aller(a.id)}
              className={"flex w-full items-center gap-3 rounded-xl px-2.5 py-2 text-left " + (i === sel ? "bg-hover" : "")}
            >
              <span className="flex size-10 flex-none items-center justify-center overflow-hidden rounded-xl bg-side">
                <Tete couleur={a.couleur} yeux={a.yeux} className="w-[34px]" />
              </span>
              <b>{a.prenom}</b>
              <span className="ml-auto text-[13px] text-muted-ink">{metier(a.metier)?.nom}</span>
            </button>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}
