import type { DatabaseSync } from "node:sqlite";
import { lister, Refus, type Agent } from "@/lib/agents";
import { auth } from "@/lib/auth";
import { peutSuspendre, type Acces } from "./acces";
import type { Jours } from "./atelier";
import { estObjet } from "./champs";
import { enCours, membreEnCours } from "./membres";
import { TA } from "./textes";
import { joursUtc, messagesDepuis, messagesParJour } from "./usage";

// Les comptes de la console (la table user de Better Auth et leurs agents), leur fiche, les totaux de la vue d'ensemble ;
// suspendre, réactiver, déconnecter partout. Le bannissement est celui de l'extension admin de Better Auth (auth.ts), écrit par
// son adaptateur interne : ses routes HTTP restent fermées. Jamais une adresse IP ni un jeton de session hors d'ici.

export type CompteConsole = {
  id: string;
  entreprise: string;
  courriel: string;
  inscritLe: string;
  derniereConnexion: string | null;
  agents: number;
  messages30j: number;
  suspendu: boolean;
  motif: string | null;
  membre: boolean;
};

/** Ce que les gestes écrivent par Better Auth : son adaptateur interne, remplaçable dans les essais. */
export type AdaptateurComptes = {
  updateUser(id: string, champs: Record<string, unknown>): Promise<unknown>;
  deleteUserSessions(id: string): Promise<unknown>;
};

const MOTIF_MAX = 200;

type Ligne = {
  id: string;
  name: string | null;
  email: string;
  createdAt: string;
  banned: number | null;
  banReason: string | null;
  derniere: string | null;
  role_membre: string | null;
  fin_acces: string | null;
  agents: number;
  messages: number;
};

/** Le premier des 30 derniers jours UTC : la période des messages d'un compte. */
const depuis30j = (maintenant: Date) => joursUtc(30, maintenant)[0];

const CHOIX = `SELECT u.id, u.name, u.email, u.createdAt, u.banned, u.banReason, c.derniere, m.role AS role_membre, m.fin_acces,
  (SELECT COUNT(*) FROM agent a WHERE a.utilisateur = u.id) AS agents,
  (SELECT COALESCE(SUM(ua.messages), 0) FROM usage_agent ua JOIN agent a ON a.id = ua.agent WHERE a.utilisateur = u.id AND ua.jour >= ?) AS messages
  FROM "user" u LEFT JOIN compte_connexion c ON c.utilisateur = u.id LEFT JOIN admin_membre m ON m.utilisateur = u.id`;

function versCompte(l: Ligne, maintenant: Date): CompteConsole {
  return {
    id: l.id,
    entreprise: l.name ?? "",
    courriel: l.email,
    inscritLe: l.createdAt,
    derniereConnexion: l.derniere,
    agents: l.agents,
    messages30j: l.messages,
    suspendu: !!l.banned,
    motif: l.banned ? l.banReason : null,
    membre: l.role_membre !== null && enCours(l.fin_acces, maintenant),
  };
}

/** Tous les comptes de la console, l'inscription la plus récente d'abord. */
export function listerComptes(db: DatabaseSync, maintenant = new Date()): CompteConsole[] {
  const lignes = db.prepare(`${CHOIX} ORDER BY u.createdAt DESC, u.rowid DESC`).all(depuis30j(maintenant)) as Ligne[];
  return lignes.map((l) => versCompte(l, maintenant));
}

/** La fiche d'un compte : ses agents et leurs messages sur 30 jours, ses sessions ouvertes (sans adresse IP ni jeton). */
export function ficheCompte(db: DatabaseSync, id: string, maintenant = new Date()): {
  compte: CompteConsole;
  agents: (Agent & { messages30j: number })[];
  sessions: { creeLe: string; expireLe: string; appareil: string | null }[];
} | undefined {
  const l = db.prepare(`${CHOIX} WHERE u.id = ?`).get(depuis30j(maintenant), id) as Ligne | undefined;
  if (!l) return undefined;
  const agents = lister(db, id);
  const messages = messagesDepuis(db, agents.map((a) => a.id), depuis30j(maintenant));
  const sessions = db
    .prepare("SELECT createdAt, expiresAt, userAgent FROM session WHERE userId = ? AND expiresAt > ? ORDER BY createdAt DESC")
    .all(id, maintenant.toISOString()) as { createdAt: string; expiresAt: string; userAgent: string | null }[];
  return {
    compte: versCompte(l, maintenant),
    agents: agents.map((a) => ({ ...a, messages30j: messages[a.id] ?? 0 })),
    sessions: sessions.map((s) => ({ creeLe: s.createdAt, expireLe: s.expiresAt, appareil: s.userAgent || null })),
  };
}

