import type { DatabaseSync } from "node:sqlite";
import { beforeEach, describe, expect, it } from "vitest";
import { DROITS, DROITS_EXTERNE } from "@/lib/admin/droits";
import {
  accesDe,
  ajouterMembre,
  enCours,
  listerMembres,
  membreEnCours,
  modifierMembre,
  retirerMembre,
} from "@/lib/admin/membres";
import { creerRole, lireRole, listerRoles, modifierRole, retirerRole } from "@/lib/admin/roles";
import { creerTablesAdmin } from "@/lib/admin/tables";
import { TA } from "@/lib/admin/textes";
import { baseEssai, compte, membre, refus, T0 } from "./aides";

let db: DatabaseSync;
beforeEach(async () => {
  db = await baseEssai();
});

describe("les tables de l'admin", () => {
  it("se créent deux fois de suite sans rien doubler, avec le superadmin et les quatre rôles de départ", () => {
    creerTablesAdmin(db, T0);
    creerTablesAdmin(db, T0);
    const roles = listerRoles(db);
    expect(roles.map((r) => r.id)).toEqual(["superadmin", "administration", "exploitation", "finance", "lecture"]);
    expect(roles[0]).toMatchObject({ nom: TA.roleSuperadmin, systeme: true, membres: 0 });
    expect(roles[0].droits).toEqual([...DROITS]);
    expect(roles.slice(1).every((r) => !r.systeme)).toBe(true);
  });

  it("ne remettent pas un rôle de départ retiré", () => {
    const s = membre(db, { utilisateur: "s", role: "superadmin" });
    retirerRole(db, s, "finance");
    creerTablesAdmin(db, T0);
    expect(lireRole(db, "finance")).toBeUndefined();
  });
});

describe("les rôles", () => {
  it("se créent avec des droits connus et un nom libre", () => {
    const s = membre(db, { utilisateur: "s", role: "superadmin" });
    const r = creerRole(db, s, { nom: " Support ", droits: ["couts.voir", "clients.voir"] }, T0);
    expect(r).toMatchObject({ nom: "Support", description: "", droits: ["clients.voir", "couts.voir"], systeme: false, membres: 0 });
    expect(r.id).toMatch(/^ro_[0-9a-f]{20}$/);
    expect(refus(() => creerRole(db, s, { nom: "Autre", droits: ["inconnu"] }))).toMatchObject({ statut: 400, message: TA.droitInconnu });
    expect(refus(() => creerRole(db, s, { nom: "support", droits: [] }))).toMatchObject({ statut: 409, message: TA.nomPris });
    expect(refus(() => creerRole(db, s, { nom: "  ", droits: [] }))).toMatchObject({ statut: 400, message: TA.nomManquant });
  });

  it("ignorent à la lecture un droit inconnu écrit à la main en base", () => {
    db.prepare("INSERT INTO admin_role (id, nom, description, droits, systeme, cree_le, modifie_le) VALUES ('main', 'À la main', '', ?, 0, ?, ?)")
      .run(JSON.stringify(["clients.voir", "inconnu"]), T0.toISOString(), T0.toISOString());
    expect(lireRole(db, "main")!.droits).toEqual(["clients.voir"]);
    compte(db, { id: "x", courriel: "x@megga.test" });
    ajouterMembre(db, { utilisateur: "x", role: "main", externe: false, perimetre: "tous", finAcces: null, ajoutePar: null }, T0);
    expect([...accesDe(db, { id: "x", email: "x@megga.test", name: "X" }, T0)!.droits]).toEqual(["clients.voir"]);
  });

  it("le superadmin ne se modifie ni ne se retire ; un rôle porté ne se retire pas", () => {
    const s = membre(db, { utilisateur: "s", role: "superadmin" });
    expect(refus(() => modifierRole(db, s, "superadmin", { nom: "Chef" }))).toMatchObject({ statut: 403, message: TA.roleFixe });
    expect(refus(() => retirerRole(db, s, "superadmin"))).toMatchObject({ statut: 403, message: TA.roleFixe });
    membre(db, { utilisateur: "l", role: "lecture" });
    expect(refus(() => retirerRole(db, s, "lecture"))).toMatchObject({ statut: 409, message: TA.rolePorte });
    expect(refus(() => retirerRole(db, s, "absent"))).toMatchObject({ statut: 404, message: TA.roleInconnu });
    expect(modifierRole(db, s, "lecture", { description: "Lire.", droits: ["clients.voir"] }, T0)).toMatchObject({ nom: TA.roleLecture,
      description: "Lire.", droits: ["clients.voir"], membres: 1 });
    expect(refus(() => modifierRole(db, s, "lecture", { nom: TA.roleFinance }))).toMatchObject({ statut: 409, message: TA.nomPris });
    retirerRole(db, s, "finance");
    expect(lireRole(db, "finance")).toBeUndefined();
  });

  it("sans être superadmin, un rôle ne s'écrit qu'avec ses propres droits, jamais celui qu'on porte", () => {
    const s = membre(db, { utilisateur: "s", role: "superadmin" });
    const gestion = creerRole(db, s, { nom: "Gestion", droits: ["clients.voir", "equipe.gerer"] });
    const m = membre(db, { utilisateur: "m", role: gestion.id });
    expect(refus(() => creerRole(db, m, { nom: "Plus", droits: ["couts.voir"] }))).toMatchObject({ statut: 403, message: TA.escalade });
    expect(refus(() => modifierRole(db, m, gestion.id, { droits: ["clients.voir"] }))).toMatchObject({ statut: 403, message: TA.escalade });
    expect(refus(() => modifierRole(db, m, "lecture", { droits: ["clients.voir"] }))).toMatchObject({ statut: 403, message: TA.escalade });
    const petit = creerRole(db, m, { nom: "Petit", droits: ["clients.voir"] });
    expect(modifierRole(db, m, petit.id, { droits: ["clients.voir", "equipe.gerer"] }).droits).toEqual(["clients.voir", "equipe.gerer"]);
    expect(refus(() => retirerRole(db, m, "administration"))).toMatchObject({ statut: 403, message: TA.escalade });
    retirerRole(db, m, petit.id);
    expect(lireRole(db, petit.id)).toBeUndefined();
  });
});

