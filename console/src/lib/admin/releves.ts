import { filtrerClients, peut, type Acces } from "./acces";
import type { ClientAtelier } from "./atelier";

// La vue d'ensemble d'après le relevé chiffré (GET /atelier/releves, 20.11.2026) : une seule lecture pour tous les clients,
// sans réveiller aucun conteneur, et jamais une conversation. Fonctions pures : le périmètre filtre les clients avant tout
// calcul, et les coûts disparaissent sans couts.voir.

/** mediane et p95 (95 % des cas en dessous), depuis le 20.11.2026 : absents ou nuls d'un relevé plus ancien. */
type Delai = { nombre: number; moyenne: number | null; mediane?: number | null; p95?: number | null };
/** Un outil de l'agent sur un jour : appels, échecs, durée totale des appels qui l'ont dite (mesures), en secondes. */
type OutilJour = { appels: number; echecs: number; duree: number; mesures: number };
export type JourReleve = {
  tours: number;
  tours_api: number;
  tours_en_echec: number;
  secours: number;
  personnes: number;
  delais?: { lecture: Delai; reponse: Delai; lentes: number };
  journal?: Record<string, { nombre?: number; quantite?: number }>;
  outils?: Record<string, OutilJour>;
  /** Les jetons de chaque modèle du jour (agno_runs). */
  modeles?: Record<string, { tours: number; entree: number; sortie: number; cache_lecture: number; cache_ecriture: number }>;
  cout?: number;
  /** Le coût du jour poste par poste (chaque modèle, la voix, l'écoute), depuis le 21.11.2026 : absent d'un atelier plus ancien. */
  postes?: Record<string, number>;
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

/**
 * La santé d'un agent, la pire d'abord : silencieux, en panne, écart de version, des soucis sur la période (tours en échec
 * ou autres soucis du journal), en bonne santé. « installation » : hors Cloudflare, suivie par son pilote, hors relevé.
 */
export type Sante = "silencieux" | "panne" | "ecart" | "soucis" | "ok" | "installation";
const ORDRE: Record<Sante, number> = { silencieux: 4, panne: 3, ecart: 2, soucis: 1, ok: 0, installation: 0 };

/** Les soucis du journal du noyau que le relevé compte (noyau/stockage.py, Journal.ALERTES), hors tours en échec. */
export const SOUCIS_DU_JOURNAL: readonly string[] = [
  "envoi_refuse", "envoi_echec", "plafond", "rappel_echec", "voix_echec", "vocal_illisible", "message_ancien", "reponse_lente",
];

/** Les soucis de la période, les plus nombreux d'abord : les tours en échec et ceux du journal, additionnés sur les jours. */
export function soucisDe(c: ClientReleve): { genre: string; nombre: number }[] {
  const n = new Map<string, number>();
  if (c.totaux.tours_en_echec > 0) n.set("tour_echec", c.totaux.tours_en_echec);
  for (const j of Object.values(c.jours)) {
    for (const g of SOUCIS_DU_JOURNAL) {
      const v = j.journal?.[g]?.nombre ?? 0;
      if (v > 0) n.set(g, (n.get(g) ?? 0) + v);
    }
  }
  return [...n.entries()].map(([genre, nombre]) => ({ genre, nombre })).sort((x, y) => y.nombre - x.nombre || x.genre.localeCompare(y.genre));
}

export function santeDe(c: ClientReleve): Sante {
  if (c.silencieux) return "silencieux";
  if (c.etat?.pannes_en_cours?.length) return "panne";
  if (c.ecart) return "ecart";
  if (soucisDe(c).length) return "soucis";
  return "ok";
}

export type LigneSante = {
  client: string;
  entreprise: string | null;
  sante: Sante;
  /** Les soucis de la période (tours en échec, envois refusés, plafond…), dits à côté de la santé. */
  soucis: { genre: string; nombre: number }[];
  /** Sans relevé (installation hors Cloudflare, client absent de l'annuaire) : ses chiffres sont inconnus ici. */
  horsReleve?: true;
  tours: number;
  echecs: number;
  secours: number;
  /** Le temps moyen jusqu'à la réponse, en secondes, sur la période ; null sans réponse mesurée. */
  reponse: number | null;
  /** Le cas lent (95 % des réponses en dessous) du pire jour de la période, en secondes ; null sans mesure. */
  reponseLente: number | null;
  releveLe: number | null;
  cout?: number;
};

export type VueReleves = {
  /** personnesParJour : les personnes de chaque jour, en moyenne sur les jours relevés (une personne revient d'un jour à l'autre). */
  tuiles: { enService: number; aSurveiller: number; silencieux: number; tours: number; echecs: number; personnesParJour: number;
    cout?: { devise: string; total: number } };
  lignes: LigneSante[];
  sansTarif: string[];
  /** Jour par jour, tous les clients du périmètre ensemble : tours, et coût avec couts.voir. */
  parJour: { jour: string; tours: number; cout: number }[];
  /** Les outils de tous les clients du périmètre sur la période, les plus appelés d'abord ; dureeMoyenne en secondes. */
  outils: { nom: string; appels: number; echecs: number; dureeMoyenne: number | null }[];
};

/** Le cas lent du pire jour : des centiles ne s'additionnent pas d'un jour à l'autre. */
function reponseLente(jours: JourReleve[]): number | null {
  const v = jours.map((j) => j.delais?.reponse?.p95).filter((x): x is number => typeof x === "number");
  return v.length ? Math.max(...v) : null;
}

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
  const lignes: LigneSante[] = actifs.map((c) => ({
      client: c.id,
      entreprise: c.entreprise,
      sante: santeDe(c),
      soucis: soucisDe(c),
      tours: c.totaux.tours,
      echecs: c.totaux.tours_en_echec,
      secours: c.totaux.secours,
      reponse: reponseMoyenne(Object.values(c.jours)),
      reponseLente: reponseLente(Object.values(c.jours)),
      releveLe: c.releve_le,
      ...(voitCouts ? { cout: c.totaux.cout } : {}),
    }));
  trier(lignes);
  const jours = new Map<string, { tours: number; cout: number; personnes: number }>();
  const outils = new Map<string, OutilJour>();
  for (const c of actifs) {
    for (const [jour, j] of Object.entries(c.jours)) {
      for (const [nom, o] of Object.entries(j.outils ?? {})) {
        const e = outils.get(nom) ?? { appels: 0, echecs: 0, duree: 0, mesures: 0 };
        e.appels += o.appels;
        e.echecs += o.echecs;
        e.duree += o.duree;
        e.mesures += o.mesures;
        outils.set(nom, e);
      }
      const t = jours.get(jour) ?? { tours: 0, cout: 0, personnes: 0 };
      t.tours += j.tours;
      t.personnes += j.personnes;
      if (voitCouts) t.cout += j.cout ?? 0;
      jours.set(jour, t);
    }
  }
  const tuiles: VueReleves["tuiles"] = {
    enService: actifs.length,
    aSurveiller: lignes.filter((l) => ORDRE[l.sante] > 0).length,
    silencieux: lignes.filter((l) => l.sante === "silencieux").length,
    tours: lignes.reduce((n, l) => n + l.tours, 0),
    echecs: lignes.reduce((n, l) => n + l.echecs, 0),
    personnesParJour: jours.size ? Math.round([...jours.values()].reduce((n, t) => n + t.personnes, 0) / jours.size) : 0,
  };
  if (voitCouts) tuiles.cout = { devise: r.devise, total: arrondi(actifs.reduce((n, c) => n + c.totaux.cout, 0)) };
  return {
    tuiles,
    lignes,
    sansTarif: voitCouts ? [...new Set(actifs.flatMap((c) => c.totaux.sans_tarif))].sort() : [],
    parJour: [...jours.entries()].sort(([x], [y]) => x.localeCompare(y)).map(([jour, t]) => ({ jour, tours: t.tours, cout: arrondi(t.cout) })),
    outils: [...outils.entries()]
      .map(([nom, o]) => ({ nom, appels: o.appels, echecs: o.echecs, dureeMoyenne: o.mesures ? Math.round((o.duree / o.mesures) * 100) / 100 : null }))
      .sort((x, y) => y.appels - x.appels || x.nom.localeCompare(y.nom)),
  };
}

