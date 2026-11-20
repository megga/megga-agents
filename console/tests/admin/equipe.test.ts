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
import type { Base } from "@/lib/donnees/base";
import { baseEssai, compte, membre, refusAsync, T0 } from "./aides";

let db: Base;
beforeEach(async () => {
  db = await baseEssai();
});

describe("les tables de l'admin", () => {
  it("se créent deux fois de suite sans rien doubler, avec le superadmin et les quatre rôles de départ", async () => {
    await creerTablesAdmin(db, T0);
    await creerTablesAdmin(db, T0);
    const roles = await listerRoles(db);
    expect(roles.map((r) => r.id)).toEqual(["superadmin", "administration", "exploitation", "finance", "lecture"]);
    expect(roles[0]).toMatchObject({ nom: TA.roleSuperadmin, systeme: true, membres: 0 });
    expect(roles[0].droits).toEqual([...DROITS]);
    expect(roles.slice(1).every((r) => !r.systeme)).toBe(true);
  });

  it("ne remettent pas un rôle de départ retiré", async () => {
    const s = await membre(db, { utilisateur: "s", role: "superadmin" });
    await retirerRole(db, s, "finance");
    await creerTablesAdmin(db, T0);
    expect(await lireRole(db, "finance")).toBeUndefined();
  });
});

describe("les rôles", () => {
  it("se créent avec des droits connus et un nom libre", async () => {
    const s = await membre(db, { utilisateur: "s", role: "superadmin" });
    const r = await creerRole(db, s, { nom: " Support ", droits: ["couts.voir", "clients.voir"] }, T0);
    expect(r).toMatchObject({ nom: "Support", description: "", droits: ["clients.voir", "couts.voir"], systeme: false, membres: 0 });
    expect(r.id).toMatch(/^ro_[0-9a-f]{20}$/);
    expect(await refusAsync(() => creerRole(db, s, { nom: "Autre", droits: ["inconnu"] }))).toMatchObject({ statut: 400, message: TA.droitInconnu });
    expect(await refusAsync(() => creerRole(db, s, { nom: "support", droits: [] }))).toMatchObject({ statut: 409, message: TA.nomPris });
    expect(await refusAsync(() => creerRole(db, s, { nom: "  ", droits: [] }))).toMatchObject({ statut: 400, message: TA.nomManquant });
  });

  it("ignorent à la lecture un droit inconnu écrit à la main en base", async () => {
    await db.ecrire("INSERT INTO admin_role (id, nom, description, droits, systeme, cree_le, modifie_le) VALUES ('main', 'À la main', '', ?, 0, ?, ?)", JSON.stringify(["clients.voir", "inconnu"]), T0.toISOString(), T0.toISOString());
    expect((await lireRole(db, "main"))!.droits).toEqual(["clients.voir"]);
    await compte(db, { id: "x", courriel: "x@megga.test" });
    await ajouterMembre(db, { utilisateur: "x", role: "main", externe: false, perimetre: "tous", finAcces: null, ajoutePar: null }, T0);
    expect([...(await accesDe(db, { id: "x", email: "x@megga.test", name: "X" }, T0))!.droits]).toEqual(["clients.voir"]);
  });

  it("le superadmin ne se modifie ni ne se retire ; un rôle porté ne se retire pas", async () => {
    const s = await membre(db, { utilisateur: "s", role: "superadmin" });
    expect(await refusAsync(() => modifierRole(db, s, "superadmin", { nom: "Chef" }))).toMatchObject({ statut: 403, message: TA.roleFixe });
    expect(await refusAsync(() => retirerRole(db, s, "superadmin"))).toMatchObject({ statut: 403, message: TA.roleFixe });
    await membre(db, { utilisateur: "l", role: "lecture" });
    expect(await refusAsync(() => retirerRole(db, s, "lecture"))).toMatchObject({ statut: 409, message: TA.rolePorte });
    expect(await refusAsync(() => retirerRole(db, s, "absent"))).toMatchObject({ statut: 404, message: TA.roleInconnu });
    expect(await modifierRole(db, s, "lecture", { description: "Lire.", droits: ["clients.voir"] }, T0)).toMatchObject({ nom: TA.roleLecture,
      description: "Lire.", droits: ["clients.voir"], membres: 1 });
    expect(await refusAsync(() => modifierRole(db, s, "lecture", { nom: TA.roleFinance }))).toMatchObject({ statut: 409, message: TA.nomPris });
    await retirerRole(db, s, "finance");
    expect(await lireRole(db, "finance")).toBeUndefined();
  });

  it("sans être superadmin, un rôle ne s'écrit qu'avec ses propres droits, jamais celui qu'on porte", async () => {
    const s = await membre(db, { utilisateur: "s", role: "superadmin" });
    const gestion = await creerRole(db, s, { nom: "Gestion", droits: ["clients.voir", "equipe.gerer"] });
    const m = await membre(db, { utilisateur: "m", role: gestion.id });
    expect(await refusAsync(() => creerRole(db, m, { nom: "Plus", droits: ["couts.voir"] }))).toMatchObject({ statut: 403, message: TA.escalade });
    expect(await refusAsync(() => modifierRole(db, m, gestion.id, { droits: ["clients.voir"] }))).toMatchObject({ statut: 403, message: TA.escalade });
    expect(await refusAsync(() => modifierRole(db, m, "lecture", { droits: ["clients.voir"] }))).toMatchObject({ statut: 403, message: TA.escalade });
    const petit = await creerRole(db, m, { nom: "Petit", droits: ["clients.voir"] });
    expect((await modifierRole(db, m, petit.id, { droits: ["clients.voir", "equipe.gerer"] })).droits).toEqual(["clients.voir", "equipe.gerer"]);
    expect(await refusAsync(() => retirerRole(db, m, "administration"))).toMatchObject({ statut: 403, message: TA.escalade });
    await retirerRole(db, m, petit.id);
    expect(await lireRole(db, petit.id)).toBeUndefined();
  });
});

