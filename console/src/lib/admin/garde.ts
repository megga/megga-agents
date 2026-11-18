import "server-only";
import type { DatabaseSync } from "node:sqlite";
import { notFound, redirect } from "next/navigation";
import { connection } from "next/server";
import { Refus } from "@/lib/agents";
import { session, sessionDe } from "@/lib/auth";
import { base } from "@/lib/base";
import { exiger, exigerClient, peut, voitClient, type Acces } from "./acces";
import { RefusChamps } from "./atelier";
import type { Droit } from "./droits";
import { noter } from "./journal";
import { accesDe } from "./membres";
import { TA } from "./textes";

// Le seul point de contrôle de l'admin : chaque route de /api/admin est exportée par garde ou gardeSession,
// chaque page appelle gardePage. Rien n'est décidé par l'écran seul ; un droit retiré vaut à la requête suivante.

/** La marque d'une route gardée (tests/admin/routes.test.ts vérifie que chaque route la porte). */
export const GARDE = Symbol("garde");

/**
 * detail : ce que le journal garde du geste (puis nettoyé et coupé), au lieu du corps entier ; pour un corps qui porte ce
 * qu'un autre membre ne doit pas lire au journal (les tarifs d'achat, réservés à couts.voir).
 */
export type Regle<P> = {
  droit: Droit;
  client?: (p: P) => string;
  action?: string;
  cible?: (p: P, corps: unknown) => string | null;
  detail?: (corps: unknown, params: P) => unknown;
};
export type Contexte<P> = { acces: Acces; params: P; corps: unknown; requete: Request; db: DatabaseSync };
export type Gestionnaire<P> = ((requete: Request, ctx: { params: Promise<P> }) => Promise<Response>) & { [GARDE]: true };

type Compte = { id: string; email: string; name: string };

/** Une écriture ne vient que de la console : l'origine de la requête, ou celle de BETTER_AUTH_URL (derrière un relais). */
export function origineAdmise(requete: Request, env: Record<string, string | undefined> = process.env): boolean {
  const origine = requete.headers.get("origin");
  if (!origine) return false;
  const admises = [new URL(requete.url).origin];
  try {
    if (env.BETTER_AUTH_URL) admises.push(new URL(env.BETTER_AUTH_URL).origin);
  } catch {
    // une adresse illisible n'admet rien de plus
  }
  return admises.includes(origine);
}

const lecture = (requete: Request) => requete.method === "GET" || requete.method === "HEAD";

async function lireCorps(requete: Request): Promise<unknown> {
  return lecture(requete) ? null : requete.json().catch(() => null);
}

/** Un refus en JSON : sa phrase, et pour un refus de l'atelier, ses messages champ par champ (ErreursChamps). */
function reponseRefus(e: Refus): Response {
  const champs = e instanceof RefusChamps && e.champs.length ? { champs: e.champs } : {};
  return Response.json({ erreur: e.message, ...champs }, { status: e.statut });
}

/**
 * traiter rend une Response (rendue telle quelle), une valeur (en JSON) ou rien (204, comme un retrait) ;
 * un Refus, son statut ; le reste, 500 sans détail.
 */
async function issue(faire: () => Promise<unknown>, noterIssue: (resultat: string) => void): Promise<Response> {
  try {
    const r = await faire();
    const reponse = r instanceof Response ? r : r === undefined ? new Response(null, { status: 204 }) : Response.json(r);
    noterIssue(reponse.ok ? "ok" : `refuse ${reponse.status}`);
    return reponse;
  } catch (e) {
    if (e instanceof Refus) {
      noterIssue(`refuse ${e.statut}`);
      return reponseRefus(e);
    }
    console.error("admin :", e);
    noterIssue("erreur");
    return Response.json({ erreur: TA.erreurInterne }, { status: 500 });
  }
}

