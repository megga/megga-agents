import "server-only";
import { mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { DatabaseSync } from "node:sqlite";

// La base de la console : les comptes de Better Auth et les agents de chaque compte.
// SQLite intégré à Node en local ; Postgres (Neon) au déploiement, par l'adaptateur de Better Auth.

const globale = globalThis as unknown as { baseConsole?: DatabaseSync };

export function cheminBase(): string {
  return process.env.CONSOLE_BASE || resolve(process.cwd(), ".donnees/console.sqlite");
}

export function base(): DatabaseSync {
  if (!globale.baseConsole) {
    const chemin = cheminBase();
    if (chemin !== ":memory:") mkdirSync(dirname(chemin), { recursive: true });
    const db = new DatabaseSync(chemin);
    db.exec("PRAGMA journal_mode = WAL; PRAGMA foreign_keys = ON;");
    db.exec(`CREATE TABLE IF NOT EXISTS agent (
      id TEXT PRIMARY KEY,
      utilisateur TEXT NOT NULL,
      prenom TEXT NOT NULL,
      metier TEXT NOT NULL,
      couleur INTEGER NOT NULL DEFAULT 0,
      yeux INTEGER NOT NULL DEFAULT 0,
      epingle INTEGER NOT NULL DEFAULT 0,
      cree_le TEXT NOT NULL
    )`);
    db.exec("CREATE INDEX IF NOT EXISTS agent_utilisateur ON agent (utilisateur)");
    globale.baseConsole = db;
  }
  return globale.baseConsole;
}
