import { redirect } from "next/navigation";
import { fournisseursActifs, session } from "@/lib/auth";
import { Connexion } from "./connexion";
import { messageErreur } from "./erreurs";
import { retourSur } from "./retour";

// ?error= : le code d'une erreur au retour de Google ou Microsoft (un compte suspendu : BANNED_USER), dit par une phrase de T,
// jamais tel quel.
export default async function PageConnexion({ searchParams }: PageProps<"/connexion">) {
  const p = await searchParams;
  const retour = retourSur(p.retour);
  if (await session()) redirect(retour);
  const erreur = p.error === undefined ? null : messageErreur(p.error);
  return <Connexion fournisseurs={fournisseursActifs()} retour={retour} erreur={erreur} />;
}

// Page propre à chaque compte : rendue à la demande, après la vérification de la session.
export const instant = false;
