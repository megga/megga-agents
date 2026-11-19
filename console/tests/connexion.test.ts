import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import type { ReactElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Connexion, messageErreur, retourSur } from "@/app/connexion/connexion";
import PageConnexion from "@/app/connexion/page";
import { ENTETE_INVITATION, fournisseurs } from "@/lib/auth";
import { T } from "@/lib/textes";

// La page de connexion appelée comme Next.js la rend, sans session.
vi.mock("@/lib/auth", async (original) => ({ ...(await original<typeof import("@/lib/auth")>()), session: async () => null }));
vi.mock("next/navigation", () => ({
  redirect: (url: string) => {
    throw new Error(`redirect:${url}`);
  },
  useRouter: () => ({ replace: () => {}, refresh: () => {} }),
}));

const page = async (p: Record<string, string | string[]>) =>
  (await PageConnexion({ searchParams: Promise.resolve(p) } as never)) as ReactElement<{ erreur?: string | null; inscription?: boolean }>;

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("Google et Microsoft", () => {
  it("restent éteints sans leurs clés", () => {
    expect(fournisseurs({})).toEqual({});
    expect(fournisseurs({ GOOGLE_CLIENT_ID: "x" })).toEqual({});
    expect(fournisseurs({ MICROSOFT_CLIENT_SECRET: "y" })).toEqual({});
  });

  it("s'allument chacun avec ses deux clés", () => {
    expect(Object.keys(fournisseurs({ GOOGLE_CLIENT_ID: "a", GOOGLE_CLIENT_SECRET: "b" }))).toEqual(["google"]);
    const f = fournisseurs({ MICROSOFT_CLIENT_ID: "a", MICROSOFT_CLIENT_SECRET: "b" });
    expect(Object.keys(f)).toEqual(["microsoft"]);
    expect(f.microsoft).toMatchObject({ tenantId: "common" });
  });
});

describe("les erreurs de connexion", () => {
  it("sont dites en français", () => {
    expect(messageErreur("INVALID_EMAIL_OR_PASSWORD")).toBe("Courriel ou mot de passe incorrect.");
    expect(messageErreur("USER_ALREADY_EXISTS_USE_ANOTHER_EMAIL")).toBe("Ce courriel a déjà un compte.");
    expect(messageErreur("PASSWORD_TOO_SHORT")).toBe("Le mot de passe fait 8 caractères au moins.");
    expect(messageErreur("AUTRE_CHOSE")).toBe("Un souci est survenu. Réessayez.");
  });

  it("un refus d'inscription hors invitation dit sa phrase, par courriel comme au retour de Google ou Microsoft", () => {
    expect(T.inscriptionSurInvitation).toBe("Un compte se crée depuis un lien d'invitation.");
    expect(messageErreur("INSCRIPTION_SUR_INVITATION")).toBe(T.inscriptionSurInvitation);
    expect(messageErreur("signup_disabled")).toBe(T.inscriptionSurInvitation);
  });

  it("un compte suspendu lit une phrase claire", () => {
    expect(messageErreur("BANNED_USER")).toBe(T.compteSuspendu);
  });

  it("au retour de Google ou Microsoft (?error=), la page dit la phrase du code, jamais le texte reçu", async () => {
    const suspendu = await page({ error: "BANNED_USER", error_description: "You have been banned" });
    expect(suspendu.type).toBe(Connexion);
    expect(suspendu.props.erreur).toBe(T.compteSuspendu);
    for (const error of ["<b>pirate</b>", "account_not_linked", ["BANNED_USER", "x"]]) {
      expect((await page({ error })).props.erreur, JSON.stringify(error)).toBe(T.erreurGenerale);
    }
    expect((await page({})).props.erreur).toBeNull();
    expect((await page({ error: "" })).props.erreur).toBeNull(); // ?error= vide : comme sans paramètre
  });

  it("Google et Microsoft renvoient leurs erreurs à la page de connexion (errorCallbackURL)", () => {
    const code = readFileSync(join(__dirname, "../src/app/connexion/connexion.tsx"), "utf8");
    expect(code.match(/signIn\.social\(\{[^}]*errorCallbackURL: RETOUR_ERREUR[^}]*\}\)/g)).toHaveLength(2);
    expect(code).toContain('const RETOUR_ERREUR = "/connexion";');
  });
});

describe("le retour après la connexion", () => {
  it("ne mène qu'à l'admin ou à la page d'invitation sans jeton, sinon à la console", () => {
    expect(retourSur("/admin")).toBe("/admin");
    expect(retourSur("/admin/invitation")).toBe("/admin/invitation");
    expect(retourSur("/admin/invitation/" + "a".repeat(43))).toBe("/");
    expect(retourSur("https://ailleurs.example")).toBe("/");
    expect(retourSur("//ailleurs.example/admin")).toBe("/");
    expect(retourSur("/admin/invitation/")).toBe("/");
    expect(retourSur("/admin/clients")).toBe("/");
    expect(retourSur(["/admin"])).toBe("/");
    expect(retourSur(undefined)).toBe("/");
  });

  it("ne porte jamais un jeton : aucune adresse ?retour= construite sous src/ n'y met une valeur", () => {
    const fichiers = (d: string): string[] =>
      readdirSync(d).flatMap((n) => (statSync(join(d, n)).isDirectory() ? fichiers(join(d, n)) : /\.tsx?$/.test(n) ? [join(d, n)] : []));
    const retours = fichiers(join(__dirname, "../src")).flatMap((f) =>
      [...readFileSync(f, "utf8").matchAll(/[?&]retour=([^"'`\s)]*)/g)].map((m) => ({ f, adresse: m[1] })));
    expect(retours.length).toBeGreaterThan(0);
    for (const r of retours) expect(r.adresse, r.f).toMatch(/^\/admin(\/invitation)?$/);
  });
});

describe("l'inscription sur invitation", () => {
  it("l'écran de connexion ne propose de créer un compte que si l'inscription est ouverte", async () => {
    vi.stubEnv("CONSOLE_INSCRIPTION", "");
    expect((await page({})).props.inscription).toBe(false);
    vi.stubEnv("CONSOLE_INSCRIPTION", "invitation");
    expect((await page({})).props.inscription).toBe(false);
    vi.stubEnv("CONSOLE_INSCRIPTION", "ouverte");
    expect((await page({})).props.inscription).toBe(true);
  });

  it("la page du lien envoie le jeton dans un en-tête de la demande d'inscription, jamais dans une adresse", () => {
    const code = readFileSync(join(__dirname, "../src/app/admin/invitation/[jeton]/rejoindre.tsx"), "utf8");
    expect(code).toMatch(/signUp\.email\(\s*\{[^}]*\},\s*\{\s*headers:\s*\{\s*\[ENTETE_INVITATION\]:\s*jeton\s*\}\s*\},?\s*\)/);
    expect(code).not.toMatch(/callbackURL[^\n]*jeton/);
    expect(code).toContain(`const ENTETE_INVITATION = "${ENTETE_INVITATION}";`); // le même nom que celui que lit le serveur
  });
});
