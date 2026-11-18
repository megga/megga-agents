"use client";

import { useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { TA } from "@/lib/admin/textes";

/**
 * Un geste qui demande confirmation : children est le libellé du bouton qui ouvre la fenêtre ; elle dit l'effet du geste
 * (obligatoire), puis Annuler ou `bouton`. Si onConfirmer échoue, sa phrase s'affiche et la fenêtre reste ouverte.
 */
export function Confirmation({ titre, effet, bouton, onConfirmer, children }: {
  titre: string;
  effet: string;
  bouton: string;
  onConfirmer: () => Promise<void>;
  children: React.ReactNode;
}) {
  const [ouvert, setOuvert] = useState(false);
  const [envoi, setEnvoi] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);

  async function confirmer() {
    setEnvoi(true);
    setErreur(null);
    try {
      await onConfirmer();
      setOuvert(false);
    } catch (e) {
      setErreur(e instanceof Error && e.message ? e.message : TA.erreurInterne);
    } finally {
      setEnvoi(false);
    }
  }

  return (
    <Dialog
      open={ouvert}
      onOpenChange={(o) => {
        setOuvert(o);
        if (o) setErreur(null);
      }}
    >
      <DialogTrigger className="trait rounded-full bg-bg px-3 py-1 text-[13px] font-semibold whitespace-nowrap text-ink hover:bg-hover">{children}</DialogTrigger>
      <DialogContent showCloseButton={false} className="gap-3 rounded-[22px] bg-bg p-5 shadow-doux sm:max-w-[420px]">
        <DialogTitle className="text-[17px] font-extrabold">{titre}</DialogTitle>
        <DialogDescription className="text-[14px] text-muted-ink">{effet}</DialogDescription>
        {erreur && (
          <p role="alert" className="m-0 text-[13.5px] font-semibold text-marque">
            {erreur}
          </p>
        )}
        <div className="mt-1 flex justify-end gap-2">
          <button type="button" onClick={() => setOuvert(false)} className="rounded-full px-4 py-2 text-[14px] font-semibold text-ink hover:bg-hover">
            {TA.annuler}
          </button>
          <button
            type="button"
            onClick={confirmer}
            disabled={envoi}
            className="rounded-full bg-marque px-4 py-2 text-[14px] font-bold text-on-marque disabled:opacity-60"
          >
            {bouton}
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
