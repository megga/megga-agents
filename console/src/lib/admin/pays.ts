import CODES_ISO from "./pays-codes.json";

// Les pays des clients (20.11.2026) : un code ISO à deux lettres, réglé dans l'atelier (PUT /clients/{id}/pays), jamais dans
// la configuration de l'agent. La liste vient de scripts/carte-monde.cjs ; le nom en français, du navigateur ou de Node (Intl).

export const CODES_PAYS: readonly string[] = CODES_ISO;
const CONNUS: ReadonlySet<string> = new Set(CODES_ISO);

export const estPays = (x: unknown): x is string => typeof x === "string" && CONNUS.has(x);

const NOMS = new Intl.DisplayNames("fr", { type: "region", fallback: "code" });
export const nomPays = (code: string) => NOMS.of(code) ?? code;

/** Les pays dans l'ordre alphabétique de leur nom, pour un menu. */
export const paysTries = () =>
  CODES_PAYS.map((code) => ({ code, nom: nomPays(code) })).sort((x, y) => x.nom.localeCompare(y.nom, "fr"));
