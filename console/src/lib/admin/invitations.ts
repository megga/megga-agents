import { createHash, randomBytes, randomUUID } from "node:crypto";
import { Refus } from "@/lib/agents";
import type { Base } from "@/lib/donnees/base";
import { aPuDonner, lirePerimetre, type Acces, type Perimetre } from "./acces";
import { SUPERADMIN } from "./droits";
import {
  ajouterMembre,
  lireFinAcces,
  membreEnCours,
  perimetreEcrit,
  perimetreLu,
  regleMembre,
  roleExistant,
  type Membre,
} from "./membres";
import { lireRole } from "./roles";
import { TA } from "./textes";

// Les invitations : un lien /admin/invitation/<jeton>, montré une fois ; la base n'en garde que l'empreinte (SHA-256).
// Valable 7 jours, une seule fois, retirable. Inconnue, expirée, acceptée ou retirée : la même réponse, 404.
// Créer, accepter et retirer lisent puis écrivent dans une même transaction : une invitation ne sert qu'une fois, et le rôle
// qu'elle donne est relu au moment de l'écrire. L'accès de l'auteur, lui, est celui que garde a lu pour la requête.

export const DUREE_INVITATION_JOURS = 7;

export type Invitation = {
  id: string;
  courriel: string;
  role: string;
  externe: boolean;
  perimetre: Perimetre;
  finAcces: string | null;
  valableJusqua: string;
  creeePar: string | null;
  creeeLe: string;
};

type Ligne = {
  id: string;
  courriel: string;
  role: string;
  externe: number;
  perimetre: string | null;
  fin_acces: string | null;
  valable_jusqua: string;
  creee_par: string | null;
  creee_le: string;
};

const JETON = /^[A-Za-z0-9_-]{43}$/;
const COURRIEL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const EN_ATTENTE = "acceptee_le IS NULL AND retiree_le IS NULL AND valable_jusqua >= ?";

export function empreinte(jeton: string): string {
  return createHash("sha256").update(jeton).digest("hex");
}

/** Les courriels se comparent en minuscules, sans espaces autour. */
const normaliser = (courriel: string) => courriel.trim().toLowerCase();

function versInvitation(l: Ligne): Invitation {
  return {
    id: l.id,
    courriel: l.courriel,
    role: l.role,
    externe: !!l.externe,
    perimetre: perimetreLu(l.perimetre),
    finAcces: l.fin_acces,
    valableJusqua: l.valable_jusqua,
    creeePar: l.creee_par,
    creeeLe: l.creee_le,
  };
}

function lireCourriel(v: unknown): string {
  const courriel = typeof v === "string" ? normaliser(v) : "";
  if (!COURRIEL.test(courriel)) throw new Refus(400, TA.courrielInvalide);
  return courriel;
}

