import { TEXTE_ETAT } from "./pastille";

// Un refus, tel que l'écran le montre : la phrase de la console (ou de l'atelier), et ses messages champ par champ ;
// pour tout un écran, un bandeau (le moteur pas branché, l'atelier injoignable, la porte muette) ; la réussite d'un geste.

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

/** Un bandeau en tête d'un écran : un refus (accent), un avertissement (warn) ou une simple information (faint). */
export function Bandeau({ children, etat = "accent" }: { children: React.ReactNode; etat?: "accent" | "warn" | "faint" }) {
  return (
    <p role={etat === "accent" ? "alert" : "status"} className={"trait m-0 rounded-2xl bg-bg px-4 py-3 text-[14px] font-semibold " + TEXTE_ETAT[etat]}>
      {children}
    </p>
  );
}

/** La réussite d'un geste, sous lui (rien tant qu'il n'a pas réussi). */
export function Fait({ texte }: { texte: string | null }) {
  if (!texte) return null;
  return (
    <p role="status" className="m-0 text-[13.5px] font-semibold text-ok">
      {texte}
    </p>
  );
}
