// La forme d'une page de l'admin pendant qu'elle se prépare : un titre, une rangée de tuiles, des lignes. Sans texte ni
// délai annoncé ; elle s'affiche dès le clic, et la page la remplace quand elle est prête (loading.tsx).

const bloc = "animate-pulse rounded-2xl bg-hover";

export function AttentePage({ titre = true }: { titre?: boolean }) {
  return (
    <div aria-busy="true" className="flex flex-col gap-5">
      {titre && <div className={bloc + " h-9 w-64 max-w-full"} />}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className={bloc + " h-[86px]"} />
        ))}
      </div>
      <div className="flex flex-col gap-2">
        {[0, 1, 2, 3, 4].map((i) => (
          <div key={i} className={bloc + " h-14"} />
        ))}
      </div>
    </div>
  );
}