/** Note une issue ; une panne du journal part à console.error et ne change jamais la réponse du geste. */
function journaliste(db: DatabaseSync, compte: Compte, action: string | undefined, cible: string | null, detail: () => unknown) {
  return (resultat: string) => {
    if (!action) return;
    try {
      noter(db, { qui: compte.id, courriel: compte.email, action, cible, resultat, detail: detail() });
    } catch (e) {
      console.error("journal de l'admin :", e);
    }
  };
}

function cibleDe<P>(regle: Regle<P>, params: P, corps: unknown): string | null {
  try {
    if (regle.cible) return regle.cible(params, corps);
    return regle.client ? `client:${regle.client(params)}` : null;
  } catch {
    return null;
  }
}

const marquer = <P>(f: (requete: Request, ctx: { params: Promise<P> }) => Promise<Response>): Gestionnaire<P> =>
  Object.assign(f, { [GARDE]: true as const });

/** Ordre : session (401), membre en cours (404), hors GET l'origine (403), le droit (403), le client (404), puis traiter. */
export function garde<P extends Record<string, string>>(regle: Regle<P>, traiter: (c: Contexte<P>) => Promise<unknown>): Gestionnaire<P> {
  return marquer<P>(async (requete, ctx) => {
    const s = await sessionDe(requete);
    if (!s) return Response.json({ erreur: TA.connectezVous }, { status: 401 });
    const db = base();
    const params = await ctx.params;
    const corps = await lireCorps(requete);
    let membre = false; // un inconnu (404) ne laisse aucun détail au journal
    const detail = () => (!membre ? null : regle.detail ? regle.detail(corps, params) : corps);
    const noterIssue = journaliste(db, s.user, regle.action, cibleDe(regle, params, corps), detail);
    return issue(async () => {
      const acces = accesDe(db, s.user);
      if (!acces) throw new Refus(404, TA.introuvable);
      membre = true;
      if (!lecture(requete) && !origineAdmise(requete)) throw new Refus(403, TA.origineRefusee);
      exiger(acces, regle.droit);
      if (regle.client) exigerClient(acces, regle.client(params));
      return traiter({ acces, params, corps, requete, db });
    }, noterIssue);
  });
}

/**
 * Pour qui n'est pas encore membre (rejoindre par une invitation) : une session et la bonne origine suffisent.
 * Ouverte à tout compte : le journal ne note du corps que ce que regle.detail en garde, jamais le corps entier.
 */
export function gardeSession<P extends Record<string, string>>(
  regle: { action: string; detail: (corps: unknown) => unknown },
  traiter: (c: { compte: Compte; params: P; corps: unknown; db: DatabaseSync }) => Promise<unknown>,
): Gestionnaire<P> {
  return marquer<P>(async (requete, ctx) => {
    const s = await sessionDe(requete);
    if (!s) return Response.json({ erreur: TA.connectezVous }, { status: 401 });
    const db = base();
    const params = await ctx.params;
    const corps = await lireCorps(requete);
    const compte = { id: s.user.id, email: s.user.email, name: s.user.name };
    return issue(async () => {
      if (!lecture(requete) && !origineAdmise(requete)) throw new Refus(403, TA.origineRefusee);
      return traiter({ compte, params, corps, db });
    }, journaliste(db, compte, regle.action, null, () => regle.detail(corps)));
  });
}

/**
 * Pour une page : sans session, la connexion puis retour à /admin ; sinon 404 pour qui n'a pas le droit ou le client.
 * connection() d'abord : une page de l'admin ne se rend qu'à la requête, jamais dans un préchargement (la fin d'accès
 * se compare à l'heure du moment, et un droit retiré doit valoir tout de suite).
 */
export async function gardePage(droit?: Droit, client?: string): Promise<Acces> {
  await connection();
  const s = await session();
  if (!s) redirect("/connexion?retour=/admin");
  const a = accesDe(base(), s.user);
  if (!a || (droit && !peut(a, droit)) || (client !== undefined && !voitClient(a, client))) notFound();
  return a;
}
