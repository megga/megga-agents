import type { DatabaseSync } from "node:sqlite";
import { DROITS, ROLES_DE_DEPART, SUPERADMIN } from "./droits";
import { TA } from "./textes";

// Les tables de l'admin, dans la base de la console (approche A de la conception).
// Dates en texte ISO UTC ; listes (droits, périmètre) en JSON ; un périmètre NULL vaut « tous ».

export function creerTablesAdmin(db: DatabaseSync, maintenant = new Date()): void {
  db.exec(`CREATE TABLE IF NOT EXISTS admin_role (
    id TEXT PRIMARY KEY,
    nom TEXT NOT NULL UNIQUE COLLATE NOCASE,
    description TEXT NOT NULL DEFAULT '',
    droits TEXT NOT NULL DEFAULT '[]',
    systeme INTEGER NOT NULL DEFAULT 0,
    cree_le TEXT NOT NULL,
    modifie_le TEXT NOT NULL
  )`);
  db.exec(`CREATE TABLE IF NOT EXISTS admin_membre (
    utilisateur TEXT PRIMARY KEY,
    role TEXT NOT NULL,
    externe INTEGER NOT NULL DEFAULT 0,
    perimetre TEXT,
    fin_acces TEXT,
    ajoute_par TEXT,
    ajoute_le TEXT NOT NULL
  )`);
  db.exec(`CREATE TABLE IF NOT EXISTS admin_invitation (
    id TEXT PRIMARY KEY,
    empreinte TEXT NOT NULL UNIQUE,
    courriel TEXT NOT NULL,
    role TEXT NOT NULL,
    externe INTEGER NOT NULL DEFAULT 0,
    perimetre TEXT,
    fin_acces TEXT,
    valable_jusqua TEXT NOT NULL,
    creee_par TEXT,
    creee_le TEXT NOT NULL,
    acceptee_le TEXT,
    acceptee_par TEXT,
    retiree_le TEXT
  )`);
  db.exec(`CREATE TABLE IF NOT EXISTS admin_journal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    quand TEXT NOT NULL,
    qui TEXT,
    courriel TEXT,
    action TEXT NOT NULL,
    cible TEXT,
    resultat TEXT NOT NULL,
    detail TEXT
  )`);
  db.exec(`CREATE TABLE IF NOT EXISTS usage_agent (
    agent TEXT NOT NULL,
    jour TEXT NOT NULL,
    messages INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (agent, jour)
  )`);
  db.exec(`CREATE TABLE IF NOT EXISTS compte_connexion (
    utilisateur TEXT PRIMARY KEY,
    derniere TEXT NOT NULL
  )`);
  db.exec("CREATE INDEX IF NOT EXISTS admin_membre_role ON admin_membre (role)");
  db.exec("CREATE INDEX IF NOT EXISTS admin_journal_quand ON admin_journal (quand)");
  semerRoles(db, maintenant);
}

/** Le superadmin à chaque démarrage ; les rôles de départ à la création seulement, pour qu'un rôle retiré ne revienne pas. */
function semerRoles(db: DatabaseSync, maintenant: Date): void {
  const quand = maintenant.toISOString();
  const premiere = (db.prepare("SELECT COUNT(*) AS n FROM admin_role").get() as { n: number }).n === 0;
  const inserer = db.prepare(
    "INSERT OR IGNORE INTO admin_role (id, nom, description, droits, systeme, cree_le, modifie_le) VALUES (?, ?, ?, ?, ?, ?, ?)",
  );
  inserer.run(SUPERADMIN, TA.roleSuperadmin, TA.roleSuperadminDescription, JSON.stringify(DROITS), 1, quand, quand);
  if (!premiere) return;
  for (const r of ROLES_DE_DEPART) inserer.run(r.id, r.nom, r.description, JSON.stringify(r.droits), 0, quand, quand);
}
