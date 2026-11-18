import { estChamp, type ChampErreur } from "@/lib/admin/champs";
import { TA } from "@/lib/admin/textes";

/** Le refus d'une route : sa phrase, et pour un refus de l'atelier, ses messages champ par champ (ErreursChamps). */
export class RefusEnvoi extends Error {
  constructor(message: string, public champs: ChampErreur[] = []) {
    super(message);
  }
}

/**
 * Un geste envoyé à une route de /api/admin : son corps en JSON (null pour un 204), ou un RefusEnvoi qui porte la phrase du
 * refus (celle de la route, sinon une phrase générale) et ses messages champ par champ, prêt pour ErreursChamps ou Confirmation.
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
    throw new RefusEnvoi(TA.erreurInterne);
  }
  if (r.status === 204) return null;
  const c = (await r.json().catch(() => null)) as { erreur?: unknown; champs?: unknown } | null;
  if (!r.ok) {
    const champs = Array.isArray(c?.champs) ? c.champs.filter(estChamp) : [];
    throw new RefusEnvoi(typeof c?.erreur === "string" && c.erreur ? c.erreur : TA.erreurInterne, champs);
  }
  return c as T;
}

/** Le refus d'un geste pour l'écran : sa phrase, et ses messages champ par champ s'il vient d'une route (RefusEnvoi). */
export function refusDe(e: unknown): { erreur: string; champs: ChampErreur[] } {
  return { erreur: e instanceof Error && e.message ? e.message : TA.erreurInterne, champs: e instanceof RefusEnvoi ? e.champs : [] };
}