describe("un rôle vaut pour tous ses porteurs", () => {
  it("sans être superadmin, un membre limité à une liste de clients n'écrit aucun rôle", async () => {
    const s = await membre(db, { utilisateur: "s", role: "superadmin" });
    const gestion = await creerRole(db, s, { nom: "Gestion", droits: ["clients.voir", "equipe.gerer"] });
    const petit = await creerRole(db, s, { nom: "Petit", droits: ["clients.voir"] });
    const m = await membre(db, { utilisateur: "m", role: gestion.id, perimetre: ["a1"] });
    expect(await refusAsync(() => creerRole(db, m, { nom: "Autre", droits: ["clients.voir"] }))).toMatchObject({ statut: 403, message: TA.escalade });
    expect(await refusAsync(() => modifierRole(db, m, petit.id, { description: "Lire." }))).toMatchObject({ statut: 403, message: TA.escalade });
    expect(await refusAsync(() => retirerRole(db, m, petit.id))).toMatchObject({ statut: 403, message: TA.escalade });
    const t = await membre(db, { utilisateur: "t", role: gestion.id });
    expect(await creerRole(db, t, { nom: "Autre", droits: ["clients.voir"] })).toMatchObject({ nom: "Autre", droits: ["clients.voir"] });
    expect((await modifierRole(db, t, petit.id, { description: "Lire." })).description).toBe("Lire.");
  });
});

