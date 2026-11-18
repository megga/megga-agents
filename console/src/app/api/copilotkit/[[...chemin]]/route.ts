import { T } from "@/lib/textes";
import { HttpAgent } from "@ag-ui/client";
import { CopilotRuntime, createCopilotRuntimeHandler } from "@copilotkit/runtime/v2";
import { after } from "next/server";
import { agentDuTour, compterSansBloquer } from "@/lib/admin/usage";
import { lister } from "@/lib/agents";
import { sessionDe } from "@/lib/auth";
import { base } from "@/lib/base";
import { enteteAgents, urlAgui } from "@/lib/serveur-agents";

// CopilotKit côté serveur : chaque requête ne voit que les agents du compte connecté,
// chacun branché par AG-UI au serveur d'agents. Le navigateur ne parle qu'à cette route.

process.env.COPILOTKIT_TELEMETRY_DISABLED ??= "true";

const utilisateurs = new WeakMap<Request, string>();

async function utilisateur(requete: Request): Promise<string | null> {
  const connu = utilisateurs.get(requete);
  if (connu) return connu;
  const s = await sessionDe(requete);
  if (s) utilisateurs.set(requete, s.user.id);
  return s?.user.id ?? null;
}

function agentsDu(id: string) {
  const agents: Record<string, HttpAgent> = {};
  for (const a of lister(base(), id)) {
    agents[a.id] = new HttpAgent({ agentId: a.id, url: urlAgui(a.id), headers: enteteAgents() });
  }
  return agents;
}

const runtime = new CopilotRuntime({
  agents: async ({ request }) => {
    const id = await utilisateur(request);
    const agents = id ? agentsDu(id) : {};
    if (!Object.keys(agents).length) throw new Error("aucun agent pour ce compte");
    return agents as Record<string, HttpAgent> & { [k: string]: HttpAgent };
  },
  identifyUser: async (request: Request) => {
    const id = await utilisateur(request);
    if (!id) throw new Error("non connecté");
    return { id, name: id };
  },
});

const gerer = createCopilotRuntimeHandler({ runtime, basePath: "/api/copilotkit" });

async function traiter(requete: Request) {
  const id = await utilisateur(requete);
  if (!id) return Response.json({ erreur: T.connectezVous }, { status: 401 });
  const agents = lister(base(), id);
  if (!agents.length) return Response.json({ erreur: "Aucun agent." }, { status: 404 });
  // Un tour accepté (réponse réussie : seuls ses en-têtes sont attendus, le flux part tel quel) à un agent du compte se
  // compte une fois la réponse finie (after) : jamais attendu, jamais un texte. Un tour refusé ne compte rien.
  const tour = agentDuTour(requete.method, new URL(requete.url).pathname);
  const r = await gerer(requete);
  if (r.ok && tour && agents.some((a) => a.id === tour)) after(() => compterSansBloquer(base, tour));
  return r;
}

export { traiter as GET, traiter as POST, traiter as PUT, traiter as PATCH, traiter as DELETE };
