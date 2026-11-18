"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Confirmation } from "@/components/admin/confirmation";
import { envoyer } from "@/components/admin/envoyer";
import { Fait } from "@/components/admin/erreurs";
import { cadre, champ, etiquette, titreBloc } from "@/components/admin/formulaire";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { TA } from "@/lib/admin/textes";

// Les gestes sur un compte de la console, chacun derrière une confirmation qui dit son effet : suspendre (avec un motif) ou
// réactiver ; déconnecter partout, s'il a des sessions ouvertes. La page ne les montre qu'au membre qui en a la main.

const adresse = (id: string) => `/api/admin/comptes/${encodeURIComponent(id)}`;

export function GestesCompte({ id, nom, suspendu, sessions }: { id: string; nom: string; suspendu: boolean; sessions: number }) {
  const router = useRouter();
  const [motif, setMotif] = useState("");
  const [fait, setFait] = useState<string | null>(null);

  async function agir(url: string, methode: "POST" | "DELETE", corps: unknown, texte: string) {
    await envoyer(url, methode, corps);
    setFait(texte);
    router.refresh();
  }

  return (
    <section className={cadre}>
      <h2 className={titreBloc}>{TA.gestesCompte}</h2>
      {!suspendu && (
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="compte-motif" className={etiquette}>{TA.motif}</Label>
          <Input id="compte-motif" value={motif} maxLength={200} autoComplete="off" onChange={(e) => setMotif(e.target.value)} className={champ} />
          <span className="text-[12.5px] text-faint">{TA.motifAide}</span>
        </div>
      )}
      <div className="flex flex-wrap items-center gap-2">
        {suspendu ? (
          <Confirmation
            titre={TA.reactiverTitre(nom)}
            effet={TA.effetReactiver}
            bouton={TA.reactiver}
            onConfirmer={() => agir(`${adresse(id)}/suspension`, "DELETE", undefined, TA.compteReactive)}
          >
            {TA.reactiver}
          </Confirmation>
        ) : (
          <Confirmation
            titre={TA.suspendreTitre(nom)}
            effet={TA.effetSuspendre}
            bouton={TA.suspendre}
            onConfirmer={async () => {
              await agir(`${adresse(id)}/suspension`, "POST", { motif: motif.trim() }, TA.compteSuspenduFait);
              setMotif("");
            }}
          >
            {TA.suspendre}
          </Confirmation>
        )}
        {sessions > 0 && (
          <Confirmation
            titre={TA.deconnecterTitre(nom)}
            effet={TA.effetDeconnecter}
            bouton={TA.deconnecterPartout}
            onConfirmer={() => agir(`${adresse(id)}/sessions`, "DELETE", undefined, TA.sessionsFermees)}
          >
            {TA.deconnecterPartout}
          </Confirmation>
        )}
      </div>
      <Fait texte={fait} />
    </section>
  );
}
