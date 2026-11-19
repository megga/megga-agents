// Les aides des essais de l'admin : un accès de membre fabriqué, la capture d'un refus,
// et une base en mémoire avec les tables de Better Auth et celles de la console.
import { getMigrations } from "better-auth/db/migration";
import { droitsEffectifs, type Acces, type Perimetre } from "@/lib/admin/acces";
import { SUPERADMIN, type Droit } from "@/lib/admin/droits";
import { accesDe, ajouterMembre } from "@/lib/admin/membres";
import { Refus } from "@/lib/agents";
import { optionsAuth } from "@/lib/auth";
import { preparer } from "@/lib/base";
import type { Base } from "@/lib/donnees/base";
import { baseVide, moteurParDefaut, type Moteur } from "../moteurs";

/** L'instant des essais. */
export const T0 = new Date("2026-11-18T10:00:00Z");

/**
 * Une base neuve du moteur des essais (CONSOLE_ESSAI_MOTEUR, SQLite en mémoire par défaut) : les tables de Better Auth,
 * puis celles de la console et de l'admin.
 */
export async function baseEssai(moteur: Moteur = moteurParDefaut()): Promise<Base> {
  const b = await baseVide(moteur);
  const { runMigrations } = await getMigrations(optionsAuth(b));
  await runMigrations();
  await preparer(b);
  return b;
}

/** Les colonnes d'une table, dans leur ordre, sous chaque moteur. */
export async function colonnes(b: Base, table: string): Promise<string[]> {
  const lignes = b.dialecte === "postgres"
    ? await b.tous<{ name: string }>(
      "SELECT column_name AS name FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = ? ORDER BY ordinal_position",
      table,
    )
    : await b.tous<{ name: string }>(`PRAGMA table_info("${table}")`);
  return lignes.map((c) => c.name);
}

/** Un compte de la console (une ligne de la table user de Better Auth). */
export async function compte(b: Base, c: { id: string; courriel: string; nom?: string; creeLe?: string }): Promise<void> {
  const quand = c.creeLe ?? T0.toISOString();
  await b.ecrire('INSERT INTO "user" (id, name, email, "emailVerified", "createdAt", "updatedAt") VALUES (?, ?, ?, ?, ?, ?)',
    c.id, c.nom ?? c.id.toUpperCase(), c.courriel, false, quand, quand);
}

/** Un membre de l'admin et son compte (créé s'il manque) ; rend son accès à T0. */
export async function membre(
  b: Base,
  m: { utilisateur: string; role: string; externe?: boolean; perimetre?: Perimetre; finAcces?: string | null },
): Promise<Acces> {
  const courriel = `${m.utilisateur}@megga.test`;
  if (!(await b.un('SELECT 1 AS n FROM "user" WHERE id = ?', m.utilisateur))) await compte(b, { id: m.utilisateur, courriel });
  await ajouterMembre(b, { utilisateur: m.utilisateur, role: m.role, externe: m.externe ?? false, perimetre: m.perimetre ?? "tous",
    finAcces: m.finAcces ?? null, ajoutePar: null }, T0);
  const a = await accesDe(b, { id: m.utilisateur, email: courriel, name: m.utilisateur.toUpperCase() }, T0);
  if (!a) throw new Error(`le membre ${m.utilisateur} n'est pas en cours à T0`);
  return a;
}

/** Un rôle sans aucun droit ; rend son identifiant. */
export async function roleVide(b: Base): Promise<string> {
  await b.ecrire("INSERT INTO admin_role (id, nom, description, droits, systeme, cree_le, modifie_le) VALUES ('vide', 'Vide', '', '[]', 0, ?, ?) ON CONFLICT DO NOTHING",
    T0.toISOString(), T0.toISOString());
  return "vide";
}

/** Un accès de membre, sans base : les droits passent par droitsEffectifs (plafond d'un externe compris). */
export function acces(p: { utilisateur?: string; role?: string; droits?: readonly Droit[]; externe?: boolean; superadmin?: boolean; perimetre?: Perimetre } = {}): Acces {
  const utilisateur = p.utilisateur ?? "u";
  const superadmin = p.superadmin ?? false;
  const externe = p.externe ?? false;
  const role = superadmin ? SUPERADMIN : (p.role ?? "essai");
  return {
    utilisateur,
    courriel: `${utilisateur}@megga.test`,
    nom: utilisateur,
    role: { id: role, nom: role },
    superadmin,
    externe,
    perimetre: superadmin ? "tous" : (p.perimetre ?? "tous"),
    finAcces: null,
    droits: droitsEffectifs(p.droits ?? [], externe, superadmin),
  };
}

export function refus(f: () => unknown): Refus {
  try {
    f();
  } catch (e) {
    if (e instanceof Refus) return e;
    throw e;
  }
  throw new Error("aucun refus");
}

export async function refusAsync(f: () => Promise<unknown>): Promise<Refus> {
  try {
    await f();
  } catch (e) {
    if (e instanceof Refus) return e;
    throw e;
  }
  throw new Error("aucun refus");
}
