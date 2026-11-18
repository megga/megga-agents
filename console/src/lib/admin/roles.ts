import { randomUUID } from "node:crypto";
import type { DatabaseSync } from "node:sqlite";
import { Refus } from "@/lib/agents";
import { peutEcrireRole, type Acces } from "./acces";
import { DROITS, estDroit, type Droit } from "./droits";
import { TA } from "./textes";

// Les rôles de l'équipe : un nom, une description, des droits cochés parmi les treize.
// Le superadmin (systeme) est fixe ; un rôle encore porté par un membre ne se retire pas.

export type Role = { id: string; nom: string; description: string; droits: Droit[]; systeme: boolean; membres: number };

type Ligne = { id: string; nom: string; description: string; droits: string; systeme: number; membres: number };

const CHOIX = `SELECT r.id, r.nom, r.description, r.droits, r.systeme,
  (SELECT COUNT(*) FROM admin_membre m WHERE m.role = r.id) AS membres FROM admin_role r`;

/** Les droits lus en base : un droit inconnu (une ligne écrite à la main) est ignoré, jamais accordé. */
function droitsLus(json: string): Droit[] {
  let v: unknown;
  try {
    v = JSON.parse(json);
  } catch {
    return [];
  }
  return Array.isArray(v) ? DROITS.filter((d) => v.includes(d)) : [];
}

function versRole(l: Ligne): Role {
  return { id: l.id, nom: l.nom, description: l.description, droits: droitsLus(l.droits), systeme: !!l.systeme, membres: l.membres };
}

export function listerRoles(db: DatabaseSync): Role[] {
  return (db.prepare(`${CHOIX} ORDER BY r.systeme DESC, r.cree_le, r.rowid`).all() as Ligne[]).map(versRole);
}

export function lireRole(db: DatabaseSync, id: string): Role | undefined {
  const l = db.prepare(`${CHOIX} WHERE r.id = ?`).get(id) as Ligne | undefined;
  return l && versRole(l);
}

const objet = (corps: unknown) => (corps && typeof corps === "object" ? corps : {}) as Record<string, unknown>;

function lireNom(v: unknown): string {
  const nom = typeof v === "string" ? v.trim().replace(/\s+/g, " ") : "";
  if (!nom) throw new Refus(400, TA.nomManquant);
  return nom;
}

const lireDescription = (v: unknown) => (typeof v === "string" ? v.trim() : "");

/** Des droits cochés : tous connus, sans doublon, rangés dans l'ordre des treize. */
function lireDroits(v: unknown): Droit[] {
  if (v === undefined) return [];
  if (!Array.isArray(v) || !v.every(estDroit)) throw new Refus(400, TA.droitInconnu);
  return DROITS.filter((d) => v.includes(d));
}

function exigerNomLibre(db: DatabaseSync, nom: string, sauf: string | null): void {
  const l = db.prepare("SELECT id FROM admin_role WHERE nom = ? COLLATE NOCASE").get(nom) as { id: string } | undefined;
  if (l && l.id !== sauf) throw new Refus(409, TA.nomPris);
}

/** Un rôle fixe ou inconnu ne se change pas ; sans être superadmin, on ne touche qu'à un rôle dont on a déjà tous les droits. */
function roleAEcrire(db: DatabaseSync, a: Acces, id: string): Role {
  const role = lireRole(db, id);
  if (role?.systeme) throw new Refus(403, TA.roleFixe);
  if (!role) throw new Refus(404, TA.roleInconnu);
  if (!peutEcrireRole(a, role.droits, id)) throw new Refus(403, TA.escalade);
  return role;
}

export function creerRole(db: DatabaseSync, a: Acces, corps: unknown, maintenant = new Date()): Role {
  const c = objet(corps);
  const nom = lireNom(c.nom);
  const droits = lireDroits(c.droits);
  if (!peutEcrireRole(a, droits, null)) throw new Refus(403, TA.escalade);
  exigerNomLibre(db, nom, null);
  const id = "ro_" + randomUUID().replace(/-/g, "").slice(0, 20);
  const quand = maintenant.toISOString();
  db.prepare("INSERT INTO admin_role (id, nom, description, droits, systeme, cree_le, modifie_le) VALUES (?, ?, ?, ?, 0, ?, ?)")
    .run(id, nom, lireDescription(c.description), JSON.stringify(droits), quand, quand);
  return lireRole(db, id)!;
}

/** Corps : { nom?, description?, droits? } ; ce qui manque reste tel quel. */
export function modifierRole(db: DatabaseSync, a: Acces, id: string, corps: unknown, maintenant = new Date()): Role {
  const role = roleAEcrire(db, a, id);
  const c = objet(corps);
  const nom = c.nom === undefined ? role.nom : lireNom(c.nom);
  const description = c.description === undefined ? role.description : lireDescription(c.description);
  const droits = c.droits === undefined ? role.droits : lireDroits(c.droits);
  if (!peutEcrireRole(a, droits, id)) throw new Refus(403, TA.escalade);
  exigerNomLibre(db, nom, id);
  db.prepare("UPDATE admin_role SET nom = ?, description = ?, droits = ?, modifie_le = ? WHERE id = ?")
    .run(nom, description, JSON.stringify(droits), maintenant.toISOString(), id);
  return lireRole(db, id)!;
}

export function retirerRole(db: DatabaseSync, a: Acces, id: string): void {
  const role = roleAEcrire(db, a, id);
  if (role.membres > 0) throw new Refus(409, TA.rolePorte);
  db.prepare("DELETE FROM admin_role WHERE id = ?").run(id);
}
