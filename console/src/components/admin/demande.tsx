"use client";

import { useCallback, useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { TA } from "@/lib/admin/textes";

type Demande = { question: string; bouton: string; faire: () => void };

/**
 * Chaque geste se confirme (règle de Julien du 19.11.2026). Pour un geste qui part d'un formulaire ou d'un menu, là où
 * Confirmation (un bouton qui ouvre sa fenêtre) ne s'emploie pas : demander(question, bouton, faire) ouvre une fenêtre avec
 * la question, Annuler et `bouton` ; faire ne part qu'après ce bouton. Le geste garde ses propres messages (envoi, erreurs).
 * avant(question, bouton, soumettre) : le onSubmit d'un formulaire qui demande d'abord.
 */
export function useDemande() {
  const [d, setD] = useState<Demande | null>(null);
  const demander = useCallback((question: string, bouton: string, faire: () => void) => setD({ question, bouton, faire }), []);
  const avant = useCallback(
    (question: string, bouton: string, soumettre: (e: React.FormEvent) => unknown) => (e: React.FormEvent) => {
      e.preventDefault();
      setD({ question, bouton, faire: () => void soumettre(e) });
    },
    [],
  );
  const fenetre = (
    <Dialog open={d !== null} onOpenChange={(o) => !o && setD(null)}>
      <DialogContent showCloseButton={false} className="gap-4 rounded-[22px] bg-bg p-5 shadow-doux sm:max-w-[420px]">
        <DialogTitle className="text-[17px] font-extrabold">{d?.question}</DialogTitle>
        <DialogDescription className="sr-only">{d?.question}</DialogDescription>
        <div className="flex justify-end gap-2">
          <button type="button" onClick={() => setD(null)} className="rounded-full px-4 py-2 text-[14px] font-semibold text-ink hover:bg-hover">
            {TA.annuler}
          </button>
          <button
            type="button"
            onClick={() => {
              const f = d?.faire;
              setD(null);
              f?.();
            }}
            className="rounded-full bg-marque px-4 py-2 text-[14px] font-bold text-on-marque"
          >
            {d?.bouton}
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
  return { demander, avant, fenetre };
}