describe("les membres", () => {
  it("restent en cours jusqu'au dernier instant de leur fin d'accès", () => {
    expect([enCours(null, T0), enCours("2026-11-18", new Date("2026-11-18T23:59:59.999Z")), enCours("2026-11-18", new Date("2026-11-19T00:00:00Z"))])
      .toEqual([true, true, false]);
    expect(enCours("pas-une-date", T0)).toBe(false);
    membre(db, { utilisateur: "f", role: "lecture", finAcces: "2026-11-18" });
    expect(membreEnCours(db, "f", new Date("2026-11-18T22:00:00Z"))).toBeDefined();
    expect(membreEnCours(db, "f", new Date("2026-11-19T00:00:01Z"))).toBeUndefined();
    expect(accesDe(db, { id: "f", email: "f@megga.test", name: "F" }, new Date("2026-11-19T00:00:01Z"))).toBeUndefined();
    expect(membreEnCours(db, "inconnu", T0)).toBeUndefined();
  });

  it("se lisent avec le courriel et le nom de leur compte", () => {
    compte(db, { id: "c1", courriel: "chef@megga.test", nom: "Chef" });
    ajouterMembre(db, { utilisateur: "c1", role: "lecture", externe: false, perimetre: ["a1"], finAcces: "2026-12-31", ajoutePar: "s" }, T0);
    expect(listerMembres(db)).toEqual([{ utilisateur: "c1", courriel: "chef@megga.test", nom: "Chef", role: "lecture", externe: false,
      perimetre: ["a1"], finAcces: "2026-12-31", ajoutePar: "s", ajouteLe: T0.toISOString(), derniereConnexion: null }]);
  });

  it("gardent toujours un superadmin", () => {
    const s = membre(db, { utilisateur: "s", role: "superadmin" });
    expect(refus(() => retirerMembre(db, s, "s", T0))).toMatchObject({ statut: 409, message: TA.dernierSuperadmin });
    expect(refus(() => modifierMembre(db, s, "s", { role: "lecture" }, T0))).toMatchObject({ statut: 409, message: TA.dernierSuperadmin });
    membre(db, { utilisateur: "t", role: "superadmin" });
    retirerMembre(db, s, "s", T0);
    expect(membreEnCours(db, "s", T0)).toBeUndefined();
    expect(refus(() => retirerMembre(db, s, "s", T0))).toMatchObject({ statut: 404, message: TA.membreInconnu });
  });

  it("un membre qui gère l'équipe ne touche ni à sa ligne, ni à un superadmin, ni au-delà de ses droits ou de son périmètre", () => {
    const s = membre(db, { utilisateur: "s", role: "superadmin" });
    const gestion = creerRole(db, s, { nom: "Gestion", droits: ["clients.voir", "equipe.gerer"] });
    const petit = creerRole(db, s, { nom: "Petit", droits: ["clients.voir"] });
    const m = membre(db, { utilisateur: "m", role: gestion.id, perimetre: ["a1"] });
    membre(db, { utilisateur: "n", role: petit.id, perimetre: ["a1"] });
    membre(db, { utilisateur: "g", role: "administration", perimetre: ["a1"] });
    for (const [qui, corps] of [
      ["m", { finAcces: "2026-12-31" }],
      ["s", { finAcces: "2026-12-31" }],
      ["n", { role: "lecture" }],
      ["n", { perimetre: ["b2"] }],
      ["n", { perimetre: "tous" }],
      ["g", { role: petit.id }],
    ] as const) {
      expect(refus(() => modifierMembre(db, m, qui, corps, T0)), `${qui} ${JSON.stringify(corps)}`).toMatchObject({ statut: 403, message: TA.escalade });
    }
    expect(refus(() => retirerMembre(db, m, "s", T0))).toMatchObject({ statut: 403, message: TA.escalade });
    expect(refus(() => retirerMembre(db, m, "g", T0))).toMatchObject({ statut: 403, message: TA.escalade });
    expect(modifierMembre(db, m, "n", { perimetre: ["a1"], finAcces: "2026-12-31" }, T0)).toMatchObject({ perimetre: ["a1"], finAcces: "2026-12-31" });
    retirerMembre(db, m, "n", T0);
    expect(membreEnCours(db, "n", T0)).toBeUndefined();
  });

  it("refusent une valeur mal formée", () => {
    const s = membre(db, { utilisateur: "s", role: "superadmin" });
    membre(db, { utilisateur: "n", role: "lecture" });
    expect(refus(() => modifierMembre(db, s, "n", { role: "absent" }, T0))).toMatchObject({ statut: 400, message: TA.roleInconnu });
    expect(refus(() => modifierMembre(db, s, "n", { finAcces: "31.12.2026" }, T0))).toMatchObject({ statut: 400, message: TA.finAccesInvalide });
    expect(refus(() => modifierMembre(db, s, "n", { finAcces: "2026-02-30" }, T0))).toMatchObject({ statut: 400, message: TA.finAccesInvalide });
    expect(refus(() => modifierMembre(db, s, "n", { perimetre: ["Garage"] }, T0))).toMatchObject({ statut: 400, message: TA.perimetreInvalide });
    expect(refus(() => modifierMembre(db, s, "absent", { finAcces: null }, T0))).toMatchObject({ statut: 404, message: TA.membreInconnu });
  });

  it("un externe a un périmètre, n'est jamais superadmin, et ne garde que trois droits", () => {
    compte(db, { id: "e", courriel: "e@megga.test" });
    const ajout = { utilisateur: "e", externe: true, finAcces: null, ajoutePar: null };
    expect(refus(() => ajouterMembre(db, { ...ajout, role: "lecture", perimetre: "tous" }, T0))).toMatchObject({ statut: 400, message: TA.externePerimetre });
    expect(refus(() => ajouterMembre(db, { ...ajout, role: "superadmin", perimetre: ["a1"] }, T0)))
      .toMatchObject({ statut: 400, message: TA.externeSuperadmin });
    ajouterMembre(db, { ...ajout, role: "administration", perimetre: ["garage-essai"] }, T0);
    const e = accesDe(db, { id: "e", email: "e@megga.test", name: "E" }, T0)!;
    expect([...e.droits].sort()).toEqual([...DROITS_EXTERNE].sort());
    expect(e).toMatchObject({ externe: true, superadmin: false, perimetre: ["garage-essai"] });
    const s = membre(db, { utilisateur: "s", role: "superadmin" });
    expect(refus(() => modifierMembre(db, s, "e", { role: "superadmin" }, T0))).toMatchObject({ statut: 400, message: TA.externeSuperadmin });
    expect(refus(() => modifierMembre(db, s, "e", { perimetre: "tous" }, T0))).toMatchObject({ statut: 400, message: TA.externePerimetre });
  });

  it("un superadmin a tous les clients et pas de fin d'accès", () => {
    compte(db, { id: "t", courriel: "t@megga.test" });
    const t = ajouterMembre(db, { utilisateur: "t", role: "superadmin", externe: false, perimetre: ["a1"], finAcces: "2026-12-01", ajoutePar: null }, T0);
    expect(t).toMatchObject({ perimetre: "tous", finAcces: null });
    const s = membre(db, { utilisateur: "s", role: "superadmin" });
    membre(db, { utilisateur: "n", role: "lecture", perimetre: ["a1"], finAcces: "2026-12-31" });
    expect(modifierMembre(db, s, "n", { role: "superadmin" }, T0)).toMatchObject({ role: "superadmin", perimetre: "tous", finAcces: null });
    const a = accesDe(db, { id: "n", email: "n@megga.test", name: "N" }, T0)!;
    expect(a).toMatchObject({ superadmin: true, perimetre: "tous", role: { id: "superadmin", nom: TA.roleSuperadmin } });
    expect(a.droits.size).toBe(13);
  });
});
