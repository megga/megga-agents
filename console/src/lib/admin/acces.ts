import { Refus } from "@/lib/agents";
import { DROITS, DROITS_EXTERNE, estDroit, SUPERADMIN, type Droit } from "./droits";
import { TA } from "./textes";

// L'accès d'un membre : ses droits, son périmètre, et ce qu'il peut faire à l'équipe sans escalade.
// Fonctions pures : la garde (garde.ts) les applique à chaque requête, l'écran ne fait que les suivre.

/** L'identifiant d'un client, celui de l'atelier (atelier/app.py, ID). */
export const ID_CLIENT = /^[a-z0-9][a-z0-9-]{1,62}$/;

/** « tous » les clients, ou une liste d'identifiants. */
export type Perimetre = "tous" | readonly string[];

export type Acces = {
  utilisateur: string;
  courriel: string;
  nom: string;
  role: { id: string; nom: string };
  superadmin: boolean;
  externe: boolean;
  perimetre: Perimetre;
  finAcces: string | null;
  droits: ReadonlySet<Droit>; // déjà plafonnés pour un externe
};

/** Les droits d'un rôle tels qu'ils valent : un droit inconnu n'est jamais accordé, un externe n'en garde que trois. */
export function droitsEffectifs(droits: readonly string[], externe: boolean, superadmin: boolean): Set<Droit> {
  const connus: readonly Droit[] = superadmin ? DROITS : droits.filter(estDroit);
  return new Set(externe ? connus.filter((d) => DROITS_EXTERNE.includes(d)) : connus);
}

export function peut(a: Acces, d: Droit): boolean {
  return a.droits.has(d);
}

export function exiger(a: Acces, d: Droit): void {
  if (!peut(a, d)) throw new Refus(403, TA.sansDroit);
}

/** Un client se voit s'il est bien formé et dans le périmètre ; une adresse tapée à la main ne passe pas autrement. */
export function voitClient(a: Acces, client: string): boolean {
  if (!ID_CLIENT.test(client)) return false;
  return a.perimetre === "tous" || a.perimetre.includes(client);
}

/** Hors du périmètre, un client n'existe pas : 404, comme une adresse inconnue. */
export function exigerClient(a: Acces, client: string): void {
  if (!voitClient(a, client)) throw new Refus(404, TA.introuvable);
}

export function filtrerClients<T extends { id: string }>(a: Acces, liste: readonly T[]): T[] {
  return liste.filter((c) => voitClient(a, c.id));
}

/** Le périmètre tel qu'un corps de requête le donne ; un externe a toujours au moins un client. */
export function lirePerimetre(v: unknown, externe: boolean): Perimetre {
  if (v === "tous") {
    if (externe) throw new Refus(400, TA.externePerimetre);
    return "tous";
  }
  if (!Array.isArray(v) || !v.every((c) => typeof c === "string" && ID_CLIENT.test(c))) throw new Refus(400, TA.perimetreInvalide);
  const liste = [...new Set(v as string[])];
  if (externe && !liste.length) throw new Refus(400, TA.externePerimetre);
  return liste;
}

/** Le périmètre p tient-il dans celui du membre ? */
export function perimetreInclus(a: Acces, p: Perimetre): boolean {
  if (a.perimetre === "tous") return true;
  const sien = a.perimetre;
  return p !== "tous" && p.every((c) => sien.includes(c));
}

/**
 * Le périmètre d'un autre (membre ou invitation) tel qu'un membre le voit à l'écran : limité à une liste, il n'en voit
 * que les clients qu'il partage, les autres seulement comptés ; « tous » ne nomme aucun client.
 */
export function perimetreVu(a: Acces, p: Perimetre): "tous" | { clients: string[]; autres: number } {
  if (p === "tous") return "tous";
  const sien = a.perimetre;
  const clients = sien === "tous" ? [...p] : p.filter((c) => sien.includes(c));
  return { clients, autres: p.length - clients.length };
}

const droitsTenus = (a: Acces, droits: readonly Droit[]) => droits.every((d) => a.droits.has(d));

/** Sans être superadmin, on ne donne qu'un rôle dont tous les droits sont déjà les siens, et jamais le rôle superadmin. */
export function peutDonnerRole(a: Acces, role: { id: string; droits: readonly Droit[] }): boolean {
  if (a.superadmin) return true;
  return peut(a, "equipe.gerer") && role.id !== SUPERADMIN && droitsTenus(a, role.droits);
}

/**
 * Ce qu'on aurait pu donner soi-même (un rôle et un périmètre) : la seule écriture de la règle de non-escalade pour
 * inviter, toucher à un membre ou retirer une invitation (membres.ts, invitations.ts) ; l'écran la suit aussi.
 */
