import "server-only";

// Le serveur d'agents (console/agents/serveur.py en local ; l'atelier plus tard).
// Le navigateur ne lui parle jamais : seule la console, avec le jeton partagé.

export function adresseAgents(): string {
  return (process.env.AGENTS_URL || "http://127.0.0.1:8100").replace(/\/+$/, "");
}

export function enteteAgents(): Record<string, string> {
  return { Authorization: `Bearer ${process.env.AGENTS_JETON || ""}` };
}

export function urlAgui(id: string): string {
  return `${adresseAgents()}/agents/${encodeURIComponent(id)}/agui`;
}

/** Met l'agent en service tout de suite : il répond dès sa création. */
/** `compte` : les agents d'un même compte sont collègues et peuvent se poser des questions. */
export async function inscrire(id: string, fiche: { prenom: string; metier: string; entreprise: string; compte: string }): Promise<void> {
  const r = await fetch(`${adresseAgents()}/agents/${encodeURIComponent(id)}`, {
    method: "PUT",
    headers: { ...enteteAgents(), "Content-Type": "application/json" },
    body: JSON.stringify(fiche),
    signal: AbortSignal.timeout(10_000), // un serveur bloqué ne fige pas la création
  });
  if (!r.ok) throw new Error(`le serveur d'agents refuse l'inscription (${r.status})`);
}
