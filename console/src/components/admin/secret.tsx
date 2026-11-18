"use client";

import { useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { TA } from "@/lib/admin/textes";

/**
 * Un secret montré une fois (un lien d'invitation, un jeton, une clé). Le parent tient la valeur et la remet à null dans
 * onFermer : fermée, la fenêtre l'oublie, et rien ne la remontre. Elle ne se ferme que par « Fermer » : ni un clic au-dehors
 * ni Échap ne font perdre un secret qu'on ne reverra plus.
 */
export function SecretUnique({ valeur, onFermer }: { valeur: string | null; onFermer: () => void }) {
  const [copie, setCopie] = useState(false);

  async function copier() {
    if (!valeur) return;
    try {
      await navigator.clipboard.writeText(valeur);
      setCopie(true);
    } catch {
      // Sans presse-papiers (adresse non sécurisée), le secret reste à sélectionner à la main.
    }
  }

  return (
    <Dialog open={valeur !== null} disablePointerDismissal onOpenChange={() => {}}>
      <DialogContent showCloseButton={false} className="gap-3 rounded-[22px] bg-bg p-5 shadow-doux sm:max-w-[480px]">
        <DialogTitle className="text-[17px] font-extrabold">{TA.secretTitre}</DialogTitle>
        <DialogDescription className="text-[14px] text-muted-ink">{TA.secretUneFois}</DialogDescription>
        <p className="trait m-0 rounded-xl bg-side px-3.5 py-2.5 text-[13.5px] font-semibold break-all text-ink select-all">{valeur}</p>
        <div className="mt-1 flex justify-end gap-2">
          <button type="button" onClick={copier} className="trait rounded-full bg-bg px-4 py-2 text-[14px] font-semibold text-ink hover:bg-hover">
            {copie ? TA.copie : TA.copier}
          </button>
          <button
            type="button"
            onClick={() => {
              setCopie(false);
              onFermer();
            }}
            className="rounded-full bg-ink px-4 py-2 text-[14px] font-bold text-bg"
          >
            {TA.fermer}
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
