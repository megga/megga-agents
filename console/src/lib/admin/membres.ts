import type { DatabaseSync } from "node:sqlite";
import { Refus } from "@/lib/agents";
import {
  aPuDonner,
  droitsEffectifs,
  lirePerimetre,
  peutToucherMembre,
  type Acces,
  type Perimetre,
} from "./acces";
import { SUPERADMIN } from "./droits";
import { lireRole, type Role } from "./roles";
import { TA } from "./textes";

// Les membres de l'admin : un compte de Better Auth, un rôle, un périmètre, une fin d'accès facultative, externe ou non.
// Un membre retiré est une ligne effacée (le journal garde la trace) ; le courriel et le nom se lisent dans la table user.

export type Membre = {
  utilisateur: string;
  courriel: string;
  nom: string;
  role: string;
  externe: boolean;
  perimetre: Perimetre;
  finAcces: string | null;
  ajoutePar: string | null;
  ajouteLe: string;
  derniereConnexion: string | null;
};

type Ligne = {
  utilisateur: string;
  courriel: string;
  nom: string;
  role: string;
  externe: number;
  perimetre: string | null;
  fin_acces: string | null;
  ajoute_par: string | null;
  ajoute_le: string;
  derniere: string | null;
};

const CHOIX = `SELECT m.*, COALESCE(u.email, '') AS courriel, COALESCE(u.name, '') AS nom, c.derniere
  FROM admin_membre m LEFT JOIN "user" u ON u.id = m.utilisateur LEFT JOIN compte_connexion c ON c.utilisateur = m.utilisateur`;

/** Un périmètre lu en base : NULL vaut « tous », une liste illisible ne donne aucun client. */
export function perimetreLu(json: string | null): Perimetre {
  if (json === null) return "tous";
  try {
    const v: unknown = JSON.parse(json);
    return Array.isArray(v) ? v.filter((c): c is string => typeof c === "string") : [];
  } catch {
    return [];
  }
}

function versMembre(l: Ligne): Membre {
  return {
    utilisateur: l.utilisateur,
    courriel: l.courriel,
    nom: l.nom,
    role: l.role,
    externe: !!l.externe,
    perimetre: perimetreLu(l.perimetre),
    finAcces: l.fin_acces,
    ajoutePar: l.ajoute_par,
    ajouteLe: l.ajoute_le,
    derniereConnexion: l.derniere,
  };
}

function lireMembre(db: DatabaseSync, utilisateur: string): Membre | undefined {
  const l = db.prepare(`${CHOIX} WHERE m.utilisateur = ?`).get(utilisateur) as Ligne | undefined;
  return l && versMembre(l);
}

/** Une fin d'accès AAAA-MM-JJ vaut jusqu'à la fin de ce jour, 23:59:59.999 UTC ; une date illisible ne laisse pas entrer. */
export function enCours(finAcces: string | null, maintenant: Date): boolean {
  if (finAcces === null) return true;
  return maintenant.getTime() <= new Date(`${finAcces}T23:59:59.999Z`).getTime();
}

/** Une vraie date AAAA-MM-JJ (ni 2026-02-30, ni 31.12.2026). */
export function estJour(v: unknown): v is string {
  return typeof v === "string" && /^\d{4}-\d{2}-\d{2}$/.test(v) && !Number.isNaN(Date.parse(v)) && new Date(v).toISOString().startsWith(v);
}

/** Une fin d'accès lue dans un corps : null, ou une vraie date AAAA-MM-JJ. */
export function lireFinAcces(v: unknown): string | null {
  if (v === null) return null;
  if (!estJour(v)) throw new Refus(400, TA.finAccesInvalide);
  return v;
}

export function membreEnCours(db: DatabaseSync, utilisateur: string, maintenant = new Date()): Membre | undefined {
  const m = lireMembre(db, utilisateur);
  return m && enCours(m.finAcces, maintenant) ? m : undefined;
}

/** L'accès d'un compte, relu à chaque requête : rien s'il n'est pas membre en cours ou si son rôle a disparu. */
export function accesDe(db: DatabaseSync, compte: { id: string; email: string; name: string }, maintenant = new Date()): Acces | undefined {
  const m = membreEnCours(db, compte.id, maintenant);
  const role = m && lireRole(db, m.role);
  if (!m || !role) return undefined;
  const superadmin = role.id === SUPERADMIN && !m.externe;
  // Un externe « tous » ne peut venir que d'une ligne écrite à la main : il ne voit alors aucun client.
  const perimetre: Perimetre = superadmin ? "tous" : m.externe && m.perimetre === "tous" ? [] : m.perimetre;
  return {
    utilisateur: compte.id,
    courriel: compte.email,
    nom: compte.name,
    role: { id: role.id, nom: role.nom },
    superadmin,
    externe: m.externe,
    perimetre,
    finAcces: superadmin ? null : m.finAcces,
    droits: droitsEffectifs(role.droits, m.externe, superadmin),
  };
}

export function listerMembres(db: DatabaseSync): Membre[] {
  return (db.prepare(`${CHOIX} ORDER BY m.ajoute_le, m.rowid`).all() as Ligne[]).map(versMembre);
}

/** Le rôle nommé dans un corps, ou 400. */
export function roleExistant(db: DatabaseSync, id: unknown): Role {
  const role = typeof id === "string" ? lireRole(db, id) : undefined;
  if (!role) throw new Refus(400, TA.roleInconnu);
  return role;
}