const trier = (l: LigneSante[]) => l.sort((x, y) => ORDRE[y.sante] - ORDRE[x.sante] || y.tours - x.tours || x.client.localeCompare(y.client));

/**
 * Les clients en service que le relevé ne porte pas, ajoutés à la vue : une installation hors Cloudflare (suivie par son
 * pilote : silencieuse, révoquée, en écart, sinon dite à part), ou un client absent de l'annuaire de la porte (une mise en
 * service interrompue : un écart). Sans eux, la vue d'ensemble les croirait inexistants.
 */
export function completer(v: VueReleves, r: Releves, clients: readonly ClientAtelier[], a: Acces): VueReleves {
  const releves = new Set(r.clients.filter((c) => c.actif).map((c) => c.id));
  const manquants: LigneSante[] = filtrerClients(a, clients)
    .filter((c) => c.version_en_service != null && !releves.has(c.id))
    .map((c) => {
      const i = c.installation;
      const sante: Sante = !i ? "ecart" : i.revoquee != null ? "panne" : i.silencieuse ? "silencieux" : i.ecart === true ? "ecart" : "installation";
      return { client: c.id, entreprise: c.entreprise, sante, soucis: [], horsReleve: true, tours: 0, echecs: 0, secours: 0, reponse: null,
        reponseLente: null, releveLe: null };
    });
  if (!manquants.length) return v;
  const lignes = trier([...v.lignes, ...manquants]);
  const aSurveiller = (l: LigneSante) => ORDRE[l.sante] > 0;
  return { ...v, lignes, tuiles: { ...v.tuiles, enService: lignes.length, aSurveiller: lignes.filter(aSurveiller).length,
    silencieux: lignes.filter((l) => l.sante === "silencieux").length } };
}
