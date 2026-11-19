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

/** Un souci : la question n'a pas eu de réponse. */
export function souci(e: EchangeVu): boolean {
  return e.etat === "hors_delai" || e.etat === "echec";
}

/** Les temps forts, puis le reste : les soucis d'abord, en pleine largeur ; puis un nombre pair d'échanges, quatre au
 * plus, pour une grille toujours complète (maquette « Temps forts »). Le reste garde l'ordre, le plus récent d'abord. */
export function tempsForts(echanges: EchangeVu[]): { forts: EchangeVu[]; reste: EchangeVu[] } {
  const soucis = echanges.filter(souci);
  const autres = echanges.filter((e) => !souci(e));
  let n = Math.min(4, autres.length);
  if (n > 1 && n % 2) n -= 1;
  const forts = [...soucis, ...autres.slice(0, n)];
  return { forts, reste: echanges.filter((e) => !forts.includes(e)) };
}

/** Le reste, rangé par jour (clé AAAA-MM-JJ, à l'heure locale), du plus récent au plus ancien. */
export function parJour(echanges: EchangeVu[]): [string, EchangeVu[]][] {
  const jours = new Map<string, EchangeVu[]>();
  for (const e of echanges) {
    const d = new Date(e.quand * 1000);
    const cle = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    jours.set(cle, [...(jours.get(cle) ?? []), e]);
  }
  return [...jours.entries()];
}
