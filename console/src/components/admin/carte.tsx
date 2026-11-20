import fond from "@/lib/admin/carte-monde.json";
import type { PaysVue } from "@/lib/admin/monde";
import { nomPays } from "@/lib/admin/pays";
import { TA } from "@/lib/admin/textes";

// La carte du monde, en SVG rendu côté serveur (aucune bibliothèque, aucun script) : le fond vient de
// scripts/carte-monde.mjs (Natural Earth). Un pays qui a des clients se fonce selon ses tours de la période, à l'échelle du
// plus actif ; un pays dont un client est à surveiller prend la couleur d'avertissement. Le détail se lit au survol, et le
// tableau sous la carte le redit pour un lecteur d'écran. Un petit pays absent du fond (Monaco) n'est que dans le tableau.

const FORMES = fond.pays as Record<string, string>;

export function Carte({ pays }: { pays: readonly PaysVue[] }) {
  const max = Math.max(1, ...pays.map((p) => p.tours));
  const parCode = new Map(pays.map((p) => [p.code, p]));
  return (
    <figure className="trait m-0 rounded-2xl bg-bg p-3">
      <svg viewBox={fond.vue} role="img" aria-label={TA.carteMonde} stroke="var(--bg)" strokeWidth={0.6} className="block h-auto w-full">
        {Object.entries(FORMES).map(([code, d]) => {
          const p = parCode.get(code);
          if (!p) return <path key={code} d={d} fill="var(--hover)" />;
          return (
            <path key={code} d={d} fill={p.aSurveiller ? "var(--warn)" : "var(--ink)"} fillOpacity={0.35 + 0.65 * (p.tours / max)}>
              <title>{TA.survolPays(nomPays(code), p.clients, p.tours)}</title>
            </path>
          );
        })}
      </svg>
    </figure>
  );
}
