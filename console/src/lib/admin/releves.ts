import { filtrerClients, peut, type Acces } from "./acces";

// La vue d'ensemble d'après le relevé chiffré (GET /atelier/releves, 20.11.2026) : une seule lecture pour tous les clients,
// sans réveiller aucun conteneur, et jamais une conversation. Fonctions pures : le périmètre filtre les clients avant tout
// calcul, et les coûts disparaissent sans couts.voir.

type Delai = { nombre: number; moyenne: number | null };
export type JourReleve = {
  tours: number;
  tours_api: number;
  tours_en_echec: number;
  secours: number;
  personnes: number;
  delais?: { lecture: Delai; reponse: Delai; lentes: number };
  cout?: number;
};
export type ClientReleve = {
  id: string;
  entreprise: string | null;
  zone: string | null;
  actif: boolean;
  version_en_service: number | null;
  ecart: boolean;
  releve_le: number | null;
  silencieux: boolean;
  etat: { demarre?: boolean; pannes_en_cours?: { quoi: string; quand: number }[] } | null;
  totaux: { tours: number; tours_api: number; tours_en_echec: number; secours: number; cout: number; sans_tarif: string[] };
  jours: Record<string, JourReleve>;
};
export type Releves = { depuis: string | null; periode_jours: number; devise: string; clients: ClientReleve[] };

/** La santé d'un agent, la pire d'abord : silencieux, en panne, écart de version, tours en échec, en bonne santé. */
export type Sante = "silencieux" | "panne" | "ecart" | "echecs" | "ok";
const ORDRE: Record<Sante, number> = { silencieux: 4, panne: 3, ecart: 2, echecs: 1, ok: 0 };

export function santeDe(c: ClientReleve): Sante {
  if (c.silencieux) return "silencieux";
  if (c.etat?.pannes_en_cours?.length) return "panne";
  if (c.ecart) return "ecart";
  if (c.totaux.tours_en_echec > 0) return "echecs";
  return "ok";
}

export type LigneSante = {
  client: string;
  entreprise: string | null;
  sante: Sante;
  tours: number;
  echecs: number;
  secours: number;
  /** Le temps moyen jusqu'à la réponse, en secondes, sur la période ; null sans réponse mesurée. */
  reponse: number | null;
  releveLe: number | null;
  cout?: number;
};

export type VueReleves = {
  tuiles: { enService: number; aSurveiller: number; silencieux: number; tours: number; echecs: number; cout?: { devise: string; total: number } };
  lignes: LigneSante[];
  sansTarif: string[];
  /** Jour par jour, tous les clients du périmètre ensemble : tours, et coût avec couts.voir. */
  parJour: { jour: string; tours: number; cout: number }[];
};

/** Le temps moyen jusqu'à la réponse sur la période : la moyenne des jours, pondérée par leur nombre de réponses. */
function reponseMoyenne(jours: JourReleve[]): number | null {
  let n = 0;
  let somme = 0;
  for (const j of jours) {
    const d = j.delais?.reponse;
    if (d?.moyenne != null && d.nombre > 0) {
      n += d.nombre;
      somme += d.moyenne * d.nombre;
    }
  }
  return n ? Math.round((somme / n) * 10) / 10 : null;
}

const arrondi = (n: number) => Math.round(n * 10_000) / 10_000;

/** La vue d'ensemble des relevés du périmètre : un client inactif n'y compte pas ; la pire santé d'abord. */
export function agregerReleves(r: Releves, a: Acces): VueReleves {
  const voitCouts = peut(a, "couts.voir");
  const actifs = filtrerClients(a, r.clients).filter((c) => c.actif);
  const lignes: LigneSante[] = actifs
    .map((c) => ({
      client: c.id,
      entreprise: c.entreprise,
      sante: santeDe(c),
      tours: c.totaux.tours,
      echecs: c.totaux.tours_en_echec,
      secours: c.totaux.secours,
      reponse: reponseMoyenne(Object.values(c.jours)),
      releveLe: c.releve_le,
      ...(voitCouts ? { cout: c.totaux.cout } : {}),
    }))
    .sort((x, y) => ORDRE[y.sante] - ORDRE[x.sante] || y.tours - x.tours || x.client.localeCompare(y.client));
  const jours = new Map<string, { tours: number; cout: number }>();
  for (const c of actifs) {
    for (const [jour, j] of Object.entries(c.jours)) {
      const t = jours.get(jour) ?? { tours: 0, cout: 0 };
      t.tours += j.tours;
      if (voitCouts) t.cout += j.cout ?? 0;
      jours.set(jour, t);
    }
  }
  const tuiles: VueReleves["tuiles"] = {
    enService: actifs.length,
    aSurveiller: lignes.filter((l) => l.sante !== "ok").length,
    silencieux: lignes.filter((l) => l.sante === "silencieux").length,
    tours: lignes.reduce((n, l) => n + l.tours, 0),
    echecs: lignes.reduce((n, l) => n + l.echecs, 0),
  };
  if (voitCouts) tuiles.cout = { devise: r.devise, total: arrondi(actifs.reduce((n, c) => n + c.totaux.cout, 0)) };
  return {
    tuiles,
    lignes,
    sansTarif: voitCouts ? [...new Set(actifs.flatMap((c) => c.totaux.sans_tarif))].sort() : [],
    parJour: [...jours.entries()].sort(([x], [y]) => x.localeCompare(y)).map(([jour, t]) => ({ jour, tours: t.tours, cout: arrondi(t.cout) })),
  };
}
