import "server-only";
import { T } from "./textes";

// Le serveur d'agents (console/agents/serveur.py en local ; l'atelier plus tard).
// Le navigateur ne lui parle jamais : seule la console, avec le jeton partagé.
// Sans AGENTS_URL (en ligne, tant que l'équipe d'agents n'existe pas), il n'est pas branché : la racine mène à /admin et
// les routes des agents répondent 503 (nonBranches).

/** L'adresse du serveur d'agents, ou null s'il n'est pas branché. Pas de valeur par défaut : le local la pose (.env.local). */
export function serveurAgents(): string | null {
  return process.env.AGENTS_URL?.replace(/\/+$/, "") || null;
}

/** La réponse des routes des agents quand le serveur n'est pas branché. */
export function nonBranches(): Response {
  return Response.json({ erreur: T.agentsNonBranches }, { status: 503 });
}

function adresseAgents(): string {
  const a = serveurAgents();
  if (!a) throw new Error("AGENTS_URL n'est pas posée : le serveur d'agents n'est pas branché");
  return a;
}

export function enteteAgents(): Record<string, string> {
  return { Authorization: `Bearer ${process.env.AGENTS_JETON || ""}` };
}

export function urlAgui(id: string): string {
  return `${adresseAgents()}/agents/${encodeURIComponent(id)}/agui`;
}

/** Met l'agent en service tout de suite : il répond dès sa création. */
export async function inscrire(id: string, fiche: { prenom: string; metier: string; entreprise: string }): Promise<void> {
  const r = await fetch(`${adresseAgents()}/agents/${encodeURIComponent(id)}`, {
    method: "PUT",
    headers: { ...enteteAgents(), "Content-Type": "application/json" },
    body: JSON.stringify(fiche),
    signal: AbortSignal.timeout(10_000), // un serveur bloqué ne fige pas la création
  });
  if (!r.ok) throw new Error(`le serveur d'agents refuse l'inscription (${r.status})`);
}
