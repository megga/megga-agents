import { connection } from "next/server";

// La santé de la console, sans session : ce que le Worker megga-console attend avant de transmettre (console/hebergement).
// Elle dit que la console tourne et de quel commit vient l'image, rien d'autre. Elle ne touche pas à la base : le Worker
// n'a pas besoin de réveiller Neon pour savoir que le conteneur est prêt.
export async function GET() {
  await connection(); // à la requête seulement : la révision est celle du conteneur, pas celle de la construction
  return Response.json({ ok: true, revision: process.env.CONSOLE_REVISION ?? null }, { headers: { "cache-control": "no-store" } });
}
