import Link from "next/link";
import type { Jours } from "@/lib/admin/atelier";
import { TA } from "@/lib/admin/textes";

// Le choix de la période (24 heures, 7 jours, 30 jours, glissantes comme l'atelier les compte), en liens : la période passe
// par l'adresse (?jours=). chemin peut porter d'autres paramètres (?tri=), gardés.

const PERIODES: { jours: Jours; texte: string }[] = [
  { jours: 1, texte: TA.periode24h },
  { jours: 7, texte: TA.periode7j },
  { jours: 30, texte: TA.periode30j },
];

export function ChoixPeriode({ jours, chemin }: { jours: Jours; chemin: string }) {
  const vers = (j: Jours) => `${chemin}${chemin.includes("?") ? "&" : "?"}jours=${j}`;
  return (
    <nav aria-label={TA.periode} className="trait flex w-fit max-w-full gap-0.5 rounded-full bg-bg p-0.5">
      {PERIODES.map((p) => (
        <Link
          key={p.jours}
          href={vers(p.jours)}
          aria-current={p.jours === jours ? "page" : undefined}
          className="rounded-full px-3 py-1 text-[13px] font-semibold whitespace-nowrap text-muted-ink hover:text-ink aria-[current=page]:bg-ink aria-[current=page]:text-bg"
        >
          {p.texte}
        </Link>
      ))}
    </nav>
  );
}
