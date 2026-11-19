import { redirect } from "next/navigation";
import { connection } from "next/server";
import { Console } from "@/components/console/console";
import { accesDe } from "@/lib/admin/membres";
import { lister } from "@/lib/agents";
import { session } from "@/lib/auth";
import { pret } from "@/lib/base";
import { serveurAgents } from "@/lib/serveur-agents";

export default async function Accueil() {
  await connection(); // à la requête seulement : l'accès à l'admin se compare à l'heure du moment
  if (!serveurAgents()) redirect("/admin"); // pas encore d'équipe d'agents (en ligne) : l'admin seul
  const s = await session();
  if (!s) redirect("/connexion");
  // Membre de l'admin : exactement ceux à qui /admin s'ouvre (gardePage), pour que le menu ne mène jamais à une page 404.
  const b = await pret();
  const membre = (await accesDe(b, s.user)) !== undefined;
  return <Console entreprise={s.user.name || s.user.email} image={s.user.image ?? null} agentsInitiaux={await lister(b, s.user.id)} membre={membre} />;
}

// Page propre à chaque compte : rendue à la demande, après la vérification de la session.
export const instant = false;
