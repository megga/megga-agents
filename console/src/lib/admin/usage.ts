import type { DatabaseSync } from "node:sqlite";
import type { Jours } from "./atelier";

// Le compteur de messages de la console (usage_agent : un agent, un jour UTC, un nombre, jamais un texte) et la dernière
// connexion d'un compte (compte_connexion). Le compteur s'écrit après la réponse de l'agent (after, dans la route de
// CopilotKit) : il ne retarde ni ne fait échouer une conversation. auth.ts importe noterConnexion : rien ici n'importe auth.ts.

const BASE_COPILOTKIT = "/api/copilotkit";
const JOUR_MS = 24 * 3600 * 1000;

const jourUtc = (quand: Date) => quand.toISOString().slice(0, 10);

function decode(segment: string): string | null {
  try {
    return decodeURIComponent(segment);
  } catch {
    return null;
  }
}

/**
 * L'agent d'un tour (POST …/agent/<id>/run), ou null. La règle de CopilotKit (fetch-router.mjs, matchSegments) : sous
 * /api/copilotkit, les trois derniers segments non vides ; l'identifiant décodé.
 */
export function agentDuTour(methode: string, chemin: string): string | null {
  if (methode !== "POST") return null;
  if (chemin !== BASE_COPILOTKIT && !chemin.startsWith(BASE_COPILOTKIT + "/")) return null;
  const s = chemin.slice(BASE_COPILOTKIT.length).split("/").filter(Boolean);
  const n = s.length;
  if (n < 3 || s[n - 3] !== "agent" || s[n - 1] !== "run") return null;
  return decode(s[n - 2]) || null;
}

/** Un tour de plus pour cet agent, le jour UTC de quand. */
export function compterTour(db: DatabaseSync, agent: string, quand = new Date()): void {
  db.prepare(
    "INSERT INTO usage_agent (agent, jour, messages) VALUES (?, ?, 1) ON CONFLICT (agent, jour) DO UPDATE SET messages = messages + 1",
  ).run(agent, jourUtc(quand));
}

/** Compte un tour sans jamais lever : une panne (base, table) part à console.error, la conversation n'en sait rien. */
export function compterSansBloquer(db: () => DatabaseSync, agent: string): void {
  try {
    compterTour(db(), agent);
  } catch (e) {
    console.error("compteur de messages :", e);
  }
}

/** Les messages de chaque agent demandé, depuis un jour AAAA-MM-JJ inclus ; zéro pour un agent sans message. */
export function messagesDepuis(db: DatabaseSync, agents: readonly string[], depuis: string): Record<string, number> {
  const total: Record<string, number> = Object.fromEntries(agents.map((a) => [a, 0]));
  if (!agents.length) return total;
  const lignes = db
    .prepare(
      `SELECT agent, SUM(messages) AS n FROM usage_agent
       WHERE jour >= ? AND agent IN (SELECT value FROM json_each(?)) GROUP BY agent`,
    )
    .all(depuis, JSON.stringify(agents)) as { agent: string; n: number }[];
  for (const l of lignes) total[l.agent] = l.n;
  return total;
}

/** Les jours UTC de la période, du plus ancien au jour de maintenant compris. */
export function joursUtc(jours: number, maintenant = new Date()): string[] {
  return Array.from({ length: jours }, (_, i) => jourUtc(new Date(maintenant.getTime() - (jours - 1 - i) * JOUR_MS)));
}

/** Les messages de tous les agents, jour par jour sur la période (jours UTC), zéros compris, le plus ancien d'abord. */
export function messagesParJour(db: DatabaseSync, jours: Jours, maintenant = new Date()): { jour: string; messages: number }[] {
  const liste = joursUtc(jours, maintenant);
  const lignes = db
    .prepare("SELECT jour, SUM(messages) AS n FROM usage_agent WHERE jour >= ? AND jour <= ? GROUP BY jour")
    .all(liste[0], liste[liste.length - 1]) as { jour: string; n: number }[];
  const parJour = new Map(lignes.map((l) => [l.jour, l.n]));
  return liste.map((jour) => ({ jour, messages: parJour.get(jour) ?? 0 }));
}

/** La dernière connexion d'un compte (une session créée par Better Auth) ; une date plus ancienne n'efface pas la dernière. */
export function noterConnexion(db: DatabaseSync, utilisateur: string, quand = new Date()): void {
  db.prepare(
    `INSERT INTO compte_connexion (utilisateur, derniere) VALUES (?, ?)
     ON CONFLICT (utilisateur) DO UPDATE SET derniere = MAX(derniere, excluded.derniere)`,
  ).run(utilisateur, quand.toISOString());
}
