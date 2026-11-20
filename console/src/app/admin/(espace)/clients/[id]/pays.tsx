"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useDemande } from "@/components/admin/demande";
import { envoyer, refusDe } from "@/components/admin/envoyer";
import { TA } from "@/lib/admin/textes";

// Le pays du client, dans l'en-tête de sa fiche (clients.creer) : un menu ; chaque choix se confirme avant de partir. La liste
// et ses noms viennent du serveur : le navigateur ne les recalcule pas (son Intl pourrait nommer un pays autrement).
export function ChoixPays({ id, pays, liste }: { id: string; pays: string | null; liste: readonly { code: string; nom: string }[] }) {
  const router = useRouter();
  const { demander, fenetre } = useDemande();
  const [message, setMessage] = useState<string | null>(null);
  return (
    <span className="flex min-w-0 max-w-full flex-wrap items-center gap-2">
      <select
        aria-label={TA.choisirPays}
        value={pays ?? ""}
        onChange={(e) => {
          const code = e.target.value || null;
          demander(TA.paysQuestion(liste.find((p) => p.code === code)?.nom ?? null), code ? TA.enregistrer : TA.retirer, () => {
            envoyer(`/api/admin/clients/${encodeURIComponent(id)}/pays`, "PUT", { pays: code })
              .then(() => {
                setMessage(TA.paysEnregistre);
                router.refresh();
              })
              .catch((err: unknown) => setMessage(refusDe(err).erreur));
          });
        }}
        className="w-48 max-w-full min-w-0 truncate rounded-lg bg-transparent text-[14px] text-muted-ink hover:text-ink"
      >
        <option value="">{TA.aucunPays}</option>
        {liste.map((p) => (
          <option key={p.code} value={p.code}>{p.nom}</option>
        ))}
      </select>
      {message && <span role="status" className="text-[13px] text-muted-ink">{message}</span>}
      {fenetre}
    </span>
  );
}
