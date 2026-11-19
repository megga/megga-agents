import { toNextJsHandler } from "better-auth/next-js";
import { auth } from "@/lib/auth";
import { pret } from "@/lib/base";

async function traiter(requete: Request) {
  await pret(); // Better Auth migré, et les tables de la console : une session créée note sa connexion (compte_connexion)
  const h = toNextJsHandler(auth());
  return requete.method === "GET" ? h.GET(requete) : h.POST(requete);
}

export { traiter as GET, traiter as POST };
