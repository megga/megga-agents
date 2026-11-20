import type { ClientAtelier } from "./atelier";
import type { LigneSante } from "./releves";

// La carte du monde de la vue d'ensemble (20.11.2026) : les clients du périmètre rangés par pays, avec leurs tours de la
// période et ceux à surveiller. Fonction pure : les lignes arrivent déjà bornées au périmètre (agregerReleves, completer).

export type PaysVue = { code: string; clients: number; tours: number; aSurveiller: number };
export type VueMonde = { pays: PaysVue[]; sansPays: number };

const A_SURVEILLER = new Set(["silencieux", "panne", "ecart", "soucis"]);

export function vueMonde(lignes: readonly LigneSante[], clients: readonly Pick<ClientAtelier, "id" | "pays">[]): VueMonde {
  const paysDe = new Map(clients.map((c) => [c.id, c.pays ?? null]));
  const parPays = new Map<string, PaysVue>();
  let sansPays = 0;
  for (const l of lignes) {
    const code = paysDe.get(l.client);
    if (!code) {
      sansPays += 1;
      continue;
    }
    const p = parPays.get(code) ?? { code, clients: 0, tours: 0, aSurveiller: 0 };
    p.clients += 1;
    p.tours += l.tours;
    if (A_SURVEILLER.has(l.sante)) p.aSurveiller += 1;
    parPays.set(code, p);
  }
  return {
    pays: [...parPays.values()].sort((x, y) => y.clients - x.clients || y.tours - x.tours || x.code.localeCompare(y.code)),
    sansPays,
  };
}
