import { randomUUID } from "node:crypto";
import { Refus } from "@/lib/agents";
import type { Base } from "@/lib/donnees/base";
import { peutEcrireRole, type Acces } from "./acces";
import { DROITS, estDroit, type Droit } from "./droits";
import { TA } from "./textes";

// Les rôles de l'équipe : un nom, une description, des droits cochés parmi les treize.
// Le superadmin (systeme) est fixe ; un rôle encore porté par un membre ne se retire pas. Chaque écriture lit puis écrit
// dans une même transaction : deux requêtes à la fois ne passent pas entre la vérification et l'écriture.

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

export async function listerRoles(b: Base): Promise<Role[]> {
  return (await b.tous<Ligne>(`${CHOIX} ORDER BY r.systeme DESC, r.cree_le, r.id`)).map(versRole);
}

export async function lireRole(b: Base, id: string): Promise<Role | undefined> {
  const l = await b.un<Ligne>(`${CHOIX} WHERE r.id = ?`, id);
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

async function exigerNomLibre(b: Base, nom: string, sauf: string | null): Promise<void> {
  const l = await b.un<{ id: string }>("SELECT id FROM admin_role WHERE lower(nom) = lower(?)", nom);
  if (l && l.id !== sauf) throw new Refus(409, TA.nomPris);
}

/** Un rôle fixe ou inconnu ne se change pas ; sans être superadmin, on ne touche qu'à un rôle dont on a déjà tous les droits. */
async function roleAEcrire(b: Base, a: Acces, id: string): Promise<Role> {
  const role = await lireRole(b, id);
  if (role?.systeme) throw new Refus(403, TA.roleFixe);
  if (!role) throw new Refus(404, TA.roleInconnu);
  if (!peutEcrireRole(a, role.droits, id)) throw new Refus(403, TA.escalade);
  return role;
}

export function creerRole(b: Base, a: Acces, corps: unknown, maintenant = new Date()): Promise<Role> {
  const c = objet(corps);
  return b.transaction(async (tx) => {
    const nom = lireNom(c.nom);
    const droits = lireDroits(c.droits);
    if (!peutEcrireRole(a, droits, null)) throw new Refus(403, TA.escalade);
    await exigerNomLibre(tx, nom, null);
    const id = "ro_" + randomUUID().replace(/-/g, "").slice(0, 20);
    const quand = maintenant.toISOString();
    await tx.ecrire("INSERT INTO admin_role (id, nom, description, droits, systeme, cree_le, modifie_le) VALUES (?, ?, ?, ?, 0, ?, ?)",
      id, nom, lireDescription(c.description), JSON.stringify(droits), quand, quand);
    return (await lireRole(tx, id))!;
  });
}

/** Corps : { nom?, description?, droits? } ; ce qui manque reste tel quel. */
export function modifierRole(b: Base, a: Acces, id: string, corps: unknown, maintenant = new Date()): Promise<Role> {
  const c = objet(corps);
  return b.transaction(async (tx) => {
    const role = await roleAEcrire(tx, a, id);
    const nom = c.nom === undefined ? role.nom : lireNom(c.nom);
    const description = c.description === undefined ? role.description : lireDescription(c.description);
    const droits = c.droits === undefined ? role.droits : lireDroits(c.droits);
    if (!peutEcrireRole(a, droits, id)) throw new Refus(403, TA.escalade);
    await exigerNomLibre(tx, nom, id);
    await tx.ecrire("UPDATE admin_role SET nom = ?, description = ?, droits = ?, modifie_le = ? WHERE id = ?",
      nom, description, JSON.stringify(droits), maintenant.toISOString(), id);
    return (await lireRole(tx, id))!;
  });
}

/** Un rôle porté par un membre, ou nommé par une invitation en attente (ni acceptée, ni retirée, ni expirée), reste. */
export function retirerRole(b: Base, a: Acces, id: string, maintenant = new Date()): Promise<void> {
  return b.transaction(async (tx) => {
    const role = await roleAEcrire(tx, a, id);
    const invite = await tx.un(
      "SELECT 1 AS n FROM admin_invitation WHERE role = ? AND acceptee_le IS NULL AND retiree_le IS NULL AND valable_jusqua >= ?",
      id, maintenant.toISOString(),
    );
    if (role.membres > 0 || invite) throw new Refus(409, TA.rolePorte);
    await tx.ecrire("DELETE FROM admin_role WHERE id = ?", id);
  });
}
