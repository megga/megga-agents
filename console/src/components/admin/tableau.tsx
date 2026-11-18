// Un tableau aux contours d'un point d'écran. Trop large pour l'écran (390 px), il défile dans son cadre, jamais la page.
// replier : les colonnes secondaires (leurs indices) ; dans un cadre de moins de 64 rem, elles quittent le tableau et se
// lisent sous la première cellule de leur ligne, chacune avec son titre.

export function Tableau({ colonnes, lignes, vide, replier = [] }: {
  colonnes: string[];
  lignes: React.ReactNode[][];
  vide: string;
  replier?: number[];
}) {
  if (!lignes.length) {
    return <p className="trait m-0 rounded-2xl bg-bg px-4 py-6 text-center text-[14px] text-faint">{vide}</p>;
  }
  const masquee = (i: number) => (replier.includes(i) ? " @max-5xl:hidden" : "");
  return (
    <div className="@container trait max-w-full overflow-x-auto rounded-2xl bg-bg">
      <table className="w-full border-collapse text-left text-[14px]">
        <thead>
          <tr className="trait-b">
            {colonnes.map((c, i) => (
              <th key={i} scope="col" className={"px-3.5 py-2.5 text-[11.5px] font-bold tracking-[.06em] whitespace-nowrap text-faint uppercase" + masquee(i)}>
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {lignes.map((l, i) => (
            <tr key={i} className="align-top [&:not(:last-child)]:trait-b">
              {l.map((cellule, j) => (
                <td key={j} className={"px-3.5 py-2.5" + masquee(j)}>
                  {cellule}
                  {j === 0 && replier.length > 0 && (
                    <dl className="m-0 mt-1.5 flex flex-col gap-1 text-[13px] @5xl:hidden">
                      {replier.map((k) => (
                        <div key={k} className="flex flex-wrap items-baseline gap-x-2">
                          <dt className="text-[11.5px] font-bold tracking-[.06em] text-faint uppercase">{colonnes[k]}</dt>
                          <dd className="m-0">{l[k]}</dd>
                        </div>
                      ))}
                    </dl>
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