/** a === null : la commande lancée sur le serveur ; sinon, un membre qui ne donne ni plus de droits ni plus de clients qu'il n'en a. */
export function creerInvitation(b: Base, a: Acces | null, corps: unknown, maintenant = new Date()): Promise<{ invitation: Invitation; jeton: string; lien: string }> {
  const c = (corps && typeof corps === "object" ? corps : {}) as Record<string, unknown>;
  return b.transaction(async (tx) => {
    const courriel = lireCourriel(c.courriel);
    const role = await roleExistant(tx, c.role);
    const externe = c.externe === true;
    const regle = regleMembre(role.id, externe, lirePerimetre(c.perimetre ?? "tous", externe), lireFinAcces(c.finAcces ?? null));
    // Le rôle donné, relu dans la transaction, contre l'accès de l'auteur lu par garde pour cette requête.
    if (a && !aPuDonner(a, role, regle.perimetre)) throw new Refus(403, TA.escalade);
    const jeton = randomBytes(32).toString("base64url");
    const id = "in_" + randomUUID().replace(/-/g, "").slice(0, 20);
    const valable = new Date(maintenant.getTime() + DUREE_INVITATION_JOURS * 24 * 3600 * 1000);
    await tx.ecrire(
      `INSERT INTO admin_invitation (id, empreinte, courriel, role, externe, perimetre, fin_acces, valable_jusqua, creee_par, creee_le)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      id, empreinte(jeton), courriel, role.id, externe ? 1 : 0, perimetreEcrit(regle.perimetre), regle.finAcces, valable.toISOString(),
      a?.utilisateur ?? null, maintenant.toISOString(),
    );
    const invitation = versInvitation((await tx.un<Ligne>("SELECT * FROM admin_invitation WHERE id = ?", id))!);
    return { invitation, jeton, lien: `/admin/invitation/${jeton}` };
  });
}

export async function invitationsEnAttente(b: Base, maintenant = new Date()): Promise<Invitation[]> {
  const lignes = await b.tous<Ligne>(`SELECT * FROM admin_invitation WHERE ${EN_ATTENTE} ORDER BY creee_le DESC, id DESC`, maintenant.toISOString());
  return lignes.map(versInvitation);
}

export async function lireInvitation(b: Base, jeton: string, maintenant = new Date()): Promise<Invitation | undefined> {
  if (!JETON.test(jeton)) return undefined;
  const l = await b.un<Ligne>(`SELECT * FROM admin_invitation WHERE empreinte = ? AND ${EN_ATTENTE}`, empreinte(jeton), maintenant.toISOString());
  return l && versInvitation(l);
}

/** Vrai si ce jeton est celui d'une invitation en attente pour ce courriel (l'inscription en mode invitation, auth.ts). */
export async function invitationPour(b: Base, jeton: string, courriel: string, maintenant = new Date()): Promise<boolean> {
  const i = await lireInvitation(b, jeton, maintenant);
  return i !== undefined && normaliser(courriel) === i.courriel;
}

export function accepterInvitation(b: Base, jeton: string, compte: { id: string; email: string }, maintenant = new Date()): Promise<Membre> {
  return b.transaction(async (tx) => {
    const i = await lireInvitation(tx, jeton, maintenant);
    if (!i) throw new Refus(404, TA.invitationInvalide);
    if (normaliser(compte.email) !== i.courriel) throw new Refus(403, TA.autreCourriel);
    if (await membreEnCours(tx, compte.id, maintenant)) throw new Refus(409, TA.dejaMembre);
    const membre = await ajouterMembre(tx, { utilisateur: compte.id, role: i.role, externe: i.externe, perimetre: i.perimetre,
      finAcces: i.finAcces, ajoutePar: i.creeePar }, maintenant);
    await tx.ecrire("UPDATE admin_invitation SET acceptee_le = ?, acceptee_par = ? WHERE id = ?", maintenant.toISOString(), compte.id, i.id);
    return membre;
  });
}

/** Sans être superadmin, on ne retire que l'invitation qu'on aurait pu faire. */
export function retirerInvitation(b: Base, a: Acces, id: string, maintenant = new Date()): Promise<void> {
  return b.transaction(async (tx) => {
    const l = await tx.un<Ligne>(`SELECT * FROM admin_invitation WHERE id = ? AND ${EN_ATTENTE}`, id, maintenant.toISOString());
    if (!l) throw new Refus(404, TA.invitationInvalide);
    const i = versInvitation(l);
    if (!aPuDonner(a, await lireRole(tx, i.role), i.perimetre)) throw new Refus(403, TA.escalade);
    await tx.ecrire("UPDATE admin_invitation SET retiree_le = ? WHERE id = ?", maintenant.toISOString(), id);
  });
}

/** Pour la commande des premiers superadmins : le lien complet, sur l'origine de la console. */
export async function inviterSuperadmin(b: Base, courriel: string, origine: string, maintenant = new Date()): Promise<string> {
  const { lien } = await creerInvitation(b, null, { courriel, role: SUPERADMIN, externe: false, perimetre: "tous", finAcces: null }, maintenant);
  return origine.replace(/\/+$/, "") + lien;
}

/** Ce que montre la page du lien. */
export function etatInvitation(i: Invitation | undefined, courrielSession: string | null): "invalide" | "rejoindre" | "autre_courriel" | "sans_session" {
  if (!i) return "invalide";
  if (courrielSession === null) return "sans_session";
  return normaliser(courrielSession) === i.courriel ? "rejoindre" : "autre_courriel";
}
