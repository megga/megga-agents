import { redirect } from "next/navigation";
import { fournisseursActifs, session } from "@/lib/auth";
import { Connexion } from "./connexion";

export default async function PageConnexion() {
  if (await session()) redirect("/");
  return <Connexion fournisseurs={fournisseursActifs()} />;
}

// Page propre à chaque compte : rendue à la demande, après la vérification de la session.
export const instant = false;
