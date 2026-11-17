import { redirect } from "next/navigation";
import { Console } from "@/components/console/console";
import { lister } from "@/lib/agents";
import { session } from "@/lib/auth";
import { base } from "@/lib/base";

export default async function Accueil() {
  const s = await session();
  if (!s) redirect("/connexion");
  return <Console entreprise={s.user.name || s.user.email} agentsInitiaux={lister(base(), s.user.id)} />;
}

// Page propre à chaque compte : rendue à la demande, après la vérification de la session.
export const instant = false;
