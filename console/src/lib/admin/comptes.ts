import type { Base } from "@/lib/donnees/base";
import { lister, Refus, type Agent } from "@/lib/agents";
import { auth } from "@/lib/auth";
import { peutSuspendre, type Acces } from "./acces";
import type { Jours } from "./atelier";
import { estObjet } from "./champs";
import { enCours, membreEnCours } from "./membres";
import { TA } from "./textes";
import { jourZurich, joursZurich, messagesDepuis, messagesParJour } from "./usage";

// Les comptes de la console (la table user de Better Auth et leurs agents), leur fiche, les totaux de la vue d'ensemble ;
// suspendre, réactiver, déconnecter partout. Le bannissement est celui de l'extension admin de Better Auth (auth.ts), ses routes
// HTTP restent fermées : la suspension l'écrit dans une transaction de la console, réactiver et déconnecter par son adaptateur
// interne. Jamais une adresse IP ni un jeton de session hors d'ici.

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
  banned: number | boolean | null; // un entier sous SQLite, un booléen sous Postgres
  banReason: string | null;
  derniere: string | null;
  role_membre: string | null;
  fin_acces: string | null;
  agents: number;
  messages: number;
};

/** Le premier des 30 derniers jours de Zurich (aujourd'hui compris) : la période des messages d'un compte. */
const depuis30j = (maintenant: Date) => joursZurich(30, maintenant)[0];