/**
 * Le membre a-t-il la main sur ce compte (suspendre, réactiver, déconnecter) ? La seule écriture de la règle pour les gestes
 * et pour l'écran : peutSuspendre, d'après le membre en cours que ce compte est peut-être.
 */
export function peutAgirSur(db: DatabaseSync, a: Acces, id: string, maintenant = new Date()): boolean {
  const m = membreEnCours(db, id, maintenant);
  return peutSuspendre(a, { id, membre: m ? { role: m.role } : null });
}

/** Le compte visé : inconnu, 404 ; hors de la main du membre, 403. */
function exigerCompte(db: DatabaseSync, a: Acces, id: string): void {
  if (!db.prepare('SELECT 1 FROM "user" WHERE id = ?').get(id)) throw new Refus(404, TA.compteInconnu);
  if (!peutAgirSur(db, a, id)) throw new Refus(403, TA.suspensionInterdite);
}

/** Le motif d'une suspension : un texte, sans les espaces autour, de 1 à 200 caractères. */
function lireMotif(corps: unknown): string {
  const m = estObjet(corps) && typeof corps.motif === "string" ? corps.motif.trim() : "";
  if (!m || [...m].length > MOTIF_MAX) throw new Refus(400, TA.motifManquant);
  return m;
}

/** L'adaptateur interne de Better Auth (celui de la console). */
export async function adaptateurComptes(): Promise<AdaptateurComptes> {
  return (await auth().$context).internalAdapter;
}

/** Corps : { motif }. Le compte ne se connecte plus (l'extension refuse toute nouvelle session) et perd ses sessions. */
export async function suspendre(db: DatabaseSync, a: Acces, id: string, corps: unknown, ad: AdaptateurComptes): Promise<void> {
  exigerCompte(db, a, id);
  const motif = lireMotif(corps);
  await ad.updateUser(id, { banned: true, banReason: motif, banExpires: null });
  await ad.deleteUserSessions(id);
}

export async function reactiver(db: DatabaseSync, a: Acces, id: string, ad: AdaptateurComptes): Promise<void> {
  exigerCompte(db, a, id);
  await ad.updateUser(id, { banned: false, banReason: null, banExpires: null });
}

/** Ferme toutes ses sessions, tout de suite ; il peut se reconnecter. */
export async function deconnecter(db: DatabaseSync, a: Acces, id: string, ad: AdaptateurComptes): Promise<void> {
  exigerCompte(db, a, id);
  await ad.deleteUserSessions(id);
}

/** La console sur la vue d'ensemble : comptes et agents en tout ; messages et inscriptions jour par jour (jours UTC). */
export function totauxConsole(db: DatabaseSync, jours: Jours, maintenant = new Date()): {
  comptes: number;
  agents: number;
  messages: number;
  parJour: { jour: string; inscriptions: number; messages: number }[];
} {
  const compter = (sql: string) => (db.prepare(sql).get() as { n: number }).n;
  const messages = messagesParJour(db, jours, maintenant);
  const inscrits = db
    .prepare('SELECT substr(createdAt, 1, 10) AS jour, COUNT(*) AS n FROM "user" WHERE substr(createdAt, 1, 10) BETWEEN ? AND ? GROUP BY jour')
    .all(messages[0].jour, messages[messages.length - 1].jour) as { jour: string; n: number }[];
  const parJour = new Map(inscrits.map((i) => [i.jour, i.n]));
  return {
    comptes: compter('SELECT COUNT(*) AS n FROM "user"'),
    agents: compter("SELECT COUNT(*) AS n FROM agent"),
    messages: messages.reduce((s, j) => s + j.messages, 0),
    parJour: messages.map((j) => ({ jour: j.jour, inscriptions: parJour.get(j.jour) ?? 0, messages: j.messages })),
  };
}
