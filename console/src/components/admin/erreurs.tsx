import { TA } from "@/lib/admin/textes";

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

/**
 * Un geste envoyé à une route de /api/admin : son corps en JSON (null pour un 204), ou une Error qui porte la phrase du
 * refus (celle de la route, sinon une phrase générale), prête pour ErreursChamps ou Confirmation.
 */
export async function envoyer<T>(url: string, methode: "POST" | "PUT" | "PATCH" | "DELETE", corps?: unknown): Promise<T | null> {
  let r: Response;
  try {
    r = await fetch(url, {
      method: methode,
      headers: corps === undefined ? undefined : { "Content-Type": "application/json" },
      body: corps === undefined ? undefined : JSON.stringify(corps),
    });
  } catch {
    throw new Error(TA.erreurInterne);
  }
  if (r.status === 204) return null;
  const c = (await r.json().catch(() => null)) as { erreur?: unknown } | null;
  if (!r.ok) throw new Error(typeof c?.erreur === "string" && c.erreur ? c.erreur : TA.erreurInterne);
  return c as T;
}
