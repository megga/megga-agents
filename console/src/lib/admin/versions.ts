import { TA } from "./textes";

// L'écart entre deux configurations, et une configuration lue à plat : des chemins pointés (voix.voix), une liste ou un objet
// vide comparés entiers. Pur, sans serveur : l'onglet Versions s'en sert aussi dans le navigateur, après « Valider ».

export type Difference = { champ: string; avant: unknown; apres: unknown };

const estObjet = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);

/** Les feuilles d'une configuration, dans son ordre : un objet non vide se déplie, tout le reste est une valeur. */
function aPlat(config: Record<string, unknown>, prefixe = ""): [string, unknown][] {
  return Object.entries(config).flatMap(([k, v]): [string, unknown][] => {
    const chemin = prefixe ? `${prefixe}.${k}` : k;
    return estObjet(v) && Object.keys(v).length ? aPlat(v, chemin) : [[chemin, v]];
  });
}

/** Ce qui change d'une configuration à l'autre, champ par champ, trié ; sans configuration d'avant, chaque champ. */
export function differences(avant: Record<string, unknown> | null, apres: Record<string, unknown>): Difference[] {
  const a = new Map(aPlat(avant ?? {}));
  const b = new Map(aPlat(apres));
  return [...new Set([...a.keys(), ...b.keys()])]
    .sort()
    .filter((champ) => JSON.stringify(a.get(champ)) !== JSON.stringify(b.get(champ)))
    .map((champ) => ({ champ, avant: a.get(champ), apres: b.get(champ) }));
}

/** Une valeur à l'écran : un texte tel quel, le reste en JSON ; absente, un tiret court. */
export function enTexte(v: unknown): string {
  if (v === undefined) return TA.inconnu;
  return typeof v === "string" ? v : JSON.stringify(v);
}

/** Une configuration à plat, avec les mêmes chemins que differences. */
export function lisible(config: Record<string, unknown>): { champ: string; valeur: string }[] {
  return aPlat(config).map(([champ, v]) => ({ champ, valeur: enTexte(v) }));
}

const NUMERO = /^[1-9]\d{0,8}$/;

/** Le numéro d'une version (dans une adresse ou un corps) : un entier positif, sinon null. */
export function numeroVersion(v: unknown): number | null {
  if (typeof v === "string") return NUMERO.test(v) ? Number(v) : null;
  return typeof v === "number" && Number.isInteger(v) && v >= 1 && v < 1e9 ? v : null;
}
