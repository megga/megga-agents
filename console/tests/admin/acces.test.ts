import { describe, expect, it } from "vitest";
import {
  droitsEffectifs,
  entreesRail,
  exiger,
  exigerClient,
  filtrerClients,
  lirePerimetre,
  perimetreInclus,
  peut,
  peutCreerClient,
  peutDonnerRole,
  peutEcrireRole,
  peutSuspendre,
  peutToucherMembre,
  voitClient,
} from "@/lib/admin/acces";
import { DROITS } from "@/lib/admin/droits";
import { TA } from "@/lib/admin/textes";
import { acces, refus } from "./aides";

describe("les droits d'un membre", () => {
  it("un externe ne garde que trois droits ; un droit inconnu n'est jamais accordé", () => {
    expect([...droitsEffectifs(DROITS, true, false)].sort()).toEqual(["clients.voir", "conversations.lire", "versions.preparer"]);
    expect(droitsEffectifs(["clients.voir", "inconnu"], false, false)).toEqual(new Set(["clients.voir"]));
    expect(droitsEffectifs([], false, true).size).toBe(13);
    expect(refus(() => exiger(acces({ droits: ["clients.voir"] }), "couts.voir"))).toMatchObject({ statut: 403, message: TA.sansDroit });
    expect(peut(acces({ droits: ["clients.voir"] }), "clients.voir")).toBe(true);
    expect(() => exiger(acces({ droits: ["clients.voir"] }), "clients.voir")).not.toThrow();
  });
});

describe("le périmètre", () => {
  it("le périmètre borne la liste et répond 404 au-dehors, même à une adresse mal formée", () => {
    const a = acces({ perimetre: ["garage-essai"] });
    expect(filtrerClients(a, [{ id: "garage-essai" }, { id: "boulangerie-essai" }]).map((c) => c.id)).toEqual(["garage-essai"]);
    expect(refus(() => exigerClient(a, "boulangerie-essai")).statut).toBe(404);
    expect(refus(() => exigerClient(a, "Garage-essai")).statut).toBe(404);
    expect(refus(() => exigerClient(acces({ perimetre: "tous" }), "..%2Fx")).statut).toBe(404);
    expect(refus(() => exigerClient(a, "boulangerie-essai")).message).toBe(TA.introuvable);
    expect([voitClient(a, "garage-essai"), voitClient(acces({ perimetre: "tous" }), "boulangerie-essai")]).toEqual([true, true]);
  });

  it("un externe a toujours au moins un client", () => {
    for (const v of [["tous", true], [[], true], [["Garage"], false]] as const) expect(refus(() => lirePerimetre(v[0], v[1])).statut).toBe(400);
    expect(lirePerimetre(["garage-essai"], true)).toEqual(["garage-essai"]);
    expect(refus(() => lirePerimetre("tous", true)).message).toBe(TA.externePerimetre);
    expect(refus(() => lirePerimetre(["Garage"], false)).message).toBe(TA.perimetreInvalide);
    expect(refus(() => lirePerimetre(undefined, false)).message).toBe(TA.perimetreInvalide);
    expect(lirePerimetre("tous", false)).toBe("tous");
    expect(lirePerimetre(["a1", "a1", "b2"], false)).toEqual(["a1", "b2"]);
  });
});

describe("la non-escalade", () => {
  it("pas d'escalade sans être superadmin", () => {
    const m = acces({ utilisateur: "m", role: "gestion", droits: ["clients.voir", "equipe.gerer"], perimetre: ["a1"] });
    expect(peutDonnerRole(m, { id: "lecture", droits: ["clients.voir", "comptes.voir"] })).toBe(false);
    expect(peutDonnerRole(m, { id: "x", droits: ["clients.voir"] })).toBe(true);
    expect(peutDonnerRole(m, { id: "superadmin", droits: DROITS })).toBe(false);
    expect(peutEcrireRole(m, ["couts.voir"], null)).toBe(false);
    expect(peutEcrireRole(m, ["clients.voir"], "gestion")).toBe(false); // jamais le rôle qu'on porte
    expect(peutToucherMembre(m, { utilisateur: "m", role: "gestion" })).toBe(false);
    expect(peutToucherMembre(m, { utilisateur: "s", role: "superadmin" })).toBe(false);
    expect(peutToucherMembre(m, { utilisateur: "n", role: "x" })).toBe(true);
    expect([perimetreInclus(m, ["a1"]), perimetreInclus(m, ["a1", "b2"]), perimetreInclus(m, "tous")]).toEqual([true, false, false]);
    expect(peutCreerClient(acces({ droits: ["clients.creer"], perimetre: ["a1"] }))).toBe(false);
  });

  it("un superadmin peut tout cela ; un membre sans equipe.gerer, rien", () => {
    const s = acces({ utilisateur: "s", superadmin: true });
    expect(peutDonnerRole(s, { id: "superadmin", droits: DROITS })).toBe(true);
    expect(peutEcrireRole(s, DROITS, null)).toBe(true);
    expect(peutToucherMembre(s, { utilisateur: "t", role: "superadmin" })).toBe(true);
    expect(perimetreInclus(s, "tous")).toBe(true);
    expect(peutCreerClient(acces({ droits: ["clients.creer"] }))).toBe(true);
    const l = acces({ utilisateur: "l", droits: ["clients.voir"] });
    expect(peutDonnerRole(l, { id: "x", droits: ["clients.voir"] })).toBe(false);
    expect(peutEcrireRole(l, ["clients.voir"], null)).toBe(false);
    expect(peutToucherMembre(l, { utilisateur: "n", role: "x" })).toBe(false);
  });

  it("suspendre le compte d'un membre est réservé aux superadmins ; ni un superadmin, ni soi-même", () => {
    const g = acces({ utilisateur: "g", droits: ["comptes.gerer"] });
    const s = acces({ utilisateur: "s", superadmin: true, role: "superadmin" });
    expect(peutSuspendre(g, { id: "c", membre: null })).toBe(true);
    expect(peutSuspendre(g, { id: "c", membre: { role: "lecture" } })).toBe(false);
    expect(peutSuspendre(s, { id: "c", membre: { role: "lecture" } })).toBe(true);
    expect(peutSuspendre(s, { id: "t", membre: { role: "superadmin" } })).toBe(false);
    expect(peutSuspendre(g, { id: "g", membre: null })).toBe(false);
    expect(peutSuspendre(acces({ utilisateur: "v", droits: ["comptes.voir"] }), { id: "c", membre: null })).toBe(false);
  });
});

describe("le rail", () => {
  it("le rail ne montre que les entrées ouvertes", () => {
    expect(entreesRail(acces({ superadmin: true })).map((e) => e.href)).toEqual(["/admin", "/admin/clients", "/admin/alertes",
      "/admin/installations", "/admin/comptes", "/admin/tarifs", "/admin/equipe", "/admin/journal"]);
    expect(entreesRail(acces({ externe: true, droits: DROITS, perimetre: ["garage-essai"] })).map((e) => e.href))
      .toEqual(["/admin", "/admin/clients", "/admin/alertes", "/admin/installations"]);
    expect(entreesRail(acces({ superadmin: true }))[0]).toEqual({ href: "/admin", texte: TA.vueEnsemble });
  });
});
