import { betterAuth } from "better-auth";
import { beforeEach, describe, expect, it } from "vitest";
import { creerInvitation, lireInvitation } from "@/lib/admin/invitations";
import { ENTETE_INVITATION, inscriptionOuverte, optionsAuth } from "@/lib/auth";
import type { Base } from "@/lib/donnees/base";
import { T } from "@/lib/textes";
import { baseEssai } from "./admin/aides";

// L'inscription sur invitation (CONSOLE_INSCRIPTION) : en ligne, un compte ne se crée qu'avec le lien d'invitation en main.
// Les courriels ne sont pas vérifiés : une invitation en attente pour un courriel ne suffit pas, il faut son jeton.

const SECRET = "secret-des-essais-de-la-console-assez-long";
const INVITATION = { CONSOLE_INSCRIPTION: "invitation" };
const OUVERTE = { CONSOLE_INSCRIPTION: "ouverte" };

let db: Base;
beforeEach(async () => {
  db = await baseEssai();
});

const authEn = (env: Record<string, string | undefined>) => betterAuth({ ...optionsAuth(db, env), secret: SECRET });
const corps = (email: string) => ({ name: "Chef", email, password: "motdepasse" });
const inviter = async (courriel: string) => (await creerInvitation(db, null, { courriel, role: "superadmin" })).jeton;
const comptes = async () => (await db.tous<{ email: string }>('SELECT email FROM "user" ORDER BY email')).map((u) => u.email);

/** Le refus de Better Auth, tel que le client le reçoit : son statut et son corps. */
async function refus(p: Promise<unknown>): Promise<{ status: unknown; body: unknown }> {
  try {
    await p;
  } catch (e) {
    const { status, body } = e as { status: unknown; body: unknown };
    return { status, body };
  }
  throw new Error("aucun refus");
}

describe("le mode d'inscription", () => {
  it("est sur invitation sauf si CONSOLE_INSCRIPTION vaut ouverte", () => {
    expect(inscriptionOuverte({})).toBe(false);
    expect(inscriptionOuverte({ CONSOLE_INSCRIPTION: "invitation" })).toBe(false);
    expect(inscriptionOuverte({ CONSOLE_INSCRIPTION: "Ouverte" })).toBe(false);
    expect(inscriptionOuverte({ CONSOLE_INSCRIPTION: "ouverte" })).toBe(true);
  });
});