export function aPuDonner(a: Acces, role: { id: string; droits: readonly Droit[] } | undefined, p: Perimetre): boolean {
  return a.superadmin || (!!role && peutDonnerRole(a, role) && perimetreInclus(a, p));
}

/** Le rôle proposé d'abord à une invitation : le plus étroit (le moins de droits), jamais Superadmin ; à égalité, le premier. */
export function roleLePlusEtroit(roles: readonly { id: string; droits: readonly Droit[] }[]): string | undefined {
  let choisi: { id: string; droits: readonly Droit[] } | undefined;
  for (const r of roles) if (r.id !== SUPERADMIN && (!choisi || r.droits.length < choisi.droits.length)) choisi = r;
  return choisi?.id;
}

/**
 * Créer (roleId null) ou modifier un rôle : avec des droits qu'on a déjà, et jamais le rôle qu'on porte.
 * Un rôle vaut pour tous ses porteurs, quel que soit leur périmètre : limité à une liste de clients, on n'en écrit aucun.
 */
export function peutEcrireRole(a: Acces, droits: readonly Droit[], roleId: string | null): boolean {
  if (a.superadmin) return true;
  if (a.perimetre !== "tous") return false;
  if (roleId !== null && (roleId === a.role.id || roleId === SUPERADMIN)) return false;
  return peut(a, "equipe.gerer") && droitsTenus(a, droits);
}

/** Sans être superadmin, on ne touche ni à sa propre ligne ni à un superadmin. */
export function peutToucherMembre(a: Acces, cible: { utilisateur: string; role: string }): boolean {
  if (a.superadmin) return true;
  return peut(a, "equipe.gerer") && cible.utilisateur !== a.utilisateur && cible.role !== SUPERADMIN;
}

/** Suspendre un compte : jamais le sien ni celui d'un superadmin ; celui d'un membre, superadmin seulement. */
export function peutSuspendre(a: Acces, cible: { id: string; membre: { role: string } | null }): boolean {
  if (!peut(a, "comptes.gerer") || cible.id === a.utilisateur) return false;
  if (!cible.membre) return true;
  return a.superadmin && cible.membre.role !== SUPERADMIN;
}

/** Un membre limité à une liste ne crée pas de client : il naîtrait hors de son périmètre. */
export function peutCreerClient(a: Acces): boolean {
  return peut(a, "clients.creer") && a.perimetre === "tous";
}

const RAIL: readonly { href: string; texte: string; droit: Droit | null }[] = [
  { href: "/admin", texte: TA.vueEnsemble, droit: null },
  { href: "/admin/clients", texte: TA.clients, droit: "clients.voir" },
  { href: "/admin/alertes", texte: TA.alertes, droit: "clients.voir" },
  { href: "/admin/installations", texte: TA.installations, droit: "clients.voir" },
  { href: "/admin/comptes", texte: TA.comptes, droit: "comptes.voir" },
  { href: "/admin/tarifs", texte: TA.tarifs, droit: "couts.voir" },
  { href: "/admin/equipe", texte: TA.equipe, droit: "equipe.gerer" },
  { href: "/admin/journal", texte: TA.journal, droit: "journal.voir" },
];

/** Les entrées du rail que les droits du membre ouvrent ; la vue d'ensemble pour tout membre. */
export function entreesRail(a: Acces): { href: string; texte: string }[] {
  return RAIL.filter((e) => e.droit === null || peut(a, e.droit)).map(({ href, texte }) => ({ href, texte }));
}

/**
 * Les onglets de la fiche d'un client que les droits du membre ouvrent. Installation : seulement hors Cloudflare (la zone
 * de sa configuration n'est pas servie par la porte). periode : l'onglet garde la période de l'adresse (avecPeriode).
 */
export function ongletsClient(a: Acces, id: string, horsCloudflare: boolean): { href: string; texte: string; periode: boolean }[] {
  const fiche = `/admin/clients/${encodeURIComponent(id)}`;
  const onglets = [
    { href: fiche, texte: TA.suivi, periode: true, ouvert: peut(a, "clients.voir") },
    { href: `${fiche}/alertes`, texte: TA.alertes, periode: true, ouvert: peut(a, "clients.voir") },
    { href: `${fiche}/conversations`, texte: TA.conversations, periode: false, ouvert: peut(a, "conversations.lire") },
    { href: `${fiche}/versions`, texte: TA.versions, periode: false, ouvert: peut(a, "clients.voir") },
    { href: `${fiche}/acces`, texte: TA.acces, periode: false, ouvert: peut(a, "acces.gerer") || peut(a, "clients.piloter") },
    { href: `${fiche}/installation`, texte: TA.installation, periode: false, ouvert: horsCloudflare && peut(a, "clients.voir") },
  ];
  return onglets.filter((o) => o.ouvert).map(({ href, texte, periode }) => ({ href, texte, periode }));
}
