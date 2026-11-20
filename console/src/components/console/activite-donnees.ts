// La page Activité, sans écran : ce qui se calcule des échanges entre agents (testé dans tests/activite.test.ts).

export type EchangeVu = {
  id: string;
  quand: number; // secondes
  de: string;
  a: string;
  question: string;
  etat: "remis" | "repondu" | "passe" | "hors_delai" | "echec";
  reponse: string | null;
};

/** Une question posée à un collègue pendant une conversation, avec l'échange qui lui correspond (s'il est rangé). */
export type EtapeVu = { collegue: string; question: string; echange: string | null; reponse: string | null; etat: EchangeVu["etat"] | null };

/** Une conversation d'un agent : le résumé d'Agno en une phrase (null tant qu'il n'est pas fait) et ses étapes. */
export type ConversationVu = { id: string; agent: string; quand: number; resume: string | null; etapes: EtapeVu[] };

/** Une ligne de la page Activité : une conversation, ou une question entre agents qui n'appartient à aucune conversation
 * affichée (jamais deux fois la même information). */
export type Action = ({ genre: "conversation" } & ConversationVu) | ({ genre: "echange" } & EchangeVu);

export function actions(conversations: ConversationVu[], echanges: EchangeVu[]): Action[] {
  const deja = new Set(conversations.flatMap((c) => c.etapes.map((e) => e.echange).filter(Boolean)));
  return [
    ...conversations.map((c) => ({ genre: "conversation" as const, ...c })),
    ...echanges.filter((e) => !deja.has(e.id)).map((e) => ({ genre: "echange" as const, ...e })),
  ].sort((a, b) => b.quand - a.quand);
}

/** Les trois chiffres de la période, tous tirés de ce qui s'est passé. */
export type Mesures = { conversations: number; reponses: number; echanges: number };

export type Periode = "jour" | "semaine" | "mois" | "an";
export const PERIODES: Periode[] = ["jour", "semaine", "mois", "an"];

/** Le début de la période, en secondes : minuit pour Aujourd'hui, sinon 7, 30 ou 365 jours en arrière. */
export function debut(p: Periode, maintenant = new Date()): number {
  if (p === "jour") {
    const m = new Date(maintenant);
    m.setHours(0, 0, 0, 0);
    return m.getTime() / 1000;
  }
  const jours = { semaine: 7, mois: 30, an: 365 }[p];
  return maintenant.getTime() / 1000 - jours * 86400;
}

const SANS_REPONSE = new Set(["hors_delai", "echec"]);

/** Un souci : une question restée sans réponse, seule ou dans une conversation. */
export function souci(a: Action | EchangeVu): boolean {
  if ("genre" in a && a.genre === "conversation") return a.etapes.some((e) => e.etat !== null && SANS_REPONSE.has(e.etat));
  return SANS_REPONSE.has((a as EchangeVu).etat);
}

/** Les temps forts, puis le reste : les soucis d'abord, en pleine largeur ; puis un nombre pair d'échanges, quatre au
 * plus, pour une grille toujours complète (maquette « Temps forts »). Le reste garde l'ordre, le plus récent d'abord. */
export function tempsForts<T extends Action | EchangeVu>(echanges: T[]): { forts: T[]; reste: T[] } {
  const soucis = echanges.filter(souci);
  const autres = echanges.filter((e) => !souci(e));
  let n = Math.min(4, autres.length);
  if (n > 1 && n % 2) n -= 1;
  const forts = [...soucis, ...autres.slice(0, n)];
  return { forts, reste: echanges.filter((e) => !forts.includes(e)) };
}

/** Le reste, rangé par jour (clé AAAA-MM-JJ, à l'heure locale), du plus récent au plus ancien. */
export function parJour<T extends { quand: number }>(echanges: T[]): [string, T[]][] {
  const jours = new Map<string, T[]>();
  for (const e of echanges) {
    const d = new Date(e.quand * 1000);
    const cle = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    jours.set(cle, [...(jours.get(cle) ?? []), e]);
  }
  return [...jours.entries()];
}
