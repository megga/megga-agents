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
  it("ne mène qu'à l'admin ou à une invitation, sinon à la console", () => {
    expect(retourSur("/admin")).toBe("/admin");
    expect(retourSur("/admin/invitation/" + "a".repeat(43))).toBe("/admin/invitation/" + "a".repeat(43));
    expect(retourSur("https://ailleurs.example")).toBe("/");
    expect(retourSur("//ailleurs.example/admin")).toBe("/");
    expect(retourSur("/admin/invitation/" + "a".repeat(42))).toBe("/");
    expect(retourSur("/admin/clients")).toBe("/");
    expect(retourSur(["/admin"])).toBe("/");
    expect(retourSur(undefined)).toBe("/");
  });
});
