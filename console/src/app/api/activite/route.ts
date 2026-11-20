import { T } from "@/lib/textes";
import { lister } from "@/lib/agents";
import { sessionDe } from "@/lib/auth";
import { base } from "@/lib/base";
import { lireConversations, lireEchanges, lireMesures } from "@/lib/serveur-agents";

// Les échanges entre les agents du compte connecté depuis une date (page Activité). Jamais ceux d'un autre compte.
export async function GET(requete: Request) {
  const s = await sessionDe(requete);
  if (!s) return Response.json({ erreur: T.connectezVous }, { status: 401 });
  const depuis = Number(new URL(requete.url).searchParams.get("depuis") ?? 0);
  if (!Number.isFinite(depuis) || depuis < 0) return Response.json({ erreur: T.erreurGenerale }, { status: 400 });
  const ids = new Set(lister(base(), s.user.id).map((a) => a.id));
  try {
    const [tous, mesures, conversations] = await Promise.all([
      lireEchanges(s.user.id, depuis),
      lireMesures(s.user.id, depuis),
      lireConversations(s.user.id, depuis),
    ]);
    return Response.json({
      echanges: tous.filter((e) => ids.has(e.de) && ids.has(e.a)),
      conversations: conversations.filter((c) => ids.has(c.agent)),
      mesures,
    });
  } catch (e) {
    console.error("activité :", e);
    return Response.json({ erreur: T.serviceIndisponible }, { status: 502 });
  }
}
