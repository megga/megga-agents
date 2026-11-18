import type { DatabaseSync, SQLInputValue } from "node:sqlite";
import type { Acces } from "./acces";
import { estJour } from "./membres";

// Le journal de l'admin : chaque écriture, réussie ou refusée, et chaque conversation ouverte.
// Jamais un secret : le détail passe toujours par nettoyer, ici même, avant d'être écrit.

export const LIGNES_PAR_PAGE = 50;

/** cible : "client:<id>", "compte:<id>", "role:<id>", "membre:<id>", "invitation:<id>". */
export type LigneJournal = {
  id: number;
  quand: string;
  qui: string | null;
  courriel: string | null;
  action: string;
  cible: string | null;
  resultat: string;
  detail: unknown;
};

export type FiltresJournal = { membre?: string; action?: string; client?: string; depuis?: string; jusqua?: string; page: number };

const MASQUE = "[masqué]";
const CLE_SECRETE = /jeton|cle|token|secret|passe|password|authorization/i;
const NUMERO = /^\+?\d{6,20}$/;
/** Au-delà, le détail sérialisé est coupé : le journal ne se remplit pas d'un corps démesuré. */
const DETAIL_MAX = 2048;

/** Le détail sans secret, à toute profondeur ; un numéro (de personne) réduit à ses quatre derniers chiffres. */
export function nettoyer(detail: unknown): unknown {
  if (typeof detail === "string") return NUMERO.test(detail) ? "…" + detail.slice(-4) : detail;
  if (Array.isArray(detail)) return detail.map(nettoyer);
  if (detail && typeof detail === "object") {
    return Object.fromEntries(Object.entries(detail).map(([k, v]) => [k, CLE_SECRETE.test(k) ? MASQUE : nettoyer(v)]));
  }
  return detail;
}

/**
 * Une cible « genre:valeur » : la valeur d'un genre secret masquée ; le numéro d'une personne réduit à ses quatre derniers
 * chiffres ; toute autre valeur entière (un identifiant de client peut être tout en chiffres).
 */
function nettoyerCible(cible: string | null): string | null {
  if (cible === null) return null;
  const i = cible.indexOf(":");
  if (i < 0) return nettoyer(cible) as string;
  const genre = cible.slice(0, i);
  const valeur = cible.slice(i + 1);
  if (CLE_SECRETE.test(genre)) return `${genre}:${MASQUE}`;
  return `${genre}:${genre === "personne" ? (nettoyer(valeur) as string) : valeur}`;
}

/** Nettoie lui-même la cible et le détail ; le détail sérialisé est coupé à DETAIL_MAX caractères. */
export function noter(db: DatabaseSync, e: Omit<LigneJournal, "id" | "quand">, maintenant = new Date()): void {
  const detail = nettoyer(e.detail);
  const texte = detail === undefined || detail === null ? null : (JSON.stringify(detail)?.slice(0, DETAIL_MAX) ?? null);
  db.prepare("INSERT INTO admin_journal (quand, qui, courriel, action, cible, resultat, detail) VALUES (?, ?, ?, ?, ?, ?, ?)")
    .run(maintenant.toISOString(), e.qui, e.courriel, e.action, nettoyerCible(e.cible), e.resultat, texte);
}

type Ligne = Omit<LigneJournal, "detail"> & { detail: string | null };

/** Ce que le membre voit, puis ses filtres. Limité à une liste : ses propres gestes et ceux qui touchent ses clients. */
function conditions(a: Acces, f: FiltresJournal): { sql: string; valeurs: SQLInputValue[] } {
  const c: string[] = [];
  const valeurs: SQLInputValue[] = [];
  const et = (sql: string, ...v: SQLInputValue[]) => {
    c.push(sql);
    valeurs.push(...v);
  };
  if (a.perimetre !== "tous") et("(qui = ? OR cible IN (SELECT 'client:' || value FROM json_each(?)))", a.utilisateur, JSON.stringify(a.perimetre));
  if (f.membre) et("qui = ?", f.membre);
  if (f.action) et("action = ?", f.action);
  if (f.client) et("cible = ?", `client:${f.client}`);
  if (f.depuis) et("quand >= ?", `${f.depuis}T00:00:00.000Z`);
  if (f.jusqua) et("quand <= ?", `${f.jusqua}T23:59:59.999Z`);
  return { sql: c.length ? `WHERE ${c.join(" AND ")}` : "", valeurs };
}

/** Le détail relu ; un détail coupé (JSON incomplet) est rendu tel quel, en texte. */
function detailLu(json: string | null): unknown {
  if (json === null) return null;
  try {
    return JSON.parse(json);
  } catch {
    return json;
  }
}

/** Le plus récent d'abord, par pages de LIGNES_PAR_PAGE. */
export function lireJournal(db: DatabaseSync, a: Acces, f: FiltresJournal): { lignes: LigneJournal[]; pages: number } {
  const { sql, valeurs } = conditions(a, f);
  const total = (db.prepare(`SELECT COUNT(*) AS n FROM admin_journal ${sql}`).get(...valeurs) as { n: number }).n;
  const pages = Math.max(1, Math.ceil(total / LIGNES_PAR_PAGE));
  if (f.page > pages) return { lignes: [], pages };
  const lignes = db
    .prepare(`SELECT * FROM admin_journal ${sql} ORDER BY quand DESC, id DESC LIMIT ? OFFSET ?`)
    .all(...valeurs, LIGNES_PAR_PAGE, (f.page - 1) * LIGNES_PAR_PAGE) as Ligne[];
  return { lignes: lignes.map((l) => ({ ...l, detail: detailLu(l.detail) })), pages };
}

/** Les filtres tels que l'adresse les donne ; une valeur mal formée est ignorée, la page retombe sur 1. */
export function filtresDe(p: Record<string, string | string[] | undefined>): FiltresJournal {
  const lire = (cle: string) => {
    const v = p[cle];
    const s = (Array.isArray(v) ? v[0] : v)?.trim();
    return s || undefined;
  };
  const page = Number(lire("page"));
  const f: FiltresJournal = { page: Number.isSafeInteger(page) && page >= 1 ? page : 1 };
  for (const cle of ["membre", "action", "client"] as const) {
    const v = lire(cle);
    if (v) f[cle] = v;
  }
  for (const cle of ["depuis", "jusqua"] as const) {
    const v = lire(cle);
    if (estJour(v)) f[cle] = v;
  }
  return f;
}
