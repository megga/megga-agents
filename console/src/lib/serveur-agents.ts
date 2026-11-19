import "server-only";
import type { EchangeVu, Mesures } from "@/components/console/activite-donnees";

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

// Les agents déjà inscrits avec leur compte par ce processus : une seule fois chacun.
const inscrits = new Set<string>();

/** Réinscrit, une fois, les agents d'un compte avec ce compte : un agent créé avant les collègues reçoit alors les siens.
 * Un échec n'empêche pas de parler à l'agent ; il sera retenté à la prochaine requête. */
export async function assurerInscriptions(
  agents: { id: string; prenom: string; metier: string }[],
  entreprise: string,
  compte: string,
): Promise<void> {
  await Promise.all(
    agents
      .filter((a) => !inscrits.has(`${a.id}:${compte}`))
      .map(async (a) => {
        try {
          await inscrire(a.id, { prenom: a.prenom, metier: a.metier, entreprise, compte });
          inscrits.add(`${a.id}:${compte}`);
        } catch (e) {
          console.error("réinscription d'agent :", e);
        }
      }),
  );
}

/** Les questions que les agents de ce compte se sont posées depuis cette date (en secondes), la plus récente d'abord. */
export async function lireEchanges(compte: string, depuis: number): Promise<EchangeVu[]> {
  const r = await fetch(`${adresseAgents()}/comptes/${encodeURIComponent(compte)}/echanges?depuis=${depuis}`, {
    headers: enteteAgents(),
    signal: AbortSignal.timeout(10_000),
    cache: "no-store",
  });
  if (!r.ok) throw new Error(`le serveur d'agents refuse la lecture des échanges (${r.status})`);
  return ((await r.json()) as { echanges: EchangeVu[] }).echanges;
}

/** Les trois chiffres de la page Activité pour ce compte depuis cette date (en secondes). */
export async function lireMesures(compte: string, depuis: number): Promise<Mesures> {
  const r = await fetch(`${adresseAgents()}/comptes/${encodeURIComponent(compte)}/mesures?depuis=${depuis}`, {
    headers: enteteAgents(),
    signal: AbortSignal.timeout(10_000),
    cache: "no-store",
  });
  if (!r.ok) throw new Error(`le serveur d'agents refuse la lecture des mesures (${r.status})`);
  return (await r.json()) as Mesures;
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
