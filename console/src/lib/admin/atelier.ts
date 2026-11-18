import "server-only";
import { Refus } from "@/lib/agents";
import { estChamp, type ChampErreur } from "./champs";
import { TA } from "./textes";

// Le client de l'atelier, côté serveur seulement : il détient le jeton de MEGGA, que le navigateur ne voit jamais.
// Une fonction par route de docs/atelier.md ; ATELIER_URL et ATELIER_JETON se lisent à chaque appel. Les lectures sont
// gardées GARDE_MS en mémoire, avant tout filtre de droits (suivi.ts filtre après) ; toute écriture oublie ce qui était gardé.

export type Jours = 1 | 7 | 30;

/** Un refus de l'atelier : sa phrase, et ses messages champ par champ quand il en donne. */
export class RefusChamps extends Refus {
  constructor(statut: number, message: string, public champs: ChampErreur[] = []) {
    super(statut, message);
  }
}

/** L'attente d'une lecture ; un essai et une mise en service attendent plus (un agent met parfois plus de 30 s à répondre). */
export const ATTENTE_MS = 10_000;
export const ATTENTE_ESSAI_MS = 120_000;
export const ATTENTE_ACTIVER_MS = 60_000;
export const GARDE_MS = 20_000; // lectures gardées en mémoire, avant tout filtre de droits

export type ClientAtelier = {
  id: string;
  nom_agent: string | null;
  entreprise: string | null;
  version_en_service: number | null;
  derniere_version: number | null;
  gere_par_megga: boolean;
  ecart?: boolean | null;
  annuaire?: { version?: number; conteneur?: { demarre: boolean } } | null;
  installation?: Record<string, unknown>;
};
export type Alerte = { quand: number | null; genre: string; detail: string; resolue?: number | null }; // quand : inconnu d'une installation sans relevé
export type Activite = {
  tours: number;
  tours_api: number;
  tours_en_echec: number;
  secours: number;
  personnes: number;
  rappels_en_attente: number;
  modeles: Record<string, { tours: number; entree: number; sortie: number; cache_lecture: number; cache_ecriture: number }>;
  journal: Record<string, { nombre?: number; quantite?: number }>;
};
export type Couts = { devise: string; postes: Record<string, number>; total: number; sans_tarif: string[] } | { erreur: string };
export type Suivi = ClientAtelier & { periode_jours: number; activite: Activite; couts?: Couts };
export type Version = {
  version: number;
  etat: "brouillon" | "publiee";
  auteur: "megga" | "client" | null;
  base: number | null;
  essais: number;
  cree_le: string | null;
  config?: Record<string, unknown>;
};
export type Catalogue = { metiers: Record<string, string[]>; champs_client: string[]; zones: string[]; zones_porte: string[]; modeles: string[] };
export type Tarifs = {
  devise: string;
  modeles: Record<string, { entree: number; sortie: number; cache_lecture: number; cache_ecriture: number }>;
  voix_par_1000_caracteres: number | null;
  par_vocal_entendu: number | null;
};
export type Gabarit = { id: string; titre: string; description: string; metier: string; reglages: Record<string, unknown> };
export type Personne = { personne: string; messages: number; derniere: number | string | null };
export type Message = { quand: number | string; sens: "recu" | "envoye"; genre: string; texte: string };
export type Corps = Record<string, unknown>;

export function atelierBranche(): boolean {
  return !!process.env.ATELIER_URL;
}

/**
 * Un refus de l'atelier : sa phrase (erreur) ; details, seulement s'il est une liste de { champ, message }. Une réponse d'une
 * autre forme (le 422 de FastAPI, un texte) donne une phrase générale. Le jeton de la console refusé (401, 403) est une
 * panne du branchement, pas un refus fait au membre : 502.
 */
export function lireErreur(statut: number, corps: unknown): RefusChamps {
  const s = statut === 401 || statut === 403 ? 502 : statut;
  const c = corps && typeof corps === "object" ? (corps as { erreur?: unknown; details?: unknown }) : null;
  if (!c || typeof c.erreur !== "string" || !c.erreur) return new RefusChamps(s, TA.atelierRefus);
  return new RefusChamps(s, c.erreur, Array.isArray(c.details) ? c.details.filter(estChamp) : []);
}

