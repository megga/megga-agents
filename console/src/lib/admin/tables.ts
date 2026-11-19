import type { Base } from "@/lib/donnees/base";
import { DROITS, ROLES_DE_DEPART, SUPERADMIN } from "./droits";
import { TA } from "./textes";

// Les tables de l'admin, dans la base de la console (approche A de la conception).
// Dates en texte ISO UTC ; listes (droits, périmètre) en JSON ; un périmètre NULL vaut « tous ». Le même DDL sous SQLite et
// sous Postgres, sauf la clé du journal. Le nom d'un rôle est unique sans tenir compte de la casse (admin_role_nom) ; une base
// SQLite créée avant garde aussi son ancienne contrainte UNIQUE COLLATE NOCASE, qui dit la même chose.

export async function creerTablesAdmin(b: Base, maintenant = new Date()): Promise<void> {
  await b.executer(`CREATE TABLE IF NOT EXISTS admin_role (
    id TEXT PRIMARY KEY,
    nom TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    droits TEXT NOT NULL DEFAULT '[]',
    systeme INTEGER NOT NULL DEFAULT 0,
    cree_le TEXT NOT NULL,
    modifie_le TEXT NOT NULL
  )`);
  await b.executer(`CREATE TABLE IF NOT EXISTS admin_membre (
    utilisateur TEXT PRIMARY KEY,
    role TEXT NOT NULL,
    externe INTEGER NOT NULL DEFAULT 0,
    perimetre TEXT,
    fin_acces TEXT,
    ajoute_par TEXT,
    ajoute_le TEXT NOT NULL
  )`);
  await b.executer(`CREATE TABLE IF NOT EXISTS admin_invitation (
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
  await b.executer(`CREATE TABLE IF NOT EXISTS admin_journal (
    id ${b.dialecte === "postgres" ? "BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY" : "INTEGER PRIMARY KEY AUTOINCREMENT"},
    quand TEXT NOT NULL,
    qui TEXT,
    courriel TEXT,
    action TEXT NOT NULL,
    cible TEXT,
    resultat TEXT NOT NULL,
    detail TEXT
  )`);
  await b.executer(`CREATE TABLE IF NOT EXISTS usage_agent (
    agent TEXT NOT NULL,
    jour TEXT NOT NULL,
    messages INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (agent, jour)
  )`);
  await b.executer(`CREATE TABLE IF NOT EXISTS compte_connexion (
    utilisateur TEXT PRIMARY KEY,
    derniere TEXT NOT NULL
  )`);
  // La photo de profil d'un compte (photo.ts) : ses octets en base64, au plus 200 Ko décodés ; la version change avec elle.
  await b.executer(`CREATE TABLE IF NOT EXISTS compte_photo (
    utilisateur TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    donnees TEXT NOT NULL,
    version TEXT NOT NULL,
    modifiee_le TEXT NOT NULL
  )`);
  await b.executer("CREATE UNIQUE INDEX IF NOT EXISTS admin_role_nom ON admin_role (lower(nom))");
  await b.executer("CREATE INDEX IF NOT EXISTS admin_membre_role ON admin_membre (role)");
  await b.executer("CREATE INDEX IF NOT EXISTS admin_journal_quand ON admin_journal (quand)");
  await semerRoles(b, maintenant);
}

/** Le superadmin à chaque démarrage ; les rôles de départ à la création seulement, pour qu'un rôle retiré ne revienne pas. */
async function semerRoles(b: Base, maintenant: Date): Promise<void> {
  const quand = maintenant.toISOString();
  await b.transaction(async (tx) => {
    const premiere = (await tx.un<{ n: number }>("SELECT COUNT(*) AS n FROM admin_role"))!.n === 0;
    const inserer = (id: string, nom: string, description: string, droits: readonly string[], systeme: number) =>
      tx.ecrire(
        `INSERT INTO admin_role (id, nom, description, droits, systeme, cree_le, modifie_le) VALUES (?, ?, ?, ?, ?, ?, ?)
         ON CONFLICT DO NOTHING`,
        id, nom, description, JSON.stringify(droits), systeme, quand, quand,
      );
    await inserer(SUPERADMIN, TA.roleSuperadmin, TA.roleSuperadminDescription, DROITS, 1);
    if (!premiere) return;
    for (const r of ROLES_DE_DEPART) await inserer(r.id, r.nom, r.description, r.droits, 0);
  });
}
