import { Refus } from "@/lib/agents";
import { filtrerClients, peut, type Acces } from "./acces";
import type { Alerte, ClientAtelier, Jours, Lecteur, Suivi } from "./atelier";
import { TA } from "./textes";

// Le suivi des clients du moteur, en fonctions pures (le lecteur de l'atelier est injecté) : la période, les soucis en
// cours, l'état d'un client, les coûts retirés sans couts.voir, la lecture des clients du périmètre, quelques-uns à la
// fois (écrans Alertes et Tarifs). Le périmètre filtre la liste avant toute lecture. La vue d'ensemble lit le relevé
// chiffré (releves.ts).

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
  "reponse_lente",
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

/** La zone d'un client : celle de sa version en service, sinon de sa dernière version (comme zone_de, atelier/app.py). */
export function zoneClient(enService: Record<string, unknown> | null | undefined, derniere: Record<string, unknown> | null | undefined): string | null {
  for (const config of [enService, derniere]) if (typeof config?.zone === "string") return config.zone;
  return null;
}

/** Hors Cloudflare : une zone que la porte ne sert pas (le catalogue, zones_porte). Zone ou catalogue inconnus : non. */
export function horsCloudflare(zone: string | null, zonesPorte: readonly string[] | null): boolean {
  return zone !== null && zonesPorte !== null && !zonesPorte.includes(zone);
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

/** Ce qu'une lecture demande à l'atelier : le suivi et les alertes, les seules alertes (l'écran Alertes) ou les seuls suivis (Tarifs). */
type Lire = Pick<Lecteur, "clients"> & { suivi?: Lecteur["suivi"]; alertes?: Lecteur["alertes"] };

/**
 * Un client, une lecture à la fois : son suivi (si on le lit), puis ses alertes (si on les lit), lues même si le suivi n'a pas
 * répondu (l'atelier y dit alors la panne : conteneur ou porte injoignable). Une lecture qui échoue rend le client injoignable.
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
  if (l.alertes) {
    try {
      lecture.alertes = (await l.alertes(client.id, jours)).alertes;
    } catch (e) {
      lecture.erreur ??= phrase(e);
    }
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

/** Les seuls suivis des clients du périmètre (l'écran Tarifs, pour les modèles vus sans tarif) : aucune alerte lue. */
export function lireSuivis(a: Acces, jours: Jours, l: Pick<Lecteur, "clients" | "suivi">, parallele = 4): Promise<{ lectures: LectureClient[]; porte: boolean }> {
  return lireClients(a, jours, { clients: l.clients, suivi: l.suivi }, parallele);
}

/** Les seules alertes des clients du périmètre (l'écran Alertes). */
export function lireAlertes(a: Acces, jours: Jours, l: Pick<Lecteur, "clients" | "alertes">, parallele = 4): Promise<{ lectures: LectureClient[]; porte: boolean }> {
  return lireClients(a, jours, { clients: l.clients, alertes: l.alertes }, parallele);
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
