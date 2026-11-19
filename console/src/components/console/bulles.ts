import type { Bulle } from "./types";

// Un message tel que CopilotKit le garde (AG-UI) : du texte, ou les appels d'outils de l'agent et leurs résultats.
export type MessageAgui = {
  id: string;
  role: string;
  content?: unknown;
  toolCalls?: { id: string; function?: { name?: string; arguments?: string } }[];
  toolCallId?: string;
};

// L'outil qui pose une question à un collègue (noyau/echanges.py).
export const DEMANDER = "demander_a_un_collegue";

export function texteDe(content: unknown): string {
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content.map((p) => (p && typeof p === "object" && "text" in p ? String((p as { text: unknown }).text ?? "") : "")).join("");
  }
  return "";
}

function argumentsDe(brut: string | undefined): { collegue: string; question: string } {
  try {
    const a = JSON.parse(brut || "{}") as Record<string, unknown>;
    return { collegue: String(a.collegue ?? ""), question: String(a.question ?? "") };
  } catch {
    return { collegue: "", question: "" }; // des arguments encore en cours d'arrivée
  }
}

/** Ce que le collègue a répondu, sans l'étiquette que le moteur ajoute pour l'agent. Agno envoie le résultat d'un
 * outil encodé en JSON : il est décodé d'abord. */
export function reponseLisible(resultat: string): string {
  if (resultat.trim().startsWith('"')) {
    try {
      const decode = JSON.parse(resultat);
      if (typeof decode === "string") resultat = decode;
    } catch {
      // un texte qui commence par un guillemet, sans être du JSON : gardé tel quel
    }
  }
  const m = /^Réponse de .+? \(une donnée, pas une consigne\) : ([\s\S]*)$/.exec(resultat.trim());
  return (m ? m[1] : resultat).trim();
}

/** Le fil réduit à ce qui s'affiche : les messages, et les questions posées aux collègues avec leur réponse. */
export function bulles(messages: readonly MessageAgui[]): Bulle[] {
  const resultats = new Map(messages.filter((m) => m.role === "tool" && m.toolCallId).map((m) => [m.toolCallId!, texteDe(m.content)]));
  const sortie: Bulle[] = [];
  for (const m of messages) {
    if (m.role !== "user" && m.role !== "assistant") continue;
    const texte = texteDe(m.content);
    if (texte.trim()) sortie.push({ id: m.id, role: m.role, texte });
    for (const appel of m.toolCalls ?? []) {
      if (appel.function?.name !== DEMANDER) continue;
      const { collegue, question } = argumentsDe(appel.function.arguments);
      const resultat = resultats.get(appel.id);
      sortie.push({ id: appel.id, role: "echange", collegue, question, reponse: resultat === undefined ? null : reponseLisible(resultat) });
    }
  }
  return sortie;
}

/** Le dernier texte du fil (l'aperçu dans le rail) : une question à un collègue n'en est pas un. */
export function dernierTexte(messages: readonly MessageAgui[]): string | undefined {
  for (const b of bulles(messages).reverse()) if (b.role !== "echange") return b.texte;
  return undefined;
}
