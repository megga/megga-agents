import { resolve } from "node:path";
import { basePostgres } from "./postgres";
import { baseSqlite } from "./sqlite";

// L'interface de la base de la console : tout le SQL de console/src/lib passe par elle. Deux moteurs la servent : SQLite
// (intégré à Node), en local et dans les essais, et Postgres (pg), quand CONSOLE_BASE_URL est posée : la production.
// Le SQL s'écrit une fois, avec des « ? », dans ce que les deux moteurs comprennent.

export type Valeur = string | number | boolean | null;
export type Ligne = Record<string, unknown>;

export interface Base {
  readonly dialecte: "sqlite" | "postgres";
  /** La première ligne, ou undefined. */
  un<T extends Ligne>(sql: string, ...params: Valeur[]): Promise<T | undefined>;
  tous<T extends Ligne>(sql: string, ...params: Valeur[]): Promise<T[]>;
  /** Le nombre de lignes touchées. */
  ecrire(sql: string, ...params: Valeur[]): Promise<{ changements: number }>;
  /** Du DDL : une seule instruction, sans paramètre. */
  executer(sql: string): Promise<void>;
  /**
   * f tourne dans une transaction, tout ou rien, l'une après l'autre avec toutes les transactions de la console ; f n'utilise
   * que tx. Une transaction ouverte dans une autre (tx.transaction) n'en fait qu'une avec elle.
   */
  transaction<T>(f: (tx: Base) => Promise<T>): Promise<T>;
  /** Ce que Better Auth reçoit dans `database` : la connexion SQLite ou le Pool de Postgres. */
  pourAuth(): unknown;
  fermer(): Promise<void>;
}

/** Le fichier SQLite de la console, quand CONSOLE_BASE_URL n'est pas posée. */
export function cheminBase(env: Record<string, string | undefined> = process.env): string {
  return env.CONSOLE_BASE || resolve(process.cwd(), ".donnees/console.sqlite");
}

/** Postgres si CONSOLE_BASE_URL est posée, sinon SQLite sur cheminBase(). */
export function ouvrirBase(env: Record<string, string | undefined> = process.env): Base {
  return env.CONSOLE_BASE_URL ? basePostgres(env.CONSOLE_BASE_URL) : baseSqlite(cheminBase(env));
}
