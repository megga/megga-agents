import { Refus } from "@/lib/agents";
import { filtrerClients, peut, type Acces } from "./acces";
import type { Alerte, ClientAtelier, Jours, Lecteur, Suivi } from "./atelier";
import { TA } from "./textes";

// Le suivi des clients du moteur, en fonctions pures (le lecteur de l'atelier est injecté) : la période, les soucis en
// cours et leur gravité, l'état d'un client, les coûts retirés sans couts.voir, la lecture de tous les clients du
// périmètre, quelques-uns à la fois, et la vue d'ensemble. Le périmètre filtre la liste avant toute lecture et tout calcul.

/** Les états de l'instant : en cours tant qu'ils durent (l'atelier les calcule au moment de la lecture). */
export const GENRES_DE_L_INSTANT: readonly string[] = [
  "ecart",
  "porte_injoignable",
  "conteneur_injoignable",
  "installation_silencieuse",
  "installation_revoquee",
  "installation_absente",
  "agent_en_panne",
  "licence_expiree",
  "licence_hors_delai",
];

/** Les genres d'alertes du moteur (noyau/stockage.py, porte/src/agent.js, atelier/pilotage.py). */
export const GENRES_CONNUS: readonly string[] = [
  ...GENRES_DE_L_INSTANT,
  "tour_echec",
  "envoi_echec",
  "vocal_illisible",
  "voix_echec",
  "rappel_echec",
  "mise_a_jour_bloquee",
  "envoi_refuse",
  "message_ancien",
  "plafond",
  "conteneur_demarrage",
  "conteneur_transmission",
  "conteneur_rappels",
  "ordre_refuse",
  "ordre_echec",
  "ordre_expire",
];

const PERIODES: Record<string, Jours> = { "1": 1, "7": 7, "30": 30 };

/** La période de l'adresse (?jours=) : 1, 7 ou 30 ; autre chose retombe sur 7, sans erreur ni appel refusé à l'atelier. */
export function joursDe(v: string | string[] | undefined): Jours {
  const s = Array.isArray(v) ? v[0] : v;
  return (s !== undefined && Object.hasOwn(PERIODES, s) && PERIODES[s]) || 7;
}

/** En cours : une panne de conteneur non résolue, ou un état de l'instant. Le reste est un fait passé, sans état. */
export function estEnCours(a: Alerte): boolean {
  return (a.genre.startsWith("conteneur_") && a.resolue == null) || GENRES_DE_L_INSTANT.includes(a.genre);
}

export function texteGenre(genre: string): string {
  return Object.hasOwn(TA.genres, genre) ? TA.genres[genre] : TA.genreInconnu(genre);
}

export type Souci = { client: string; genre: string; enCours: boolean; quand: number };

export function soucis(client: string, alertes: Alerte[]): Souci[] {
  return alertes.map((a) => ({ client, genre: a.genre, enCours: estEnCours(a), quand: a.quand }));
}

// À TRANCHER PAR THOMAS : l'ordre de gravité des soucis dans « À surveiller ».
// Provisoire : un souci en cours (2) avant un fait passé (1). À décider : une panne de conteneur avant un écart ?
// un plafond atteint avant un tour en échec ? un souci récent avant un ancien ?
export function gravite(s: Souci): number {
  return s.enCours ? 2 : 1;
}

/** Les clients qui ont un souci, le plus grave d'abord : la plus forte gravité, puis le nombre de soucis, puis l'identifiant. */
export function classerASurveiller(l: { client: string; soucis: Souci[] }[]): { client: string; soucis: Souci[] }[] {
  const pire = (x: { soucis: Souci[] }) => Math.max(...x.soucis.map(gravite));
  return l
    .filter((x) => x.soucis.length > 0)
    .sort((a, b) => pire(b) - pire(a) || b.soucis.length - a.soucis.length || a.client.localeCompare(b.client));
}

export type EtatClient = { service: "en_service" | "jamais"; ecart: boolean; tenuParMegga: boolean; conteneur: "demarre" | "arrete" | "inconnu" };

export function etatClient(c: ClientAtelier): EtatClient {
  const demarre = c.annuaire?.conteneur?.demarre;
  return {
    service: c.version_en_service == null ? "jamais" : "en_service",
    ecart: c.ecart === true,
    tenuParMegga: c.gere_par_megga,
    conteneur: demarre === true ? "demarre" : demarre === false ? "arrete" : "inconnu",
  };
}

/** La réponse de l'atelier sans ses coûts pour qui n'a pas couts.voir (il les porte dès que le jeton est celui de MEGGA). */
export function sansCouts<T extends { couts?: unknown }>(r: T, a: Acces): T {
  if (peut(a, "couts.voir")) return r;
  const reste = { ...r };
  delete reste.couts;
  return reste;
}

export type LectureClient = { client: ClientAtelier; suivi?: Suivi; alertes?: Alerte[]; erreur?: string };