/** Les règles d'une ligne de membre ou d'une invitation : un externe a un périmètre et n'est jamais superadmin ; un superadmin a tout, sans fin. */
export function regleMembre(
  role: string,
  externe: boolean,
  perimetre: Perimetre,
  finAcces: string | null,
): { perimetre: Perimetre; finAcces: string | null } {
  if (externe && role === SUPERADMIN) throw new Refus(400, TA.externeSuperadmin);
  if (externe && (perimetre === "tous" || !perimetre.length)) throw new Refus(400, TA.externePerimetre);
  return role === SUPERADMIN ? { perimetre: "tous", finAcces: null } : { perimetre, finAcces };
}

export const perimetreEcrit = (p: Perimetre) => (p === "tous" ? null : JSON.stringify(p));

/** Ajoute (ou remplace) la ligne d'un membre ; les droits de qui l'ajoute sont vérifiés avant (invitation, commande). */
export function ajouterMembre(
  db: DatabaseSync,
  m: { utilisateur: string; role: string; externe: boolean; perimetre: Perimetre; finAcces: string | null; ajoutePar: string | null },
  maintenant = new Date(),
): Membre {
  roleExistant(db, m.role);
  const r = regleMembre(m.role, m.externe, m.perimetre, m.finAcces);
  db.prepare(
    `INSERT INTO admin_membre (utilisateur, role, externe, perimetre, fin_acces, ajoute_par, ajoute_le) VALUES (?, ?, ?, ?, ?, ?, ?)
     ON CONFLICT (utilisateur) DO UPDATE SET role = excluded.role, externe = excluded.externe, perimetre = excluded.perimetre,
       fin_acces = excluded.fin_acces, ajoute_par = excluded.ajoute_par, ajoute_le = excluded.ajoute_le`,
  ).run(m.utilisateur, m.role, m.externe ? 1 : 0, perimetreEcrit(r.perimetre), r.finAcces, m.ajoutePar, maintenant.toISOString());
  return lireMembre(db, m.utilisateur)!;
}

/** Les autres superadmins qui peuvent se connecter : en cours, et dont le compte n'est pas suspendu (comptes.ts). */
function autresSuperadmins(db: DatabaseSync, utilisateur: string, maintenant: Date): number {
  const lignes = db
    .prepare(
      `SELECT m.fin_acces FROM admin_membre m LEFT JOIN "user" u ON u.id = m.utilisateur
       WHERE m.role = ? AND m.externe = 0 AND m.utilisateur <> ? AND COALESCE(u.banned, 0) = 0`,
    )
    .all(SUPERADMIN, utilisateur) as { fin_acces: string | null }[];
  return lignes.filter((l) => enCours(l.fin_acces, maintenant)).length;
}

/**
 * Le membre que a veut changer. Sans être superadmin : ni sa propre ligne, ni un superadmin (peutToucherMembre),
 * ni un membre dont le rôle ou le périmètre dépasse les siens (il n'aurait pas pu l'inviter : aPuDonner).
 */
function membreAToucher(db: DatabaseSync, a: Acces, utilisateur: string): Membre {
  const cible = lireMembre(db, utilisateur);
  if (!cible) throw new Refus(404, TA.membreInconnu);
  if (!peutToucherMembre(a, cible) || !aPuDonner(a, lireRole(db, cible.role), cible.perimetre)) throw new Refus(403, TA.escalade);
  return cible;
}

function exigerAutreSuperadmin(db: DatabaseSync, cible: Membre, maintenant: Date): void {
  if (cible.role === SUPERADMIN && autresSuperadmins(db, cible.utilisateur, maintenant) < 1) throw new Refus(409, TA.dernierSuperadmin);
}

/** Un compte suspendu (comptes.ts) ne devient pas superadmin : il faudrait d'abord le réactiver. */
function exigerCompteActif(db: DatabaseSync, utilisateur: string): void {
  const u = db.prepare('SELECT banned FROM "user" WHERE id = ?').get(utilisateur) as { banned: number | null } | undefined;
  if (u?.banned) throw new Refus(409, TA.superadminSuspendu);
}

/** Corps : { role?, perimetre?, finAcces? } ; externe ne change pas (l'invitation le fixe). */
export function modifierMembre(db: DatabaseSync, a: Acces, utilisateur: string, corps: unknown, maintenant = new Date()): Membre {
  const cible = membreAToucher(db, a, utilisateur);
  const c = (corps && typeof corps === "object" ? corps : {}) as Record<string, unknown>;
  const role = c.role === undefined ? undefined : roleExistant(db, c.role);
  const perimetre = c.perimetre === undefined ? cible.perimetre : lirePerimetre(c.perimetre, cible.externe);
  if (!aPuDonner(a, role ?? lireRole(db, cible.role), perimetre)) throw new Refus(403, TA.escalade);
  const finAcces = c.finAcces === undefined ? cible.finAcces : lireFinAcces(c.finAcces);
  const nouveauRole = role?.id ?? cible.role;
  const r = regleMembre(nouveauRole, cible.externe, perimetre, finAcces);
  if (role?.id === SUPERADMIN) exigerCompteActif(db, utilisateur);
  if (nouveauRole !== SUPERADMIN) exigerAutreSuperadmin(db, cible, maintenant);
  db.prepare("UPDATE admin_membre SET role = ?, perimetre = ?, fin_acces = ? WHERE utilisateur = ?")
    .run(nouveauRole, perimetreEcrit(r.perimetre), r.finAcces, utilisateur);
  return lireMembre(db, utilisateur)!;
}

export function retirerMembre(db: DatabaseSync, a: Acces, utilisateur: string, maintenant = new Date()): void {
  const cible = membreAToucher(db, a, utilisateur);
  exigerAutreSuperadmin(db, cible, maintenant);
  db.prepare("DELETE FROM admin_membre WHERE utilisateur = ?").run(utilisateur);
}
