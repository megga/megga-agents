import "server-only";
import { betterAuth, type BetterAuthOptions } from "better-auth";
import { APIError } from "better-auth/api";
import { getMigrations } from "better-auth/db/migration";
import { nextCookies } from "better-auth/next-js";
import { admin } from "better-auth/plugins/admin";
import { headers } from "next/headers";
import { cache } from "react";
import { invitationPour } from "./admin/invitations";
import { noterConnexion } from "./admin/usage";
import { donnees, pret } from "./base";
import type { Base } from "./donnees/base";
import { estAdressePhoto } from "./photo-adresse";
import { T } from "./textes";

type Fournisseurs = NonNullable<BetterAuthOptions["socialProviders"]>;
type Env = Record<string, string | undefined>;

/**
 * L'inscription libre, seulement si on l'écrit (CONSOLE_INSCRIPTION=ouverte : le local et les parcours). Sinon, en ligne
 * notamment, un compte ne se crée que depuis la page d'un lien d'invitation, jeton à l'appui.
 */
export function inscriptionOuverte(env: Env = process.env): boolean {
  return env.CONSOLE_INSCRIPTION === "ouverte";
}

/** L'en-tête qui porte le jeton du lien d'invitation avec la demande d'inscription (rejoindre.tsx), jamais une adresse. */
export const ENTETE_INVITATION = "x-megga-invitation-token";

/** Le seul chemin qui crée un compte en mode invitation : l'inscription par courriel. */
const INSCRIPTION_COURRIEL = "/sign-up/email";

/** Google et Microsoft sont préparés ; chacun ne s'allume que si ses deux clés sont posées. */
export function fournisseurs(env: Env = process.env): Fournisseurs {
  const f: Fournisseurs = {};
  // En mode invitation, ni l'un ni l'autre ne crée de compte : ils ne servent qu'à un compte qui existe déjà.
  const fermee = inscriptionOuverte(env) ? {} : { disableSignUp: true };
  if (env.GOOGLE_CLIENT_ID && env.GOOGLE_CLIENT_SECRET) {
    f.google = { clientId: env.GOOGLE_CLIENT_ID, clientSecret: env.GOOGLE_CLIENT_SECRET, ...fermee };
  }
  if (env.MICROSOFT_CLIENT_ID && env.MICROSOFT_CLIENT_SECRET) {
    f.microsoft = { clientId: env.MICROSOFT_CLIENT_ID, clientSecret: env.MICROSOFT_CLIENT_SECRET, tenantId: env.MICROSOFT_TENANT_ID || "common", ...fermee };
  }
  return f;
}

export function fournisseursActifs(): ("google" | "microsoft")[] {
  return Object.keys(fournisseurs()) as ("google" | "microsoft")[];
}

/** La dernière connexion d'un compte, notée à chaque session créée ; une panne ne refuse jamais la connexion. */
async function noterSansBloquer(b: Base, utilisateur: string): Promise<void> {
  try {
    await noterConnexion(b, utilisateur);
  } catch (e) {
    console.error("dernière connexion :", e);
  }
}

/**
 * En mode invitation, avant toute création de compte : seule l'inscription par courriel passe, et seulement avec le jeton
 * d'une invitation en attente pour ce même courriel (en-tête ENTETE_INVITATION). Les courriels ne sont pas vérifiés : une
 * invitation en attente ne suffit pas, sinon qui connaît l'adresse d'un invité prendrait son compte avant lui. L'invitation
 * n'est pas consommée ici : elle s'accepte ensuite par sa route (POST /api/admin/invitation).
 */
async function verifierInvitation(b: Base, courriel: string, ctx: { path?: string; headers?: Headers } | null): Promise<void> {
  const jeton = ctx?.path === INSCRIPTION_COURRIEL ? ctx.headers?.get(ENTETE_INVITATION) : null;
  if (jeton && (await invitationPour(b, jeton, courriel))) return;
  throw new APIError("FORBIDDEN", { code: "INSCRIPTION_SUR_INVITATION", message: T.inscriptionSurInvitation });
}

