import type { DatabaseSync } from "node:sqlite";
import { lister, Refus, type Agent } from "@/lib/agents";
import { auth } from "@/lib/auth";
import { peutSuspendre, type Acces } from "./acces";
import type { Jours } from "./atelier";
import { estObjet } from "./champs";
import { enCours, membreEnCours } from "./membres";
import { TA } from "./textes";
import { jourZurich, joursZurich, messagesDepuis, messagesParJour } from "./usage";

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

/** Le premier des 30 derniers jours de Zurich (aujourd'hui compris) : la période des messages d'un compte. */
const depuis30j = (maintenant: Date) => joursZurich(30, maintenant)[0];

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

export const COMPTES_PAR_PAGE = 50;
const RECHERCHE_MAX = 100;

/** La recherche (dans l'entreprise ou le courriel) et la page de la liste des comptes. */
export type FiltresComptes = { q?: string; page: number };

/** Les filtres tels que l'adresse les donne (?q=, ?page=) ; une page mal formée retombe sur 1, une recherche vide n'en est pas une. */
export function filtresComptesDe(p: Record<string, string | string[] | undefined>): FiltresComptes {
  const lire = (cle: string) => {
    const v = p[cle];
    return (Array.isArray(v) ? v[0] : v)?.trim() || undefined;
  };
  const page = Number(lire("page"));
  const q = lire("q")?.slice(0, RECHERCHE_MAX);
  return { page: Number.isSafeInteger(page) && page >= 1 ? page : 1, ...(q ? { q } : {}) };
}

/** Une recherche prise à la lettre dans un LIKE : \, % et _ échappés. */
const enLike = (q: string) => `%${q.replace(/[\\%_]/g, (c) => "\\" + c)}%`;

/**
 * Les comptes de la console, l'inscription la plus récente d'abord, par pages de COMPTES_PAR_PAGE ; la recherche et la page
 * se font dans le SQL. Une page demandée trop loin est ramenée à la dernière (page).
 */
export function listerComptes(db: DatabaseSync, f: FiltresComptes = { page: 1 }, maintenant = new Date()): {
  comptes: CompteConsole[];
  pages: number;
  page: number;
} {
  const ou = f.q ? `WHERE (u.name LIKE ? ESCAPE '\\' OR u.email LIKE ? ESCAPE '\\')` : "";
  const valeurs = f.q ? [enLike(f.q), enLike(f.q)] : [];
  const total = (db.prepare(`SELECT COUNT(*) AS n FROM "user" u ${ou}`).get(...valeurs) as { n: number }).n;
  const pages = Math.max(1, Math.ceil(total / COMPTES_PAR_PAGE));
  const page = Math.min(f.page, pages);
  const lignes = db
    .prepare(`${CHOIX} ${ou} ORDER BY u.createdAt DESC, u.rowid DESC LIMIT ? OFFSET ?`)
    .all(depuis30j(maintenant), ...valeurs, COMPTES_PAR_PAGE, (page - 1) * COMPTES_PAR_PAGE) as Ligne[];
  return { comptes: lignes.map((l) => versCompte(l, maintenant)), pages, page };
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

/** Ce que le journal garde d'une suspension : son motif, coupé à 200 caractères ; rien d'autre du corps. */
export function detailSuspension(corps: unknown): { motif: string | null } {
  const m = estObjet(corps) && typeof corps.motif === "string" ? corps.motif.trim() : null;
  return { motif: m === null ? null : [...m].slice(0, MOTIF_MAX).join("") };
}

/** L'adaptateur interne de Better Auth (celui de la console). */
export async function adaptateurComptes(): Promise<AdaptateurComptes> {
  return (await auth().$context).internalAdapter;
}

/**
 * Corps : { motif }. Le compte ne se connecte plus (l'extension refuse toute nouvelle session) et perd ses sessions. Le
 * bannissement écrit (s'il échoue, l'erreur remonte : rien n'est fait), un effacement des sessions en échec est réessayé une
 * fois. sessionsRestent : le compte est suspendu, mais ses sessions restent après ces deux essais (« Déconnecter partout »).
 */
export async function suspendre(db: DatabaseSync, a: Acces, id: string, corps: unknown, ad: AdaptateurComptes): Promise<{ sessionsRestent: boolean }> {
  exigerCompte(db, a, id);
  const motif = lireMotif(corps);
  await ad.updateUser(id, { banned: true, banReason: motif, banExpires: null });
  for (let essai = 1; essai <= 2; essai++) {
    try {
      await ad.deleteUserSessions(id);
      return { sessionsRestent: false };
    } catch (e) {
      console.error(`suspension : sessions non effacées (essai ${essai}) :`, e);
    }
  }
  return { sessionsRestent: true };
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

/**
 * La console sur la vue d'ensemble : comptes et agents en tout ; messages et inscriptions jour par jour, en jours de Zurich
 * (une inscription à 0 h 30 de Zurich compte ce jour-là). Les comptes inscrits dès la veille UTC du premier jour sont lus,
 * puis rangés par leur jour de Zurich.
 */
export function totauxConsole(db: DatabaseSync, jours: Jours, maintenant = new Date()): {
  comptes: number;
  agents: number;
  messages: number;
  parJour: { jour: string; inscriptions: number; messages: number }[];
} {
  const compter = (sql: string) => (db.prepare(sql).get() as { n: number }).n;
  const messages = messagesParJour(db, jours, maintenant);
  const veille = new Date(Date.parse(`${messages[0].jour}T00:00:00Z`) - 24 * 3600 * 1000).toISOString();
  const inscrits = db.prepare('SELECT createdAt FROM "user" WHERE createdAt >= ?').all(veille) as { createdAt: string }[];
  const parJour = new Map<string, number>();
  for (const i of inscrits) {
    const jour = jourZurich(new Date(i.createdAt));
    parJour.set(jour, (parJour.get(jour) ?? 0) + 1);
  }
  return {
    comptes: compter('SELECT COUNT(*) AS n FROM "user"'),
    agents: compter("SELECT COUNT(*) AS n FROM agent"),
    messages: messages.reduce((s, j) => s + j.messages, 0),
    parJour: messages.map((j) => ({ jour: j.jour, inscriptions: parJour.get(j.jour) ?? 0, messages: j.messages })),
  };
}