function adresse(): string {
  const url = process.env.ATELIER_URL;
  if (!url) throw new RefusChamps(503, TA.moteurNonBranche);
  return url.replace(/\/+$/, "") + "/atelier";
}

type Methode = "GET" | "POST" | "PUT" | "DELETE";

/** La trace d'une panne, côté serveur : le nom de l'erreur et sa cause (un code), jamais le jeton ni l'en-tête. */
function noterPanne(e: unknown, delai: boolean): void {
  const cause = e instanceof Error ? (e.cause as { code?: unknown; name?: unknown } | undefined) : undefined;
  const nom = e instanceof Error ? e.name : typeof e;
  const texte = cause ? `${nom} (${String(cause.code ?? cause.name ?? "?")})` : nom;
  const jeton = process.env.ATELIER_JETON;
  console.error(`atelier : ${delai ? "pas de réponse à temps" : "injoignable"},`, jeton ? texte.replaceAll(jeton, "[masqué]") : texte);
}

/**
 * Un appel, borné : la minuterie couvre la réponse et son corps ; un atelier muet donne 504, injoignable 502. Une réponse
 * réussie mais illisible (une page HTML, autre chose qu'un objet JSON) est un refus 502, jamais un succès vide.
 */
async function appel<T>(url: string, methode: Methode, corps?: unknown, attente = ATTENTE_MS): Promise<T> {
  const arret = new AbortController();
  const minuterie = setTimeout(() => arret.abort(), attente);
  try {
    const r = await fetch(url, {
      method: methode,
      headers: { authorization: `Bearer ${process.env.ATELIER_JETON ?? ""}`, ...(corps === undefined ? {} : { "content-type": "application/json" }) },
      body: corps === undefined ? undefined : JSON.stringify(corps),
      signal: arret.signal,
      cache: "no-store",
    });
    if (!r.ok) throw lireErreur(r.status, await r.json().catch(() => null));
    const lu: unknown = await r.json().catch((e: unknown) => {
      if (arret.signal.aborted) throw e;
      throw new RefusChamps(502, TA.atelierRefus);
    });
    if (!lu || typeof lu !== "object") throw new RefusChamps(502, TA.atelierRefus);
    return lu as T;
  } catch (e) {
    if (e instanceof RefusChamps) throw e;
    noterPanne(e, arret.signal.aborted);
    throw new RefusChamps(arret.signal.aborted ? 504 : 502, arret.signal.aborted ? TA.atelierLent : TA.atelierInjoignable);
  } finally {
    clearTimeout(minuterie);
  }
}

const gardees = new Map<string, { quand: number; valeur: Promise<unknown> }>();

/** Oublie toutes les lectures gardées (après une écriture). */
export function oublier(): void {
  gardees.clear();
}

/** Combien de lectures sont gardées (pour les essais). */
export function tailleGarde(): number {
  return gardees.size;
}

/** Une lecture, gardée GARDE_MS : deux lectures rapprochées n'en font qu'une ; un refus n'est pas gardé. */
async function lire<T>(chemin: string): Promise<T> {
  const url = adresse() + chemin;
  const maintenant = Date.now();
  for (const [cle, g] of gardees) if (maintenant - g.quand >= GARDE_MS) gardees.delete(cle); // les périmées s'en vont
  const g = gardees.get(url);
  if (g) return g.valeur as Promise<T>;
  const valeur = appel<T>(url, "GET");
  gardees.set(url, { quand: maintenant, valeur });
  valeur.catch(() => {
    if (gardees.get(url)?.valeur === valeur) gardees.delete(url);
  });
  return valeur;
}

/** Une écriture : jamais gardée, et elle oublie les lectures gardées, réussie ou non. */
async function ecrire<T>(chemin: string, methode: Exclude<Methode, "GET">, corps?: unknown, attente?: number): Promise<T> {
  try {
    return await appel<T>(adresse() + chemin, methode, corps, attente);
  } finally {
    oublier();
  }
}

const c = (id: string) => `/clients/${encodeURIComponent(id)}`;
const v = (id: string, n: number) => `${c(id)}/versions/${encodeURIComponent(String(n))}`;

