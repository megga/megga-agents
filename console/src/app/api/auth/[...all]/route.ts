import { toNextJsHandler } from "better-auth/next-js";
import { auth, migrer } from "@/lib/auth";

async function traiter(requete: Request) {
  await migrer();
  const h = toNextJsHandler(auth());
  return requete.method === "GET" ? h.GET(requete) : h.POST(requete);
}

export { traiter as GET, traiter as POST };
