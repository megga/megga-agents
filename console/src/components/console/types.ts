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
