"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Confirmation } from "@/components/admin/confirmation";
import { envoyer } from "@/components/admin/envoyer";
import { Fait } from "@/components/admin/erreurs";
import { Tableau } from "@/components/admin/tableau";
import { TA } from "@/lib/admin/textes";
import { enTexte, type Difference } from "@/lib/admin/versions";

// Le pilotage d'une version (clients.piloter) : la mettre en service, y revenir, la forcer, ou la relancer après un écart,
// chacun derrière une confirmation qui dit son effet ; et le tableau de ce qui change d'une configuration à l'autre, partagé
// par la version ouverte et l'aperçu d'un brouillon (preparer.tsx). La route refait les contrôles : l'écran les suit.

/** Ce qui change d'une configuration à l'autre : le réglage, avant, après (repliés sous le réglage dans un cadre étroit). */
export function TableauDifferences({ liste }: { liste: Difference[] }) {
  const valeur = (v: unknown) => <span className="whitespace-pre-wrap wrap-anywhere">{enTexte(v)}</span>;
  return (
    <Tableau
      colonnes={[TA.reglage, TA.avant, TA.apres]}
      vide={TA.rienNeChange}
      replier={[1, 2]}
      lignes={liste.map((d) => [<b key="champ" className="font-bold wrap-anywhere">{d.champ}</b>, valeur(d.avant), valeur(d.apres)])}
    />
  );
}

type Geste = { titre: string; bouton: string; effet: string; forcer: boolean };

/**
 * Le geste de pilotage d'une version, s'il y en a un. L'effet : le conteneur redémarre, ou hors Cloudflare un ordre signé part
 * (ordre) ; la zone inconnue (null, catalogue illisible), il dit les deux cas plutôt qu'un effet peut-être faux.
 */
export function gesteDe(v: { numero: number; etat: "brouillon" | "publiee"; essais: number }, enService: number | null, ecart: boolean,
  ordre: boolean | null): Geste | null {
  const n = v.numero;
  const effet = ordre === null ? TA.effetSelonZone(n) : ordre ? TA.effetOrdre(n) : TA.effetActiver(n);
  if (v.etat === "brouillon" && v.essais === 0) return { titre: TA.forcerTitre(n), bouton: TA.forcer, effet: `${TA.jamaisEssayee} ${effet}`, forcer: true };
  if (n === enService) return ecart ? { titre: TA.relancerTitre(n), bouton: TA.mettreEnService, effet: `${TA.ecartARelancer} ${effet}`, forcer: false } : null;
  if (v.etat === "publiee" && enService !== null && n < enService) return { titre: TA.revenirTitre(n), bouton: TA.revenirVersion, effet, forcer: false };
  return { titre: TA.mettreEnServiceTitre(n), bouton: TA.mettreEnService, effet, forcer: false };
}

/** Mettre en service, revenir à une version, forcer, ou relancer après un écart (clients.piloter), derrière une confirmation. */
export function GestesVersion({ id, version, enService, ecart, ordre }: {
  id: string;
  version: { numero: number; etat: "brouillon" | "publiee"; essais: number };
  enService: number | null;
  ecart: boolean;
  /** Hors Cloudflare : un ordre signé part à l'installation au lieu de redémarrer un conteneur ; null : zone inconnue. */
  ordre: boolean | null;
}) {
  const router = useRouter();
  const [fait, setFait] = useState<string | null>(null);
  const geste = gesteDe(version, enService, ecart, ordre);
  if (!geste && !fait) return null;
  return (
    <div className="flex flex-wrap items-center gap-3">
      {geste && (
        <Confirmation
          titre={geste.titre}
          effet={geste.effet}
          bouton={geste.bouton}
          onConfirmer={async () => {
            const r = await envoyer<{ pilotage?: { ordre?: number } }>(`/api/admin/clients/${encodeURIComponent(id)}/versions/${version.numero}/activer`,
              "POST", geste.forcer ? { forcer: true } : {});
            const ordrePart = typeof r?.pilotage?.ordre === "number" ? ` ${TA.ordreParti(r.pilotage.ordre)}` : "";
            setFait(TA.enServiceFait(version.numero) + ordrePart);
            router.refresh();
          }}
        >
          {geste.bouton}
        </Confirmation>
      )}
      <Fait texte={fait} />
    </div>
  );
}