/** Les colonnes de Better Auth en casse mixte se citent : Postgres les lit ainsi. */
const CHOIX = `SELECT u.id, u.name, u.email, u."createdAt", u.banned, u."banReason", c.derniere, m.role AS role_membre, m.fin_acces,
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
 * Les comptes de la console, l'inscription la plus récente d'abord, par pages de COMPTES_PAR_PAGE ; la recherche (sans tenir
 * compte de la casse, sous les deux moteurs) et la page se font dans le SQL. Une page demandée trop loin est ramenée à la
 * dernière (page).
 */
export async function listerComptes(b: Base, f: FiltresComptes = { page: 1 }, maintenant = new Date()): Promise<{
  comptes: CompteConsole[];
  pages: number;
  page: number;
}> {
  const ou = f.q ? `WHERE (lower(u.name) LIKE lower(?) ESCAPE '\\' OR lower(u.email) LIKE lower(?) ESCAPE '\\')` : "";
  const valeurs = f.q ? [enLike(f.q), enLike(f.q)] : [];
  const total = (await b.un<{ n: number }>(`SELECT COUNT(*) AS n FROM "user" u ${ou}`, ...valeurs))!.n;
  const pages = Math.max(1, Math.ceil(total / COMPTES_PAR_PAGE));
  const page = Math.min(f.page, pages);
  const lignes = await b.tous<Ligne>(`${CHOIX} ${ou} ORDER BY u."createdAt" DESC, u.id DESC LIMIT ? OFFSET ?`,
    depuis30j(maintenant), ...valeurs, COMPTES_PAR_PAGE, (page - 1) * COMPTES_PAR_PAGE);
  return { comptes: lignes.map((l) => versCompte(l, maintenant)), pages, page };
}

/** La fiche d'un compte : ses agents et leurs messages sur 30 jours, ses sessions ouvertes (sans adresse IP ni jeton). */
export async function ficheCompte(b: Base, id: string, maintenant = new Date()): Promise<{
  compte: CompteConsole;
  agents: (Agent & { messages30j: number })[];
  sessions: { creeLe: string; expireLe: string; appareil: string | null }[];
} | undefined> {
  const l = await b.un<Ligne>(`${CHOIX} WHERE u.id = ?`, depuis30j(maintenant), id);
  if (!l) return undefined;
  const agents = await lister(b, id);
  const messages = await messagesDepuis(b, agents.map((a) => a.id), depuis30j(maintenant));
  const sessions = await b.tous<{ createdAt: string; expiresAt: string; userAgent: string | null }>(
    'SELECT "createdAt", "expiresAt", "userAgent" FROM session WHERE "userId" = ? AND "expiresAt" > ? ORDER BY "createdAt" DESC',
    id, maintenant.toISOString(),
  );
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
export async function peutAgirSur(b: Base, a: Acces, id: string, maintenant = new Date()): Promise<boolean> {
  const m = await membreEnCours(b, id, maintenant);
  return peutSuspendre(a, { id, membre: m ? { role: m.role } : null });
}

/** Le compte visé : inconnu, 404 ; hors de la main du membre, 403. */
async function exigerCompte(b: Base, a: Acces, id: string): Promise<void> {
  if (!(await b.un('SELECT 1 AS n FROM "user" WHERE id = ?', id))) throw new Refus(404, TA.compteInconnu);
  if (!(await peutAgirSur(b, a, id))) throw new Refus(403, TA.suspensionInterdite);
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
 * Corps : { motif }. Le compte ne se connecte plus (l'extension refuse toute nouvelle session) et perd ses sessions. La
 * vérification du compte, le bannissement (les colonnes que l'extension admin de Better Auth écrit) et l'effacement de ses
 * sessions passent dans une même transaction, par sa seule connexion : tout ou rien, et un compte qu'on vient de nommer
 * superadmin n'est pas suspendu d'après ce qu'il était avant. Pas d'appel à l'adaptateur de Better Auth ici : il prendrait
 * une autre connexion pendant que celle-ci tient le verrou des transactions.
 */
export async function suspendre(b: Base, a: Acces, id: string, corps: unknown, maintenant = new Date()): Promise<void> {
  await b.transaction(async (tx) => {
    await exigerCompte(tx, a, id);
    const motif = lireMotif(corps);
    await tx.ecrire('UPDATE "user" SET banned = ?, "banReason" = ?, "banExpires" = NULL, "updatedAt" = ? WHERE id = ?',
      true, motif, maintenant.toISOString(), id);
    await tx.ecrire('DELETE FROM session WHERE "userId" = ?', id);
  });
}

export async function reactiver(b: Base, a: Acces, id: string, ad: AdaptateurComptes): Promise<void> {
  await exigerCompte(b, a, id);
  await ad.updateUser(id, { banned: false, banReason: null, banExpires: null });
}

/** Ferme toutes ses sessions, tout de suite ; il peut se reconnecter. */
export async function deconnecter(b: Base, a: Acces, id: string, ad: AdaptateurComptes): Promise<void> {
  await exigerCompte(b, a, id);
  await ad.deleteUserSessions(id);
}

/**
 * La console sur la vue d'ensemble : comptes et agents en tout ; messages et inscriptions jour par jour, en jours de Zurich
 * (une inscription à 0 h 30 de Zurich compte ce jour-là). Les comptes inscrits dès la veille UTC du premier jour sont lus,
 * puis rangés par leur jour de Zurich.
 */
export async function totauxConsole(b: Base, jours: Jours, maintenant = new Date()): Promise<{
  comptes: number;
  agents: number;
  messages: number;
  parJour: { jour: string; inscriptions: number; messages: number }[];
}> {
  const compter = async (sql: string) => (await b.un<{ n: number }>(sql))!.n;
  const messages = await messagesParJour(b, jours, maintenant);
  const veille = new Date(Date.parse(`${messages[0].jour}T00:00:00Z`) - 24 * 3600 * 1000).toISOString();
  const inscrits = await b.tous<{ createdAt: string }>('SELECT "createdAt" FROM "user" WHERE "createdAt" >= ?', veille);
  const parJour = new Map<string, number>();
  for (const i of inscrits) {
    const jour = jourZurich(new Date(i.createdAt));
    parJour.set(jour, (parJour.get(jour) ?? 0) + 1);
  }
  return {
    comptes: await compter('SELECT COUNT(*) AS n FROM "user"'),
    agents: await compter("SELECT COUNT(*) AS n FROM agent"),
    messages: messages.reduce((s, j) => s + j.messages, 0),
    parJour: messages.map((j) => ({ jour: j.jour, inscriptions: parJour.get(j.jour) ?? 0, messages: j.messages })),
  };
}
