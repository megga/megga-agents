import { mkdirSync } from "node:fs";
import { dirname } from "node:path";
import { DatabaseSync, type SQLInputValue } from "node:sqlite";
import type { Base, Ligne, Valeur } from "./base";

// Le moteur SQLite (node:sqlite) : une seule connexion, et toute opération passe par un verrou (une file de promesses).
// Une transaction garde le verrou de BEGIN IMMEDIATE à COMMIT ou ROLLBACK : une requête lancée pendant qu'elle attend un
// await passe après elle, sans entrer dans la transaction ni être annulée avec elle.

const versSqlite = (params: Valeur[]): SQLInputValue[] => params.map((p) => (typeof p === "boolean" ? (p ? 1 : 0) : p));

/** Les opérations directes sur la connexion, sans verrou : celles d'une transaction déjà ouverte. */
function directe(db: DatabaseSync, dans: (f: (tx: Base) => Promise<unknown>) => Promise<unknown>, fermer: () => Promise<void>): Base {
  return {
    dialecte: "sqlite",
    un: async <T extends Ligne>(sql: string, ...params: Valeur[]) => db.prepare(sql).get(...versSqlite(params)) as T | undefined,
    tous: async <T extends Ligne>(sql: string, ...params: Valeur[]) => db.prepare(sql).all(...versSqlite(params)) as T[],
    ecrire: async (sql: string, ...params: Valeur[]) => ({ changements: Number(db.prepare(sql).run(...versSqlite(params)).changes) }),
    executer: async (sql: string) => {
      db.exec(sql);
    },
    transaction: <T>(f: (tx: Base) => Promise<T>) => dans(f) as Promise<T>,
    pourAuth: () => db,
    fermer,
  };
}

export function baseSqlite(chemin: string): Base {
  if (chemin !== ":memory:") mkdirSync(dirname(chemin), { recursive: true });
  const db = new DatabaseSync(chemin);
  db.exec(chemin === ":memory:" ? "PRAGMA foreign_keys = ON;" : "PRAGMA journal_mode = WAL; PRAGMA foreign_keys = ON;");

  let file: Promise<unknown> = Promise.resolve();
  /** f passe quand tout ce qui a été lancé avant lui est fini, réussi ou non. */
  function verrou<T>(f: () => Promise<T>): Promise<T> {
    const r = file.then(f);
    file = r.catch(() => undefined);
    return r;
  }

  const fermer = async () => {
    await verrou(async () => {
      if (db.isOpen) db.close();
    });
  };

  // Dans une transaction : une transaction imbriquée n'en fait qu'une avec elle.
  const tx: Base = directe(db, (f) => f(tx), fermer);

  const transaction = <T>(f: (tx: Base) => Promise<T>): Promise<T> =>
    verrou(async () => {
      db.exec("BEGIN IMMEDIATE");
      try {
        const r = await f(tx);
        db.exec("COMMIT");
        return r;
      } catch (e) {
        if (db.isTransaction) db.exec("ROLLBACK");
        throw e;
      }
    });

  return {
    dialecte: "sqlite",
    un: <T extends Ligne>(sql: string, ...params: Valeur[]) => verrou(() => tx.un<T>(sql, ...params)),
    tous: <T extends Ligne>(sql: string, ...params: Valeur[]) => verrou(() => tx.tous<T>(sql, ...params)),
    ecrire: (sql, ...params) => verrou(() => tx.ecrire(sql, ...params)),
    executer: (sql) => verrou(() => tx.executer(sql)),
    transaction,
    pourAuth: () => db,
    fermer,
  };
}
