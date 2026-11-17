import "server-only";
import { betterAuth, type BetterAuthOptions } from "better-auth";
import { getMigrations } from "better-auth/db/migration";
import { nextCookies } from "better-auth/next-js";
import { headers } from "next/headers";
import { base } from "./base";

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

function options(): BetterAuthOptions {
  return {
    appName: "MEGGA",
    database: base(),
    emailAndPassword: { enabled: true, minPasswordLength: 8, autoSignIn: true },
    socialProviders: fournisseurs(),
    telemetry: { enabled: false },
    plugins: [nextCookies()],
  };
}

const globale = globalThis as unknown as { authConsole?: ReturnType<typeof betterAuth>; migre?: Promise<void> };

export function auth() {
  if (!globale.authConsole) globale.authConsole = betterAuth(options());
  return globale.authConsole;
}

/** Les tables de Better Auth, créées au premier appel (et complétées après une mise à jour). */
export function migrer(): Promise<void> {
  if (!globale.migre) {
    globale.migre = getMigrations(auth().options).then(({ runMigrations }) => runMigrations());
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
