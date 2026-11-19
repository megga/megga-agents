import { Refus } from "@/lib/agents";
import type { Base } from "@/lib/donnees/base";
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
// Chaque écriture lit puis écrit dans une même transaction : il reste toujours un superadmin en cours, et le rôle donné existe
// au moment de l'écriture, même quand deux requêtes arrivent à la fois.

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

async function lireMembre(b: Base, utilisateur: string): Promise<Membre | undefined> {
  const l = await b.un<Ligne>(`${CHOIX} WHERE m.utilisateur = ?`, utilisateur);
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

export async function membreEnCours(b: Base, utilisateur: string, maintenant = new Date()): Promise<Membre | undefined> {
  const m = await lireMembre(b, utilisateur);
  return m && enCours(m.finAcces, maintenant) ? m : undefined;
}

/** L'accès d'un compte, relu à chaque requête : rien s'il n'est pas membre en cours ou si son rôle a disparu. */
export async function accesDe(b: Base, compte: { id: string; email: string; name: string }, maintenant = new Date()): Promise<Acces | undefined> {
  const m = await membreEnCours(b, compte.id, maintenant);
  const role = m && (await lireRole(b, m.role));
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

export async function listerMembres(b: Base): Promise<Membre[]> {
  return (await b.tous<Ligne>(`${CHOIX} ORDER BY m.ajoute_le, m.utilisateur`)).map(versMembre);
}

/** Le rôle nommé dans un corps, ou 400. */
export async function roleExistant(b: Base, id: unknown): Promise<Role> {
  const role = typeof id === "string" ? await lireRole(b, id) : undefined;
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
  b: Base,
  m: { utilisateur: string; role: string; externe: boolean; perimetre: Perimetre; finAcces: string | null; ajoutePar: string | null },
  maintenant = new Date(),
): Promise<Membre> {
  return b.transaction(async (tx) => {
    await roleExistant(tx, m.role);
    const r = regleMembre(m.role, m.externe, m.perimetre, m.finAcces);
    await tx.ecrire(
      `INSERT INTO admin_membre (utilisateur, role, externe, perimetre, fin_acces, ajoute_par, ajoute_le) VALUES (?, ?, ?, ?, ?, ?, ?)
       ON CONFLICT (utilisateur) DO UPDATE SET role = excluded.role, externe = excluded.externe, perimetre = excluded.perimetre,
         fin_acces = excluded.fin_acces, ajoute_par = excluded.ajoute_par, ajoute_le = excluded.ajoute_le`,
      m.utilisateur, m.role, m.externe ? 1 : 0, perimetreEcrit(r.perimetre), r.finAcces, m.ajoutePar, maintenant.toISOString(),
    );
    return (await lireMembre(tx, m.utilisateur))!;
  });
}

/** Les autres superadmins qui peuvent se connecter : en cours, et dont le compte n'est pas suspendu (comptes.ts). */
async function autresSuperadmins(b: Base, utilisateur: string, maintenant: Date): Promise<number> {
  const lignes = await b.tous<{ fin_acces: string | null }>(
    `SELECT m.fin_acces FROM admin_membre m LEFT JOIN "user" u ON u.id = m.utilisateur
     WHERE m.role = ? AND m.externe = 0 AND m.utilisateur <> ? AND u.banned IS NOT TRUE`,
    SUPERADMIN, utilisateur,
  );
  return lignes.filter((l) => enCours(l.fin_acces, maintenant)).length;
}

/**
 * Le membre que a veut changer. Sans être superadmin : ni sa propre ligne, ni un superadmin (peutToucherMembre),
 * ni un membre dont le rôle ou le périmètre dépasse les siens (il n'aurait pas pu l'inviter : aPuDonner).
 */
async function membreAToucher(b: Base, a: Acces, utilisateur: string): Promise<Membre> {
  const cible = await lireMembre(b, utilisateur);
  if (!cible) throw new Refus(404, TA.membreInconnu);
  if (!peutToucherMembre(a, cible) || !aPuDonner(a, await lireRole(b, cible.role), cible.perimetre)) throw new Refus(403, TA.escalade);
  return cible;
}

async function exigerAutreSuperadmin(b: Base, cible: Membre, maintenant: Date): Promise<void> {
  if (cible.role === SUPERADMIN && (await autresSuperadmins(b, cible.utilisateur, maintenant)) < 1) throw new Refus(409, TA.dernierSuperadmin);
}

/** Un compte suspendu (comptes.ts) ne devient pas superadmin : il faudrait d'abord le réactiver. */
async function exigerCompteActif(b: Base, utilisateur: string): Promise<void> {
  const u = await b.un<{ banned: number | boolean | null }>('SELECT banned FROM "user" WHERE id = ?', utilisateur);
  if (u?.banned) throw new Refus(409, TA.superadminSuspendu);
}

/** Corps : { role?, perimetre?, finAcces? } ; externe ne change pas (l'invitation le fixe). */
export function modifierMembre(b: Base, a: Acces, utilisateur: string, corps: unknown, maintenant = new Date()): Promise<Membre> {
  const c = (corps && typeof corps === "object" ? corps : {}) as Record<string, unknown>;
  return b.transaction(async (tx) => {
    const cible = await membreAToucher(tx, a, utilisateur);
    const role = c.role === undefined ? undefined : await roleExistant(tx, c.role);
    const perimetre = c.perimetre === undefined ? cible.perimetre : lirePerimetre(c.perimetre, cible.externe);
    if (!aPuDonner(a, role ?? (await lireRole(tx, cible.role)), perimetre)) throw new Refus(403, TA.escalade);
    const finAcces = c.finAcces === undefined ? cible.finAcces : lireFinAcces(c.finAcces);
    const nouveauRole = role?.id ?? cible.role;
    const r = regleMembre(nouveauRole, cible.externe, perimetre, finAcces);
    if (role?.id === SUPERADMIN) await exigerCompteActif(tx, utilisateur);
    if (nouveauRole !== SUPERADMIN) await exigerAutreSuperadmin(tx, cible, maintenant);
    await tx.ecrire("UPDATE admin_membre SET role = ?, perimetre = ?, fin_acces = ? WHERE utilisateur = ?",
      nouveauRole, perimetreEcrit(r.perimetre), r.finAcces, utilisateur);
    return (await lireMembre(tx, utilisateur))!;
  });
}

export function retirerMembre(b: Base, a: Acces, utilisateur: string, maintenant = new Date()): Promise<void> {
  return b.transaction(async (tx) => {
    const cible = await membreAToucher(tx, a, utilisateur);
    await exigerAutreSuperadmin(tx, cible, maintenant);
    await tx.ecrire("DELETE FROM admin_membre WHERE utilisateur = ?", utilisateur);
  });
}