describe("les membres", () => {
  it("restent en cours jusqu'au dernier instant de leur fin d'accès", async () => {
    expect([enCours(null, T0), enCours("2026-11-18", new Date("2026-11-18T23:59:59.999Z")), enCours("2026-11-18", new Date("2026-11-19T00:00:00Z"))])
      .toEqual([true, true, false]);
    expect(enCours("pas-une-date", T0)).toBe(false);
    await membre(db, { utilisateur: "f", role: "lecture", finAcces: "2026-11-18" });
    expect(await membreEnCours(db, "f", new Date("2026-11-18T22:00:00Z"))).toBeDefined();
    expect(await membreEnCours(db, "f", new Date("2026-11-19T00:00:01Z"))).toBeUndefined();
    expect(await accesDe(db, { id: "f", email: "f@megga.test", name: "F" }, new Date("2026-11-19T00:00:01Z"))).toBeUndefined();
    expect(await membreEnCours(db, "inconnu", T0)).toBeUndefined();
  });

  it("se lisent avec le courriel et le nom de leur compte", async () => {
    await compte(db, { id: "c1", courriel: "chef@megga.test", nom: "Chef" });
    await ajouterMembre(db, { utilisateur: "c1", role: "lecture", externe: false, perimetre: ["a1"], finAcces: "2026-12-31", ajoutePar: "s" }, T0);
    expect(await listerMembres(db)).toEqual([{ utilisateur: "c1", courriel: "chef@megga.test", nom: "Chef", image: null, role: "lecture", externe: false,
      perimetre: ["a1"], finAcces: "2026-12-31", ajoutePar: "s", ajouteLe: T0.toISOString(), derniereConnexion: null }]);
  });

  it("se lisent avec la photo de leur compte quand il en a une", async () => {
    await compte(db, { id: "c1", courriel: "chef@megga.test", nom: "Chef" });
    await compte(db, { id: "c2", courriel: "aide@megga.test", nom: "Aide" });
    for (const c of ["c1", "c2"]) await ajouterMembre(db, { utilisateur: c, role: "lecture", externe: false, perimetre: "tous", finAcces: null, ajoutePar: "s" }, T0);
    await db.ecrire('UPDATE "user" SET image = ? WHERE id = ?', "/api/compte/photo/c1?v=0123456789ab", "c1");
    const images = Object.fromEntries((await listerMembres(db)).map((m) => [m.utilisateur, m.image]));
    expect(images).toEqual({ c1: "/api/compte/photo/c1?v=0123456789ab", c2: null });
  });

  it("gardent toujours un superadmin", async () => {
    const s = await membre(db, { utilisateur: "s", role: "superadmin" });
    expect(await refusAsync(() => retirerMembre(db, s, "s", T0))).toMatchObject({ statut: 409, message: TA.dernierSuperadmin });
    expect(await refusAsync(() => modifierMembre(db, s, "s", { role: "lecture" }, T0))).toMatchObject({ statut: 409, message: TA.dernierSuperadmin });
    await membre(db, { utilisateur: "t", role: "superadmin" });
    await retirerMembre(db, s, "s", T0);
    expect(await membreEnCours(db, "s", T0)).toBeUndefined();
    expect(await refusAsync(() => retirerMembre(db, s, "s", T0))).toMatchObject({ statut: 404, message: TA.membreInconnu });
  });

  it("un membre qui gère l'équipe ne touche ni à sa ligne, ni à un superadmin, ni au-delà de ses droits ou de son périmètre", async () => {
    const s = await membre(db, { utilisateur: "s", role: "superadmin" });
    const gestion = await creerRole(db, s, { nom: "Gestion", droits: ["clients.voir", "equipe.gerer"] });
    const petit = await creerRole(db, s, { nom: "Petit", droits: ["clients.voir"] });
    const m = await membre(db, { utilisateur: "m", role: gestion.id, perimetre: ["a1"] });
    await membre(db, { utilisateur: "n", role: petit.id, perimetre: ["a1"] });
    await membre(db, { utilisateur: "g", role: "administration", perimetre: ["a1"] });
    for (const [qui, corps] of [
      ["m", { finAcces: "2026-12-31" }],
      ["s", { finAcces: "2026-12-31" }],
      ["n", { role: "lecture" }],
      ["n", { perimetre: ["b2"] }],
      ["n", { perimetre: "tous" }],
      ["g", { role: petit.id }],
    ] as const) {
      expect(await refusAsync(() => modifierMembre(db, m, qui, corps, T0)), `${qui} ${JSON.stringify(corps)}`).toMatchObject({ statut: 403, message: TA.escalade });
    }
    expect(await refusAsync(() => retirerMembre(db, m, "s", T0))).toMatchObject({ statut: 403, message: TA.escalade });
    expect(await refusAsync(() => retirerMembre(db, m, "g", T0))).toMatchObject({ statut: 403, message: TA.escalade });
    expect(await modifierMembre(db, m, "n", { perimetre: ["a1"], finAcces: "2026-12-31" }, T0)).toMatchObject({ perimetre: ["a1"], finAcces: "2026-12-31" });
    await retirerMembre(db, m, "n", T0);
    expect(await membreEnCours(db, "n", T0)).toBeUndefined();
  });

  it("refusent une valeur mal formée", async () => {
    const s = await membre(db, { utilisateur: "s", role: "superadmin" });
    await membre(db, { utilisateur: "n", role: "lecture" });
    expect(await refusAsync(() => modifierMembre(db, s, "n", { role: "absent" }, T0))).toMatchObject({ statut: 400, message: TA.roleInconnu });
    expect(await refusAsync(() => modifierMembre(db, s, "n", { finAcces: "31.12.2026" }, T0))).toMatchObject({ statut: 400, message: TA.finAccesInvalide });
    expect(await refusAsync(() => modifierMembre(db, s, "n", { finAcces: "2026-02-30" }, T0))).toMatchObject({ statut: 400, message: TA.finAccesInvalide });
    expect(await refusAsync(() => modifierMembre(db, s, "n", { perimetre: ["Garage"] }, T0))).toMatchObject({ statut: 400, message: TA.perimetreInvalide });
    expect(await refusAsync(() => modifierMembre(db, s, "absent", { finAcces: null }, T0))).toMatchObject({ statut: 404, message: TA.membreInconnu });
  });

  it("un externe a un périmètre, n'est jamais superadmin, et ne garde que trois droits", async () => {
    await compte(db, { id: "e", courriel: "e@megga.test" });
    const ajout = { utilisateur: "e", externe: true, finAcces: null, ajoutePar: null };
    expect(await refusAsync(() => ajouterMembre(db, { ...ajout, role: "lecture", perimetre: "tous" }, T0))).toMatchObject({ statut: 400, message: TA.externePerimetre });
    expect(await refusAsync(() => ajouterMembre(db, { ...ajout, role: "superadmin", perimetre: ["a1"] }, T0)))
      .toMatchObject({ statut: 400, message: TA.externeSuperadmin });
    await ajouterMembre(db, { ...ajout, role: "administration", perimetre: ["garage-essai"] }, T0);
    const e = (await accesDe(db, { id: "e", email: "e@megga.test", name: "E" }, T0))!;
    expect([...e.droits].sort()).toEqual([...DROITS_EXTERNE].sort());
    expect(e).toMatchObject({ externe: true, superadmin: false, perimetre: ["garage-essai"] });
    const s = await membre(db, { utilisateur: "s", role: "superadmin" });
    expect(await refusAsync(() => modifierMembre(db, s, "e", { role: "superadmin" }, T0))).toMatchObject({ statut: 400, message: TA.externeSuperadmin });
    expect(await refusAsync(() => modifierMembre(db, s, "e", { perimetre: "tous" }, T0))).toMatchObject({ statut: 400, message: TA.externePerimetre });
  });

  it("un superadmin a tous les clients et pas de fin d'accès", async () => {
    await compte(db, { id: "t", courriel: "t@megga.test" });
    const t = await ajouterMembre(db, { utilisateur: "t", role: "superadmin", externe: false, perimetre: ["a1"], finAcces: "2026-12-01", ajoutePar: null }, T0);
    expect(t).toMatchObject({ perimetre: "tous", finAcces: null });
    const s = await membre(db, { utilisateur: "s", role: "superadmin" });
    await membre(db, { utilisateur: "n", role: "lecture", perimetre: ["a1"], finAcces: "2026-12-31" });
    expect(await modifierMembre(db, s, "n", { role: "superadmin" }, T0)).toMatchObject({ role: "superadmin", perimetre: "tous", finAcces: null });
    const a = (await accesDe(db, { id: "n", email: "n@megga.test", name: "N" }, T0))!;
    expect(a).toMatchObject({ superadmin: true, perimetre: "tous", role: { id: "superadmin", nom: TA.roleSuperadmin } });
    expect(a.droits.size).toBe(13);
  });

  it("un compte suspendu ne devient pas superadmin : 409, rien ne change ; réactivé, il le peut", async () => {
    const s = await membre(db, { utilisateur: "s", role: "superadmin" });
    await membre(db, { utilisateur: "n", role: "lecture" });
    await db.ecrire("UPDATE \"user\" SET banned = ? WHERE id = 'n'", true);
    expect(await refusAsync(() => modifierMembre(db, s, "n", { role: "superadmin" }, T0))).toMatchObject({ statut: 409, message: TA.superadminSuspendu });
    expect((await listerMembres(db)).find((m) => m.utilisateur === "n")?.role).toBe("lecture");
    expect(await modifierMembre(db, s, "n", { role: "finance" }, T0)).toMatchObject({ role: "finance" }); // un autre rôle reste permis
    await db.ecrire("UPDATE \"user\" SET banned = ? WHERE id = 'n'", false);
    expect(await modifierMembre(db, s, "n", { role: "superadmin" }, T0)).toMatchObject({ role: "superadmin" });
  });
});
