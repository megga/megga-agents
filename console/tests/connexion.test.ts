import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { messageErreur, retourSur } from "@/app/connexion/connexion";
import { fournisseurs } from "@/lib/auth";

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
