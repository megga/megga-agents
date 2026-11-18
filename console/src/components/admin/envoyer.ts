import { TA } from "@/lib/admin/textes";

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
