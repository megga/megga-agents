import { redirect } from "next/navigation";
import { connection } from "next/server";
import { Console } from "@/components/console/console";
import { accesDe } from "@/lib/admin/membres";
import { lister } from "@/lib/agents";
import { session } from "@/lib/auth";
import { base, pret } from "@/lib/base";

export default async function Accueil() {
  await connection(); // à la requête seulement : l'accès à l'admin se compare à l'heure du moment
  const s = await session();
  if (!s) redirect("/connexion");
  // Membre de l'admin : exactement ceux à qui /admin s'ouvre (gardePage), pour que le menu ne mène jamais à une page 404.
  const membre = accesDe(base(), s.user) !== undefined;
  return <Console entreprise={s.user.name || s.user.email} agentsInitiaux={await lister(await pret(), s.user.id)} membre={membre} />;
}

// Page propre à chaque compte : rendue à la demande, après la vérification de la session.
export const instant = false;
