import type { Base } from "@/lib/donnees/base";
import type { Jours } from "./atelier";

// Le compteur de messages de la console (usage_agent : un agent, un jour de Zurich, un nombre, jamais un texte) et la dernière
// connexion d'un compte (compte_connexion). Les jours sont ceux de Europe/Zurich, comme le journal et les dates de l'écran. Le compteur s'écrit après la réponse de l'agent (after, dans la route de
// CopilotKit) : il ne retarde ni ne fait échouer une conversation. auth.ts importe noterConnexion : rien ici n'importe auth.ts.

const BASE_COPILOTKIT = "/api/copilotkit";

const ZURICH = new Intl.DateTimeFormat("en-US", { timeZone: "Europe/Zurich", year: "numeric", month: "2-digit", day: "2-digit" });

/** Le jour de Zurich d'un instant, AAAA-MM-JJ (0 h 30 à Zurich est déjà le jour suivant en UTC moins une ou deux heures). */
export function jourZurich(quand: Date): string {
  const p = Object.fromEntries(ZURICH.formatToParts(quand).map((x) => [x.type, x.value]));
  return `${p.year}-${p.month}-${p.day}`;
}

/**
 * Les jours de Zurich de la période, du plus ancien à aujourd'hui compris : 1, aujourd'hui ; 7, aujourd'hui et les 6 jours
 * d'avant ; 30, aujourd'hui et les 29 jours d'avant. Compté en dates du calendrier : un changement d'heure ne saute aucun jour.
 */
export function joursZurich(jours: number, maintenant = new Date()): string[] {
  const [a, m, j] = jourZurich(maintenant).split("-").map(Number);
  return Array.from({ length: jours }, (_, i) => new Date(Date.UTC(a, m - 1, j - (jours - 1 - i))).toISOString().slice(0, 10));
}

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

/** Un tour de plus pour cet agent, le jour de Zurich de quand. */
export async function compterTour(b: Base, agent: string, quand = new Date()): Promise<void> {
  await b.ecrire(
    "INSERT INTO usage_agent (agent, jour, messages) VALUES (?, ?, 1) ON CONFLICT (agent, jour) DO UPDATE SET messages = usage_agent.messages + 1",
    agent, jourZurich(quand),
  );
}

/** Compte un tour sans jamais lever : une panne (base, table) part à console.error, la conversation n'en sait rien. */
export async function compterSansBloquer(b: () => Base | Promise<Base>, agent: string): Promise<void> {
  try {
    await compterTour(await b(), agent);
  } catch (e) {
    console.error("compteur de messages :", e);
  }
}

/** Les « ? » d'une liste IN (…) de n valeurs. */
export const marques = (n: number) => Array.from({ length: n }, () => "?").join(", ");

/** Les messages de chaque agent demandé, depuis un jour AAAA-MM-JJ inclus ; zéro pour un agent sans message. */
export async function messagesDepuis(b: Base, agents: readonly string[], depuis: string): Promise<Record<string, number>> {
  const total: Record<string, number> = Object.fromEntries(agents.map((a) => [a, 0]));
  if (!agents.length) return total;
  const lignes = await b.tous<{ agent: string; n: number }>(
    `SELECT agent, SUM(messages) AS n FROM usage_agent WHERE jour >= ? AND agent IN (${marques(agents.length)}) GROUP BY agent`,
    depuis, ...agents,
  );
  for (const l of lignes) total[l.agent] = l.n;
  return total;
}

/** Les messages de tous les agents, jour par jour sur la période (jours de Zurich), zéros compris, le plus ancien d'abord. */
export async function messagesParJour(b: Base, jours: Jours, maintenant = new Date()): Promise<{ jour: string; messages: number }[]> {
  const liste = joursZurich(jours, maintenant);
  const lignes = await b.tous<{ jour: string; n: number }>(
    "SELECT jour, SUM(messages) AS n FROM usage_agent WHERE jour >= ? AND jour <= ? GROUP BY jour",
    liste[0], liste[liste.length - 1],
  );
  const parJour = new Map(lignes.map((l) => [l.jour, l.n]));
  return liste.map((jour) => ({ jour, messages: parJour.get(jour) ?? 0 }));
}

/** La dernière connexion d'un compte (une session créée par Better Auth) ; une date plus ancienne n'efface pas la dernière. */
export async function noterConnexion(b: Base, utilisateur: string, quand = new Date()): Promise<void> {
  await b.ecrire(
    `INSERT INTO compte_connexion (utilisateur, derniere) VALUES (?, ?)
     ON CONFLICT (utilisateur) DO UPDATE SET derniere =
       CASE WHEN excluded.derniere > compte_connexion.derniere THEN excluded.derniere ELSE compte_connexion.derniere END`,
    utilisateur, quand.toISOString(),
  );
}
