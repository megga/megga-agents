import { redirect } from "next/navigation";
import { fournisseursActifs, inscriptionOuverte, session } from "@/lib/auth";
import { serveurAgents } from "@/lib/serveur-agents";
import { Connexion } from "./connexion";
import { messageErreur } from "./erreurs";
import { retourSur } from "./retour";

// ?error= : le code d'une erreur au retour de Google ou Microsoft (un compte suspendu : BANNED_USER), dit par une phrase de T,
// jamais tel quel.
export default async function PageConnexion({ searchParams }: PageProps<"/connexion">) {
  const p = await searchParams;
  // Sans équipe d'agents (en ligne), « / » ne fait que renvoyer à /admin : on y va directement, sans ce détour.
  const retour = retourSur(p.retour, serveurAgents() ? "/" : "/admin");
  if (await session()) redirect(retour);
  const erreur = p.error === undefined || p.error === "" ? null : messageErreur(p.error); // ?error= vide : comme sans paramètre
  return <Connexion fournisseurs={fournisseursActifs()} retour={retour} erreur={erreur} inscription={inscriptionOuverte()} />;
}

// Page propre à chaque compte : rendue à la demande, après la vérification de la session.
export const instant = false;
