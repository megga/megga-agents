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

export type Souci = { client: string; genre: string; enCours: boolean; quand: number | null };

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

/** La zone d'un client : celle de sa version en service, sinon de sa dernière version (comme zone_de, atelier/app.py). */
export function zoneClient(enService: Record<string, unknown> | null | undefined, derniere: Record<string, unknown> | null | undefined): string | null {
  for (const config of [enService, derniere]) if (typeof config?.zone === "string") return config.zone;
  return null;
}

/** Hors Cloudflare : une zone que la porte ne sert pas (le catalogue, zones_porte). Zone ou catalogue inconnus : non. */
export function horsCloudflare(zone: string | null, zonesPorte: readonly string[] | null): boolean {
  return zone !== null && zonesPorte !== null && !zonesPorte.includes(zone);
}

/** Une personne, comme le moteur la nomme (noyau/suivi.py, PERSONNE) : un numéro, ou api:<logiciel>:<identifiant>. */
const PERSONNE = /^(\+?\d{6,20}|api:[a-z0-9][a-z0-9-]{0,19}:(?=[^:]*[A-Za-z])[A-Za-z0-9._-]{1,40})$/;

/**
 * La personne d'une adresse (le fil d'une conversation), décodée une seule fois ; mal formée, rien : une adresse tapée à la
 * main ne va pas jusqu'à l'atelier (« .. » y remonterait d'un dossier).
 */
export function personneDe(brut: string): string | null {
  let p: string;
  try {
    p = decodeURIComponent(brut);
  } catch {
    return null;
  }
  return PERSONNE.test(p) ? p : null;
}

export type EtatClient ={ service: "en_service" | "jamais"; ecart: boolean; tenuParMegga: boolean; conteneur: "demarre" | "arrete" | "inconnu" };

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

/** Les postes de l'atelier qui ne sont pas des modèles (atelier/couts.py) : leurs tarifs se règlent à part. */
const POSTES_HORS_MODELES: readonly string[] = ["voix", "ecoute"];

/**
 * Les modèles vus dans l'activité sans tarif (l'écran Tarifs les propose à l'ajout) : l'union triée des sans_tarif des
 * lectures, sans la voix ni l'écoute. Des coûts illisibles ({ erreur }) ou absents (sans couts.voir) n'en donnent aucun.
 */
export function modelesSansTarif(lectures: LectureClient[]): string[] {
  const vus = lectures.flatMap((l) => {
    const c = l.suivi?.couts;
    return c && "sans_tarif" in c ? c.sans_tarif : [];
  });
  return [...new Set(vus)].filter((m) => !POSTES_HORS_MODELES.includes(m)).sort();
}

/** La phrase d'un refus de lecture ; une erreur inattendue part à console.error. */
function phrase(e: unknown): string {
  if (e instanceof Refus) return e.message;
  console.error("suivi de l'admin :", e);
  return TA.erreurInterne;
}

/** Ce qu'une lecture demande à l'atelier : sans suivi, les seules alertes (l'écran Alertes). */
type Lire = Pick<Lecteur, "clients" | "alertes"> & { suivi?: Lecteur["suivi"] };

/**
 * Un client, une lecture à la fois : son suivi (si on le lit), puis ses alertes, lues même si le suivi n'a pas répondu (l'atelier
 * y dit alors la panne : conteneur ou porte injoignable). Une lecture qui échoue rend le client injoignable (sa phrase).
 * Jamais mis en service : rien à lire (ni conteneur ni activité ; l'atelier y verrait une fausse panne).
 */
async function lireUn(a: Acces, jours: Jours, l: Lire, client: ClientAtelier): Promise<LectureClient> {
  const lecture: LectureClient = { client };
  if (client.version_en_service == null) return lecture;
  if (l.suivi) {
    try {
      lecture.suivi = sansCouts(await l.suivi(client.id, jours), a);
    } catch (e) {
      lecture.erreur = phrase(e);
    }
  }
  try {
    lecture.alertes = (await l.alertes(client.id, jours)).alertes;
  } catch (e) {
    lecture.erreur ??= phrase(e);
  }
  return lecture;
}

/** Les clients du périmètre (un client hors périmètre n'est jamais lu), au plus `parallele` en même temps. */
async function lireClients(a: Acces, jours: Jours, l: Lire, parallele: number) {
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

/** Le suivi et les alertes des clients du périmètre (la vue d'ensemble). porte : la porte a répondu pour la liste. */
export function lireTout(a: Acces, jours: Jours, l: Lecteur, parallele = 4): Promise<{ lectures: LectureClient[]; porte: boolean }> {
  return lireClients(a, jours, l, parallele);
}

/** Les seules alertes des clients du périmètre (l'écran Alertes). */
export function lireAlertes(a: Acces, jours: Jours, l: Pick<Lecteur, "clients" | "alertes">, parallele = 4): Promise<{ lectures: LectureClient[]; porte: boolean }> {
  return lireClients(a, jours, { clients: l.clients, alertes: l.alertes }, parallele);
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

/**
 * La vue d'ensemble des lectures (déjà bornées au périmètre) : l'activité des clients dont le suivi a répondu, les soucis de
 * tous ceux dont les alertes ont répondu (un client injoignable compris) ; les coûts seulement avec couts.voir.
 */
export function agreger(lectures: LectureClient[], a: Acces): VueEnsemble {
  const lues = lectures.filter((l): l is LectureClient & { suivi: Suivi } => !!l.suivi);
  const somme = (f: (l: LectureClient & { suivi: Suivi }) => number) => lues.reduce((n, l) => n + f(l), 0);
  const parClient = lectures.filter((l) => l.alertes).map((l) => ({ client: l.client.id, soucis: soucis(l.client.id, l.alertes ?? []) }));
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

/**
 * Les alertes, les soucis en cours d'abord ; puis la plus récente d'abord (un instant inconnu en dernier), ou par client (dans
 * l'ordre du nom montré, nom, sinon l'identifiant), ou par genre (dit en clair).
 */
export function trierAlertes<T extends Alerte & { client: string; nom?: string }>(l: T[], tri: "quand" | "client" | "genre"): T[] {
  const nom = (x: T) => x.nom ?? x.client;
  const ordre = (a: T, b: T) =>
    tri === "client" ? nom(a).localeCompare(nom(b), "fr") || a.client.localeCompare(b.client)
    : tri === "genre" ? texteGenre(a.genre).localeCompare(texteGenre(b.genre), "fr") : 0;
  return [...l].sort((a, b) => Number(estEnCours(b)) - Number(estEnCours(a)) || ordre(a, b) || (b.quand ?? -Infinity) - (a.quand ?? -Infinity) || 0);
}