export const atelier = {
  catalogue: () => lire<Catalogue>("/catalogue"),
  gabarits: () => lire<{ gabarits: Gabarit[] }>("/gabarits"),
  clients: () => lire<{ clients: ClientAtelier[]; porte: boolean }>("/clients"),
  client: (id: string) => lire<ClientAtelier & { config: Corps | null }>(c(id)),
  versions: (id: string) => lire<{ versions: Version[] }>(`${c(id)}/versions`),
  version: (id: string, n: number) => lire<Version>(v(id, n)),
  valider: (id: string, corps: Corps) => ecrire<{ base: number; config: Corps; manques: string[] }>(`${c(id)}/valider`, "POST", corps),
  ajouterVersion: (id: string, corps: Corps) => ecrire<Version & { manques: string[] }>(`${c(id)}/versions`, "POST", corps),
  depuisGabarit: (id: string, corps: Corps) => ecrire<Version & { manques: string[] }>(`${c(id)}/gabarit`, "POST", corps),
  essai: (id: string, n: number, corps: Corps) =>
    ecrire<{ version: number; conversation: string; reponse: string }>(`${v(id, n)}/essai`, "POST", corps, ATTENTE_ESSAI_MS),
  activer: (id: string, n: number, corps: Corps) => ecrire<Corps>(`${v(id, n)}/activer`, "POST", corps, ATTENTE_ACTIVER_MS),
  reprise: (id: string, corps: Corps) => ecrire<{ client: string; gere_par_megga: boolean }>(`${c(id)}/reprise`, "POST", corps),
  creerJeton: (id: string) => ecrire<{ client: string; jeton: string }>(`${c(id)}/jetons`, "POST"),
  retirerJetons: (id: string) => ecrire<{ client: string; retires: number }>(`${c(id)}/jetons`, "DELETE"),
  cles: (id: string) => lire<{ client: string; cles: Corps[] }>(`${c(id)}/cles`),
  creerCle: (id: string, corps: Corps) =>
    ecrire<{ client: string; id: string; logiciel: string; par_minute: number; cle: string }>(`${c(id)}/cles`, "POST", corps),
  retirerCle: (id: string, cle: string) => ecrire<Corps>(`${c(id)}/cles/${encodeURIComponent(cle)}`, "DELETE"),
  suivi: (id: string, jours: Jours) => lire<Suivi>(`${c(id)}/suivi?jours=${jours}`),
  alertes: (id: string, jours: Jours) => lire<{ periode_jours: number; alertes: Alerte[] }>(`${c(id)}/alertes?jours=${jours}`),
  conversations: (id: string) => lire<{ conversations: Personne[] }>(`${c(id)}/conversations`),
  echanges: (id: string, personne: string) =>
    lire<{ personne: string; messages: Message[] }>(`${c(id)}/conversations/${encodeURIComponent(personne)}`),
  installations: () => lire<{ installations: (Corps & { client: string })[]; cle_pilotage: boolean }>("/installations"),
  installation: (id: string) => lire<Corps>(`${c(id)}/installation`),
  enregistrerInstallation: (id: string, corps: Corps) => ecrire<{ client: string; cle: string }>(`${c(id)}/installation`, "PUT", corps),
  revoquerInstallation: (id: string) => ecrire<{ client: string; revoquee: boolean }>(`${c(id)}/installation`, "DELETE"),
  proposerImage: (id: string, corps: Corps) => ecrire<Corps>(`${c(id)}/installation/image`, "POST", corps),
  tarifs: () => lire<Tarifs>("/tarifs"),
  reglerTarifs: (corps: Corps) => ecrire<Tarifs>("/tarifs", "PUT", corps),
  creerClient: (corps: Corps) => ecrire<Version & { client: string }>("/clients", "POST", corps),
};

/** Pour un écran : la réponse, ou le refus de l'atelier (sa phrase, son statut), que l'écran montre au lieu de lever. */
export function ouRefus<T>(lecture: Promise<T>): Promise<T | RefusChamps> {
  return lecture.catch((e: unknown) => {
    if (e instanceof RefusChamps) return e;
    console.error("atelier :", e);
    return new RefusChamps(500, TA.erreurInterne);
  });
}

/** Ce que le suivi lit (suivi.ts, lireTout) : remplaçable dans les essais. */
export type Lecteur = Pick<typeof atelier, "clients" | "suivi" | "alertes">;
