import type { Base, Valeur } from "@/lib/donnees/base";
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
  /** La photo de qui a agi (lue dans la table user) ; null pour le serveur ou un compte sans photo. */
  image: string | null;
};

export type FiltresJournal = { membre?: string; action?: string; client?: string; depuis?: string; jusqua?: string; page: number };

const MASQUE = "[masqué]";
const CLE_SECRETE = /jeton|cle|token|secret|passe|password|authorization/i;
/** Le numéro d'une personne : sous la clé personne, avec ou sans « + » ; ailleurs, seulement la forme internationale. */
const NUMERO = /^\+?\d{6,20}$/;
const INTERNATIONAL = /^\+\d{6,20}$/;
/** Au-delà, le détail sérialisé est coupé : le journal ne se remplit pas d'un corps démesuré. */
const DETAIL_MAX = 2048;

/**
 * Le détail sans secret, à toute profondeur. Un numéro de personne est réduit à ses quatre derniers chiffres : sous la clé
 * personne, ou partout sous sa forme internationale (+ et 6 à 20 chiffres). Un identifiant de client tout en chiffres
 * (« 1234567 », dans client ou perimetre) reste entier. cle : la clé sous laquelle se trouve la valeur.
 */
export function nettoyer(detail: unknown, cle: string | null = null): unknown {
  if (typeof detail === "string") return (cle === "personne" ? NUMERO : INTERNATIONAL).test(detail) ? "…" + detail.slice(-4) : detail;
  if (Array.isArray(detail)) return detail.map((v) => nettoyer(v, cle));
  if (detail && typeof detail === "object") {
    return Object.fromEntries(Object.entries(detail).map(([k, v]) => [k, CLE_SECRETE.test(k) ? MASQUE : nettoyer(v, k)]));
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
  return `${genre}:${genre === "personne" ? (nettoyer(valeur, "personne") as string) : valeur}`;
}

/** Nettoie lui-même la cible et le détail ; le détail sérialisé est coupé à DETAIL_MAX caractères. */
export async function noter(b: Base, e: Omit<LigneJournal, "id" | "quand" | "image">, maintenant = new Date()): Promise<void> {
  const detail = nettoyer(e.detail);
  const texte = detail === undefined || detail === null ? null : (JSON.stringify(detail)?.slice(0, DETAIL_MAX) ?? null);
  await b.ecrire("INSERT INTO admin_journal (quand, qui, courriel, action, cible, resultat, detail) VALUES (?, ?, ?, ?, ?, ?, ?)",
    maintenant.toISOString(), e.qui, e.courriel, e.action, nettoyerCible(e.cible), e.resultat, texte);
}

type Ligne = Omit<LigneJournal, "detail" | "image"> & { detail: string | null; image: string | null };

const ZURICH = new Intl.DateTimeFormat("en-US", {
  timeZone: "Europe/Zurich",
  hourCycle: "h23",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
});

/** L'avance de Zurich sur UTC, en millisecondes, à un instant donné (une heure en hiver, deux en été). */
function avanceZurich(t: number): number {
  const p = Object.fromEntries(ZURICH.formatToParts(new Date(t)).map((x) => [x.type, Number(x.value)]));
  return Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute, p.second) - Math.floor(t / 1000) * 1000;
}

/** Le premier instant (ISO UTC) d'un jour AAAA-MM-JJ de Zurich, le fuseau où l'écran montre le journal (TA.instant). */
function debutJour(jour: string): string {
  const minuitUtc = Date.parse(`${jour}T00:00:00Z`);
  return new Date(minuitUtc - avanceZurich(minuitUtc - avanceZurich(minuitUtc))).toISOString();
}

const lendemain = (jour: string) => new Date(Date.parse(`${jour}T00:00:00Z`) + 24 * 3600 * 1000).toISOString().slice(0, 10);

/** Ce que le membre voit, puis ses filtres. Limité à une liste : ses propres gestes et ceux qui touchent ses clients. */
function conditions(a: Acces, f: FiltresJournal): { sql: string; valeurs: Valeur[] } {
  const c: string[] = [];
  const valeurs: Valeur[] = [];
  const et = (sql: string, ...v: Valeur[]) => {
    c.push(sql);
    valeurs.push(...v);
  };
  if (a.perimetre !== "tous") {
    const cibles = a.perimetre.map((client) => `client:${client}`);
    if (cibles.length) et(`(qui = ? OR cible IN (${cibles.map(() => "?").join(", ")}))`, a.utilisateur, ...cibles);
    else et("qui = ?", a.utilisateur);
  }
  if (f.membre) et("qui = ?", f.membre);
  if (f.action) et("action = ?", f.action);
  if (f.client) et("cible = ?", `client:${f.client}`);
  // depuis et jusqua sont des jours de Zurich, inclus : un geste montré « 05.01 00:30 » est du 5 janvier.
  if (f.depuis) et("quand >= ?", debutJour(f.depuis));
  if (f.jusqua) et("quand < ?", debutJour(lendemain(f.jusqua)));
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

/** Le plus récent d'abord, par pages de LIGNES_PAR_PAGE ; une page demandée trop loin est ramenée à la dernière (page). */
export async function lireJournal(b: Base, a: Acces, f: FiltresJournal): Promise<{ lignes: LigneJournal[]; pages: number; page: number }> {
  const { sql, valeurs } = conditions(a, f);
  const total = (await b.un<{ n: number }>(`SELECT COUNT(*) AS n FROM admin_journal ${sql}`, ...valeurs))!.n;
  const pages = Math.max(1, Math.ceil(total / LIGNES_PAR_PAGE));
  const page = Math.min(f.page, pages);
  // Les conditions nomment des colonnes que la table user n'a pas (quand, qui, action, cible) : seul id se qualifie.
  const lignes = await b.tous<Ligne>(
    `SELECT j.*, u.image FROM admin_journal j LEFT JOIN "user" u ON u.id = j.qui ${sql} ORDER BY j.quand DESC, j.id DESC LIMIT ? OFFSET ?`,
    ...valeurs, LIGNES_PAR_PAGE, (page - 1) * LIGNES_PAR_PAGE);
  return { lignes: lignes.map((l) => ({ ...l, detail: detailLu(l.detail), image: l.image ?? null })), pages, page };
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
