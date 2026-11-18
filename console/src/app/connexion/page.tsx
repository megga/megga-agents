import { redirect } from "next/navigation";
import { fournisseursActifs, session } from "@/lib/auth";
import { Connexion } from "./connexion";
import { retourSur } from "./retour";

export default async function PageConnexion({ searchParams }: PageProps<"/connexion">) {
  const retour = retourSur((await searchParams).retour);
  if (await session()) redirect(retour);
  return <Connexion fournisseurs={fournisseursActifs()} retour={retour} />;
}

// Page propre à chaque compte : rendue à la demande, après la vérification de la session.
export const instant = false;
