import "server-only";
import type { DatabaseSync } from "node:sqlite";
import { betterAuth, type BetterAuthOptions } from "better-auth";
import { getMigrations } from "better-auth/db/migration";
import { nextCookies } from "better-auth/next-js";
import { admin } from "better-auth/plugins/admin";
import { headers } from "next/headers";
import { noterConnexion } from "./admin/usage";
import { base } from "./base";
import { T } from "./textes";

type Fournisseurs = NonNullable<BetterAuthOptions["socialProviders"]>;

/** Google et Microsoft sont préparés ; chacun ne s'allume que si ses deux clés sont posées. */
export function fournisseurs(env: Record<string, string | undefined> = process.env): Fournisseurs {
  const f: Fournisseurs = {};
  if (env.GOOGLE_CLIENT_ID && env.GOOGLE_CLIENT_SECRET) {
    f.google = { clientId: env.GOOGLE_CLIENT_ID, clientSecret: env.GOOGLE_CLIENT_SECRET };
  }
  if (env.MICROSOFT_CLIENT_ID && env.MICROSOFT_CLIENT_SECRET) {
    f.microsoft = { clientId: env.MICROSOFT_CLIENT_ID, clientSecret: env.MICROSOFT_CLIENT_SECRET, tenantId: env.MICROSOFT_TENANT_ID || "common" };
  }
  return f;
}

export function fournisseursActifs(): ("google" | "microsoft")[] {
  return Object.keys(fournisseurs()) as ("google" | "microsoft")[];
}

/** La dernière connexion d'un compte, notée à chaque session créée ; une panne ne refuse jamais la connexion. */
function noterSansBloquer(db: DatabaseSync, utilisateur: string): void {
  try {
    noterConnexion(db, utilisateur);
  } catch (e) {
    console.error("dernière connexion :", e);
  }
}

/**
 * Les quinze routes HTTP de l'extension admin de Better Auth (ban-user, impersonate-user, set-role…), toutes fermées : ses
 * rôles ne servent pas. L'extension ne sert qu'au bannissement, écrit côté serveur par les routes gardées de l'admin (comptes.ts).
 */
export const CHEMINS_ADMIN_FERMES: string[] = Object.values(admin().endpoints).map((e) => e.path);

/**
 * Les options de Better Auth sur une base donnée (celle de la console par défaut, une base en mémoire dans les essais).
 * L'extension admin refuse toute nouvelle session à un compte suspendu (BANNED_USER, T.compteSuspendu) ; nextCookies reste
 * la dernière extension.
 */
export function optionsAuth(db: DatabaseSync = base()): BetterAuthOptions {
  return {
    appName: "MEGGA",
    database: db,
    emailAndPassword: { enabled: true, minPasswordLength: 8, autoSignIn: true },
    socialProviders: fournisseurs(),
    telemetry: { enabled: false },
    databaseHooks: { session: { create: { after: async (s) => noterSansBloquer(db, s.userId) } } },
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

export async function session() {
  await migrer();
  return auth().api.getSession({ headers: await headers() });
}

export async function sessionDe(requete: Request) {
  await migrer();
  return auth().api.getSession({ headers: requete.headers });
}
