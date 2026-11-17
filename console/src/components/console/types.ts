// Ce que l'écran connaît d'un agent (la forme renvoyée par /api/agents).
export type AgentVu = {
  id: string;
  prenom: string;
  metier: string;
  couleur: number;
  yeux: number;
  epingle: boolean;
  creeLe: string;
};

/** Un message du fil, réduit à ce qui s'affiche. */
export type Bulle = { id: string; role: "user" | "assistant"; texte: string };

/** Le fil d'un agent : son identifiant de conversation (l'agent y retrouve ce qui a été dit) et ses messages. */
export type Memoire = { threadId: string; messages: { id: string; role: string; content?: unknown }[] };