/** Un client : son suivi, puis ses alertes ; s'il ne répond pas, il est injoignable (sa phrase), sans rien d'autre. */
async function lireUn(a: Acces, jours: Jours, l: Lecteur, client: ClientAtelier): Promise<LectureClient> {
  try {
    const suivi = sansCouts(await l.suivi(client.id, jours), a);
    const { alertes } = await l.alertes(client.id, jours);
    return { client, suivi, alertes };
  } catch (e) {
    if (!(e instanceof Refus)) console.error("suivi de l'admin :", e);
    return { client, erreur: e instanceof Refus ? e.message : TA.erreurInterne };
  }
}

/**
 * Les clients du périmètre, chacun lu (suivi et alertes) par au plus `parallele` lectures en même temps ; un client hors
 * périmètre n'est jamais lu. porte : la porte a répondu pour la liste.
 */
export async function lireTout(a: Acces, jours: Jours, l: Lecteur, parallele = 4): Promise<{ lectures: LectureClient[]; porte: boolean }> {
  const { clients, porte } = await l.clients();
  const visibles = filtrerClients(a, clients);
  const lectures: LectureClient[] = new Array(visibles.length);
  let suivant = 0;
  async function lecteur() {
    while (suivant < visibles.length) {
      const i = suivant++;
      lectures[i] = await lireUn(a, jours, l, visibles[i]);
    }
  }
  await Promise.all(Array.from({ length: Math.min(parallele, visibles.length) }, lecteur));
  return { lectures, porte };
}

export type VueEnsemble = {
  tuiles: {
    enService: number;
    soucisEnCours: number;
    tours: number;
    personnes: number;
    cout?: { devise: string; total: number; sansTarif: string[] };
  };
  aSurveiller: { client: string; soucis: Souci[] }[];
  injoignables: string[];
  activite: { client: string; entreprise: string | null; tours: number; personnes: number; echecs: number; secours: number; cout?: number }[];
};

type CoutsLus = { devise: string; total: number; sans_tarif: string[] };

/** Les coûts d'une lecture, s'ils sont lisibles et que le membre peut les voir ; sinon rien. */
function coutsDe(l: LectureClient, a: Acces): CoutsLus | undefined {
  const c = l.suivi?.couts;
  return peut(a, "couts.voir") && c && "total" in c ? c : undefined;
}

/** La vue d'ensemble des lectures (déjà bornées au périmètre) ; les coûts seulement avec couts.voir. */
export function agreger(lectures: LectureClient[], a: Acces): VueEnsemble {
  const lues = lectures.filter((l): l is LectureClient & { suivi: Suivi } => !!l.suivi && !l.erreur);
  const somme = (f: (l: LectureClient & { suivi: Suivi }) => number) => lues.reduce((n, l) => n + f(l), 0);
  const parClient = lues.map((l) => ({ client: l.client.id, soucis: soucis(l.client.id, l.alertes ?? []) }));
  const couts = lues.map((l) => coutsDe(l, a)).filter((c): c is CoutsLus => !!c);
  const tuiles: VueEnsemble["tuiles"] = {
    enService: lectures.filter((l) => l.client.version_en_service != null).length,
    soucisEnCours: parClient.reduce((n, x) => n + x.soucis.filter((s) => s.enCours).length, 0),
    tours: somme((l) => l.suivi.activite.tours),
    personnes: somme((l) => l.suivi.activite.personnes),
  };
  if (couts.length) {
    tuiles.cout = {
      devise: couts[0].devise,
      total: Math.round(couts.reduce((n, c) => n + c.total, 0) * 10_000) / 10_000,
      sansTarif: [...new Set(couts.flatMap((c) => c.sans_tarif))].sort(),
    };
  }
  return {
    tuiles,
    aSurveiller: classerASurveiller(parClient),
    injoignables: lectures.filter((l) => l.erreur).map((l) => l.client.id),
    activite: lues.map((l) => {
      const c = coutsDe(l, a);
      const x = l.suivi.activite;
      return { client: l.client.id, entreprise: l.client.entreprise, tours: x.tours, personnes: x.personnes, echecs: x.tours_en_echec,
        secours: x.secours, ...(c ? { cout: c.total } : {}) };
    }),
  };
}

/** Les alertes, les soucis en cours d'abord ; puis la plus récente d'abord, ou par client, ou par genre (dit en clair). */
export function trierAlertes<T extends Alerte & { client: string }>(l: T[], tri: "quand" | "client" | "genre"): T[] {
  const ordre = (a: T, b: T) =>
    tri === "client" ? a.client.localeCompare(b.client) : tri === "genre" ? texteGenre(a.genre).localeCompare(texteGenre(b.genre), "fr") : 0;
  return [...l].sort((a, b) => Number(estEnCours(b)) - Number(estEnCours(a)) || ordre(a, b) || b.quand - a.quand);
}
