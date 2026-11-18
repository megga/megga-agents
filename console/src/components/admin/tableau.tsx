// Un tableau aux contours d'un point d'écran. Trop large pour l'écran (390 px), il défile dans son cadre, jamais la page.

export function Tableau({ colonnes, lignes, vide }: { colonnes: string[]; lignes: React.ReactNode[][]; vide: string }) {
  if (!lignes.length) {
    return <p className="trait m-0 rounded-2xl bg-bg px-4 py-6 text-center text-[14px] text-faint">{vide}</p>;
  }
  return (
    <div className="trait max-w-full overflow-x-auto rounded-2xl bg-bg">
      <table className="w-full border-collapse text-left text-[14px]">
        <thead>
          <tr className="trait-b">
            {colonnes.map((c, i) => (
              <th key={i} scope="col" className="px-3.5 py-2.5 text-[11.5px] font-bold tracking-[.06em] whitespace-nowrap text-faint uppercase">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {lignes.map((l, i) => (
            <tr key={i} className="align-top [&:not(:last-child)]:trait-b">
              {l.map((cellule, j) => (
                <td key={j} className="px-3.5 py-2.5">
                  {cellule}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
