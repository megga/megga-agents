import { describe, expect, it } from "vitest";
import {
  aPuDonner,
  droitsEffectifs,
  entreesRail,
  exiger,
  exigerClient,
  filtrerClients,
  lirePerimetre,
  ongletsClient,
  perimetreInclus,
  peut,
  peutCreerClient,
  peutDonnerRole,
  peutEcrireRole,
  peutSuspendre,
  peutToucherMembre,
  perimetreVu,
  roleLePlusEtroit,
  voitClient,
} from "@/lib/admin/acces";
import { avecPeriode } from "@/components/admin/onglets";
import { DROITS, ROLES_DE_DEPART, SUPERADMIN } from "@/lib/admin/droits";
import { TA } from "@/lib/admin/textes";
import { acces, refus } from "./aides";

describe("les droits d'un membre", () => {
  it("un externe ne garde que deux droits ; un droit inconnu n'est jamais accordé", () => {
    expect([...droitsEffectifs(DROITS, true, false)].sort()).toEqual(["clients.voir", "versions.preparer"]);
    expect(droitsEffectifs(["clients.voir", "inconnu"], false, false)).toEqual(new Set(["clients.voir"]));
    expect(droitsEffectifs([], false, true).size).toBe(12);
    // un rôle qui avait coché la lecture des conversations la garde en base, sans effet
    expect(droitsEffectifs(["clients.voir", "conversations.lire"], false, false)).toEqual(new Set(["clients.voir"]));
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

  it("celui d'un autre ne montre à un membre limité que les clients qu'il partage, les autres comptés", () => {
    const limite = acces({ perimetre: ["a1", "b2"] });
    expect(perimetreVu(limite, ["a1", "c3", "d4", "b2", "e5"])).toEqual({ clients: ["a1", "b2"], autres: 3 });
    expect(perimetreVu(limite, ["c3"])).toEqual({ clients: [], autres: 1 });
    expect(perimetreVu(limite, [])).toEqual({ clients: [], autres: 0 });
    expect(perimetreVu(limite, "tous")).toBe("tous");
    const tous = acces({ perimetre: "tous" });
    expect(perimetreVu(tous, ["a1", "c3"])).toEqual({ clients: ["a1", "c3"], autres: 0 });
    expect(perimetreVu(acces({ superadmin: true }), ["c3"])).toEqual({ clients: ["c3"], autres: 0 });
    expect(perimetreVu(acces({ perimetre: [] }), ["a1"])).toEqual({ clients: [], autres: 1 });
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
    expect(peutEcrireRole(m, ["clients.voir"], null)).toBe(false); // un rôle vaut pour tous ses porteurs : limité à une liste, on n'en écrit aucun
    expect(peutEcrireRole({ ...m, perimetre: "tous" }, ["clients.voir"], null)).toBe(true);
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

describe("ce qu'on aurait pu donner soi-même", () => {
  it("un rôle qu'on peut donner, sur un périmètre inclus dans le sien ; tout, pour un superadmin", () => {
    const m = acces({ utilisateur: "m", droits: ["clients.voir", "equipe.gerer"], perimetre: ["a1"] });
    const petit = { id: "petit", droits: ["clients.voir"] as const };
    expect(aPuDonner(m, petit, ["a1"])).toBe(true);
    expect(aPuDonner(m, petit, ["a1", "b2"])).toBe(false);
    expect(aPuDonner(m, petit, "tous")).toBe(false);
    expect(aPuDonner(m, { id: "lecture", droits: ["clients.voir", "comptes.voir"] }, ["a1"])).toBe(false);
    expect(aPuDonner(m, undefined, ["a1"])).toBe(false);
    expect(aPuDonner(acces({ superadmin: true }), undefined, "tous")).toBe(true);
    expect(aPuDonner(acces({ droits: ["clients.voir"] }), petit, "tous")).toBe(false);
  });
});

describe("le rôle proposé d'abord à une invitation", () => {
  it("est le plus étroit, jamais Superadmin ; à égalité, le premier", () => {
    const depart = [{ id: SUPERADMIN, droits: DROITS }, ...ROLES_DE_DEPART];
    expect(roleLePlusEtroit(depart)).toBe("lecture");
    expect(roleLePlusEtroit([...depart, { id: "petit", droits: ["clients.voir"] }])).toBe("petit");
    expect(roleLePlusEtroit([{ id: "a", droits: ["clients.voir"] }, { id: "b", droits: ["journal.voir"] }])).toBe("a");
    expect(roleLePlusEtroit([{ id: SUPERADMIN, droits: [] }, { id: "administration", droits: DROITS }])).toBe("administration");
    expect(roleLePlusEtroit([{ id: SUPERADMIN, droits: DROITS }])).toBeUndefined();
    expect(roleLePlusEtroit([])).toBeUndefined();
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

describe("les onglets d'un client", () => {
  const textes = (o: { texte: string }[]) => o.map((x) => x.texte);

  it("un externe voit Suivi, Alertes, Versions, et Installation hors Cloudflare seulement ; jamais de conversations", () => {
    const e = acces({ externe: true, droits: DROITS, perimetre: ["garage-essai"] });
    expect(textes(ongletsClient(e, "garage-essai", false))).toEqual([TA.suivi, TA.alertes, TA.versions]);
    expect(textes(ongletsClient(e, "chalet-essai", true))).toEqual([TA.suivi, TA.alertes, TA.versions, TA.installation]);
  });

  it("un membre Finance voit Suivi, Alertes, Versions ; Accès s'ouvre avec acces.gerer ou clients.piloter", () => {
    const finance = ROLES_DE_DEPART.find((r) => r.id === "finance")!;
    expect(textes(ongletsClient(acces({ droits: finance.droits }), "garage-essai", false))).toEqual([TA.suivi, TA.alertes, TA.versions]);
    for (const d of ["acces.gerer", "clients.piloter"] as const)
      expect(textes(ongletsClient(acces({ droits: ["clients.voir", d] }), "garage-essai", false)), d).toContain(TA.acces);
    expect(ongletsClient(acces({ superadmin: true }), "garage-essai", true).map((o) => o.href)).toEqual([
      "/admin/clients/garage-essai", "/admin/clients/garage-essai/alertes",
      "/admin/clients/garage-essai/versions", "/admin/clients/garage-essai/acces", "/admin/clients/garage-essai/installation",
    ]);
  });

  it("Suivi et Alertes gardent la période de l'adresse ; les autres onglets n'en ont pas", () => {
    const o = ongletsClient(acces({ superadmin: true }), "garage-essai", true);
    expect(o.filter((x) => x.periode).map((x) => x.texte)).toEqual([TA.suivi, TA.alertes]);
    expect(avecPeriode(o, "30").map((x) => x.href)).toEqual([
      "/admin/clients/garage-essai?jours=30", "/admin/clients/garage-essai/alertes?jours=30",
      "/admin/clients/garage-essai/versions", "/admin/clients/garage-essai/acces", "/admin/clients/garage-essai/installation",
    ]);
    for (const j of [null, "abc", "999"]) expect(avecPeriode(o, j).map((x) => x.href), String(j)).toEqual(o.map((x) => x.href));
    expect(avecPeriode(o, "1")[0]).toEqual({ href: "/admin/clients/garage-essai?jours=1", texte: TA.suivi });
  });
});