/**
 * Le champ image d'un compte n'est jamais que null ou l'adresse de sa propre photo (photo-adresse.ts), posée par la route
 * vérifiée de Mon compte : /update-user de Better Auth, ouvert à toute session, ne peut y mettre une adresse d'ailleurs, une
 * data: URI ou la photo d'un autre compte. Le compte visé est celui de la session de la requête : sans session, rien d'autre
 * que null ne s'écrit.
 */
function verifierImageEcrite(u: Record<string, unknown>, ctx: { context?: { session?: { user?: { id?: string } } | null } } | null): void {
  if (!("image" in u) || u.image === null || u.image === undefined) return;
  const id = ctx?.context?.session?.user?.id;
  if (id && estAdressePhoto(u.image, id)) return;
  throw new APIError("BAD_REQUEST", { code: "IMAGE_REFUSEE", message: T.imageRefusee });
}

/**
 * Les quinze routes HTTP de l'extension admin de Better Auth (ban-user, impersonate-user, set-role…), toutes fermées : ses
 * rôles ne servent pas. L'extension ne sert qu'au bannissement, écrit côté serveur par les routes gardées de l'admin (comptes.ts).
 */
export const CHEMINS_ADMIN_FERMES: string[] = Object.values(admin().endpoints).map((e) => e.path);

/**
 * Les options de Better Auth sur une base donnée (celle de la console par défaut, une base en mémoire dans les essais).
 * L'extension admin refuse toute nouvelle session à un compte suspendu (BANNED_USER, T.compteSuspendu) ; nextCookies reste
 * la dernière extension. En mode invitation (inscriptionOuverte), un compte ne se crée que jeton à l'appui, et un compte
 * Google ou Microsoft ne se lie jamais de lui-même à un compte existant de même courriel.
 */
export function optionsAuth(b: Base = donnees(), env: Env = process.env): BetterAuthOptions {
  const ouverte = inscriptionOuverte(env);
  return {
    appName: "MEGGA",
    database: b.pourAuth() as BetterAuthOptions["database"],
    emailAndPassword: { enabled: true, minPasswordLength: 8, autoSignIn: true },
    socialProviders: fournisseurs(env),
    ...(ouverte ? {} : { account: { accountLinking: { enabled: false } } }),
    telemetry: { enabled: false },
    databaseHooks: {
      user: {
        // À la création, aucune image : celle d'un fournisseur (Google, Microsoft) ou d'un corps d'inscription n'est pas gardée,
        // sans refuser l'inscription ; la photo se pose ensuite depuis Mon compte.
        create: {
          before: async (u, ctx) => {
            if (!ouverte) await verifierInvitation(b, u.email, ctx);
            return u.image ? { data: { ...u, image: null } } : undefined;
          },
        },
        update: { before: async (u, ctx) => verifierImageEcrite(u, ctx as Parameters<typeof verifierImageEcrite>[1]) },
      },
      session: { create: { after: async (s) => noterSansBloquer(b, s.userId) } },
    },
    disabledPaths: CHEMINS_ADMIN_FERMES,
    plugins: [admin({ bannedUserMessage: T.compteSuspendu }), nextCookies()],
  };
}

const globale = globalThis as unknown as { authConsole?: ReturnType<typeof betterAuth>; migre?: Promise<void> };

export function auth() {
  if (!globale.authConsole) globale.authConsole = betterAuth(optionsAuth());
  return globale.authConsole;
}

/** Les tables de Better Auth, créées au premier appel (et complétées après une mise à jour). */
export function migrer(): Promise<void> {
  if (!globale.migre) {
    globale.migre = getMigrations(auth().options)
      .then(({ runMigrations }) => runMigrations())
      .catch((e) => {
        globale.migre = undefined; // un échec n'est pas gardé : la prochaine requête réessaie
        throw e;
      });
  }
  return globale.migre;
}

/**
 * La session de la requête en cours. Lue une fois par rendu (cache de React) : la coquille et la page de l'admin la
 * demandent chacune, et elle ne change pas pendant un même rendu.
 */
export const session = cache(async () => {
  await pret();
  return auth().api.getSession({ headers: await headers() });
});

export async function sessionDe(requete: Request) {
  await pret();
  return auth().api.getSession({ headers: requete.headers });
}
