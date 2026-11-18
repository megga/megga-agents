import { TA } from "@/lib/admin/textes";

// Des barres en CSS, aux jetons de la console (aucune bibliothèque de graphiques) : un cadre par légende, une barre par jour,
// chacun à sa propre échelle (quelques inscriptions et cent messages ne se lisent pas sur la même). Le nombre exact s'annonce
// une fois : un texte caché pour un lecteur d'écran (dans une barre positionnée : sinon il ferait défiler toute la page), et
// le même au survol, sur la zone aria-hidden de la barre. Le premier et le dernier jour sous les barres ; elles se serrent sans
// jamais déborder.

export function Barres({ jours, legendes }: { jours: { jour: string; valeurs: number[] }[]; legendes: string[] }) {
  if (!jours.length) return null;
  return (
    <div className="@container">
      <div className="grid gap-3 @2xl:grid-cols-2">
        {legendes.map((legende, k) => {
          const valeurs = jours.map((j) => j.valeurs[k] ?? 0);
          const max = Math.max(...valeurs);
          return (
            <figure key={legende} className="trait m-0 flex min-w-0 flex-col gap-2 rounded-2xl bg-bg px-4 pt-3 pb-3">
              <figcaption className="flex items-baseline justify-between gap-2">
                <span className="truncate text-[12.5px] font-semibold text-muted-ink">{legende}</span>
                <b className="text-[15px] font-extrabold tabular-nums">{TA.nombre(valeurs.reduce((s, v) => s + v, 0))}</b>
              </figcaption>
              <ol className="trait-b m-0 flex h-24 list-none items-end gap-[2px] p-0">
                {jours.map((j, i) => {
                  const texte = TA.barre(TA.jour(j.jour), valeurs[i]);
                  return (
                    <li key={j.jour} className="relative flex h-full min-w-0 flex-1">
                      <span className="sr-only">{texte}</span>
                      <span aria-hidden title={texte} className="flex h-full w-full items-end justify-center">
                        <span className="w-full max-w-7 rounded-t-[3px] bg-muted-ink" style={{ height: max ? `${(valeurs[i] / max) * 100}%` : 0 }} />
                      </span>
                    </li>
                  );
                })}
              </ol>
              <div aria-hidden className="flex justify-between gap-2 text-[11.5px] text-faint tabular-nums">
                <span>{TA.jour(jours[0].jour)}</span>
                {jours.length > 1 && <span>{TA.jour(jours[jours.length - 1].jour)}</span>}
              </div>
            </figure>
          );
        })}
      </div>
    </div>
  );
}