describe("l'inscription sur invitation", () => {
  it("refuse une inscription sans invitation", async () => {
    const r = await refus(authEn(INVITATION).api.signUpEmail({ body: corps("chef@megga.test") }));
    expect(r.status).toBe("FORBIDDEN");
    expect(r.body).toMatchObject({ code: "INSCRIPTION_SUR_INVITATION", message: T.inscriptionSurInvitation });
    expect(await comptes()).toEqual([]);
  });

  it("refuse une inscription pour un courriel invité, sans le jeton de son lien", async () => {
    await inviter("chef@megga.test");
    const r = await refus(authEn(INVITATION).api.signUpEmail({ body: corps("chef@megga.test") }));
    expect(r.status).toBe("FORBIDDEN");
    expect(await comptes()).toEqual([]);
  });

  it("refuse un jeton valable pour un autre courriel", async () => {
    const jeton = await inviter("chef@megga.test");
    const auth = authEn(INVITATION);
    const r = await refus(auth.api.signUpEmail({ body: corps("intrus@megga.test"), headers: new Headers({ [ENTETE_INVITATION]: jeton }) }));
    expect(r.status).toBe("FORBIDDEN");
    expect(await comptes()).toEqual([]);
  });

  it("refuse un jeton inconnu ou mal formé", async () => {
    await inviter("chef@megga.test");
    const auth = authEn(INVITATION);
    for (const jeton of ["a".repeat(43), "court", ""]) {
      const r = await refus(auth.api.signUpEmail({ body: corps("chef@megga.test"), headers: new Headers({ [ENTETE_INVITATION]: jeton }) }));
      expect(r.status, jeton).toBe("FORBIDDEN");
    }
    expect(await comptes()).toEqual([]);
  });

  it("accepte le jeton de l'invitation de ce courriel, puis l'invitation reste à accepter par sa route", async () => {
    const jeton = await inviter("chef@megga.test");
    const auth = authEn(INVITATION);
    const { user } = await auth.api.signUpEmail({ body: corps("Chef@Megga.test"), headers: new Headers({ [ENTETE_INVITATION]: jeton }) });
    expect(user.email).toBe("chef@megga.test");
    expect(await comptes()).toEqual(["chef@megga.test"]);
    expect(await lireInvitation(db, jeton)).toMatchObject({ courriel: "chef@megga.test" }); // toujours en attente
    expect(await db.tous("SELECT * FROM admin_membre")).toEqual([]); // le compte existe, il n'est pas encore membre
  });

  it("passe aussi par HTTP, comme la page du lien : le jeton dans l'en-tête de la requête", async () => {
    const jeton = await inviter("chef@megga.test");
    const auth = betterAuth({ ...optionsAuth(db, INVITATION), secret: SECRET, baseURL: "http://localhost:3000" });
    const inscrire = (entetes: Record<string, string>) =>
      auth.handler(new Request("http://localhost:3000/api/auth/sign-up/email", {
        method: "POST",
        headers: { "content-type": "application/json", origin: "http://localhost:3000", ...entetes },
        body: JSON.stringify(corps("chef@megga.test")),
      }));
    const sans = await inscrire({});
    expect(sans.status).toBe(403);
    expect(await sans.json()).toMatchObject({ code: "INSCRIPTION_SUR_INVITATION", message: T.inscriptionSurInvitation });
    expect(await comptes()).toEqual([]);
    expect((await inscrire({ [ENTETE_INVITATION]: jeton })).status).toBe(200);
    expect(await comptes()).toEqual(["chef@megga.test"]);
  });

  it("Google et Microsoft ne créent pas de compte et ne se lient jamais d'eux-mêmes, même jeton à l'appui", async () => {
    const jeton = await inviter("chef@megga.test");
    const env = { ...INVITATION, GOOGLE_CLIENT_ID: "a", GOOGLE_CLIENT_SECRET: "b", MICROSOFT_CLIENT_ID: "c", MICROSOFT_CLIENT_SECRET: "d" };
    const o = optionsAuth(db, env);
    expect(o.account?.accountLinking?.enabled).toBe(false);
    expect(o.socialProviders?.google).toMatchObject({ disableSignUp: true });
    expect(o.socialProviders?.microsoft).toMatchObject({ disableSignUp: true });
    // Le crochet de création refuse tout ce qui ne vient pas de l'inscription par courriel, avec ou sans en-tête.
    const avant = o.databaseHooks!.user!.create!.before!;
    const utilisateur = { id: "u", name: "Chef", email: "chef@megga.test", emailVerified: true, createdAt: new Date(), updatedAt: new Date() };
    for (const path of ["/callback/:id", "/sign-in/social"]) {
      const ctx = { path, headers: new Headers({ [ENTETE_INVITATION]: jeton }) } as unknown as Parameters<typeof avant>[1];
      await expect(avant(utilisateur, ctx), path).rejects.toMatchObject({ status: "FORBIDDEN" });
    }
    await expect(avant(utilisateur, null)).rejects.toMatchObject({ status: "FORBIDDEN" });
  });

  it("laisse tout passer quand l'inscription est ouverte", async () => {
    const auth = authEn(OUVERTE);
    await auth.api.signUpEmail({ body: corps("libre@megga.test") });
    expect(await comptes()).toEqual(["libre@megga.test"]);
    const o = optionsAuth(db, { ...OUVERTE, GOOGLE_CLIENT_ID: "a", GOOGLE_CLIENT_SECRET: "b" });
    expect(o.account?.accountLinking?.enabled).not.toBe(false);
    expect(o.socialProviders?.google).not.toHaveProperty("disableSignUp");
  });
});
