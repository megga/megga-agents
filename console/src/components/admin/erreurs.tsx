// Un refus, tel que l'écran le montre : la phrase de la console (ou de l'atelier), et ses messages champ par champ.

export function ErreursChamps({ erreur, champs }: { erreur: string | null; champs?: { champ: string; message: string }[] }) {
  if (!erreur && !champs?.length) return null;
  return (
    <div role="alert" className="flex flex-col gap-1 text-[13.5px] font-semibold text-marque">
      {erreur && <p className="m-0">{erreur}</p>}
      {!!champs?.length && (
        <ul className="m-0 flex list-none flex-col gap-0.5 p-0 font-medium">
          {champs.map((c, i) => (
            <li key={i}>
              <b className="font-bold">{c.champ}</b> {c.message}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
