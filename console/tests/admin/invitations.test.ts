import { createHash } from "node:crypto";
import { beforeEach, describe, expect, it } from "vitest";
import {
  accepterInvitation,
  creerInvitation,
  DUREE_INVITATION_JOURS,
  empreinte,
  etatInvitation,
  invitationsEnAttente,
  inviterSuperadmin,
  lireInvitation,
  retirerInvitation,
} from "@/lib/admin/invitations";
import { accesDe, membreEnCours } from "@/lib/admin/membres";
import { creerRole, lireRole, retirerRole } from "@/lib/admin/roles";
import { TA } from "@/lib/admin/textes";
import type { Base } from "@/lib/donnees/base";
import { baseEssai, compte, membre, refusAsync, T0 } from "./aides";

let db: Base;
beforeEach(async () => {
  db = await baseEssai();
});

const JOUR = 24 * 3600 * 1000;
const apres = (ms: number) => new Date(T0.getTime() + ms);
const chef = { courriel: "Chef@Megga.test ", role: "administration", externe: false, perimetre: "tous", finAcces: null };

describe("une invitation", () => {
  it("donne un lien montré une fois ; la base n'en garde que l'empreinte", async () => {
    const s = await membre(db, { utilisateur: "s", role: "superadmin" });
    const { invitation, jeton, lien } = await creerInvitation(db, s, chef, T0);
    expect(jeton).toMatch(/^[A-Za-z0-9_-]{43}$/);
    expect(lien).toBe("/admin/invitation/" + jeton);
    expect(invitation).toMatchObject({ courriel: "chef@megga.test", role: "administration", externe: false, perimetre: "tous", finAcces: null,
      creeePar: "s", creeeLe: T0.toISOString() });
    const lignes = (await db.tous("SELECT * FROM admin_invitation")) as Record<string, unknown>[];
    expect(lignes).toHaveLength(1);
    expect(lignes[0].empreinte).toBe(createHash("sha256").update(jeton).digest("hex"));
    expect(empreinte(jeton)).toBe(lignes[0].empreinte);
    for (const v of Object.values(lignes[0])) expect(String(v)).not.toContain(jeton);
  });

  it("vaut sept jours", async () => {
    const s = await membre(db, { utilisateur: "s", role: "superadmin" });
    const { invitation, jeton } = await creerInvitation(db, s, chef, T0);
    expect(DUREE_INVITATION_JOURS).toBe(7);
    expect(invitation.valableJusqua).toBe(apres(7 * JOUR).toISOString());
    expect(await lireInvitation(db, jeton, apres(7 * JOUR - 1))).toBeDefined();
    expect(await lireInvitation(db, jeton, apres(7 * JOUR + 1))).toBeUndefined();
    expect((await invitationsEnAttente(db, apres(7 * JOUR - 1))).map((i) => i.id)).toEqual([invitation.id]);
    expect(await invitationsEnAttente(db, apres(7 * JOUR + 1))).toEqual([]);
    expect(await lireInvitation(db, "inconnu", T0)).toBeUndefined();
    expect(await refusAsync(() => accepterInvitation(db, jeton, { id: "c", email: "chef@megga.test" }, apres(7 * JOUR + 1))))
      .toMatchObject({ statut: 404, message: TA.invitationInvalide });
  });

  it("s'accepte une seule fois, par le courriel invité, quelle que soit sa casse", async () => {
    const s = await membre(db, { utilisateur: "s", role: "superadmin" });
    const { jeton } = await creerInvitation(db, s, chef, T0);
    await compte(db, { id: "c", courriel: "chef@megga.test" });
    expect(await refusAsync(() => accepterInvitation(db, jeton, { id: "a", email: "autre@megga.test" }, T0)))
      .toMatchObject({ statut: 403, message: TA.autreCourriel });
    const m = await accepterInvitation(db, jeton, { id: "c", email: "CHEF@megga.test" }, T0);
    expect(m).toMatchObject({ utilisateur: "c", role: "administration", externe: false, perimetre: "tous", ajoutePar: "s" });
    expect((await accesDe(db, { id: "c", email: "chef@megga.test", name: "C" }, T0))?.role.id).toBe("administration");
    expect(await refusAsync(() => accepterInvitation(db, jeton, { id: "c", email: "chef@megga.test" }, T0)))
      .toMatchObject({ statut: 404, message: TA.invitationInvalide });
    expect(await invitationsEnAttente(db, T0)).toEqual([]);
  });

  it("se retire, et ne vaut plus rien ensuite ; un membre en cours ne la reprend pas", async () => {
    const s = await membre(db, { utilisateur: "s", role: "superadmin" });
    const { invitation, jeton } = await creerInvitation(db, s, chef, T0);
    await retirerInvitation(db, s, invitation.id, T0);
    expect(await refusAsync(() => accepterInvitation(db, jeton, { id: "c", email: "chef@megga.test" }, T0)))
      .toMatchObject({ statut: 404, message: TA.invitationInvalide });
    expect(await refusAsync(() => retirerInvitation(db, s, invitation.id, T0))).toMatchObject({ statut: 404, message: TA.invitationInvalide });
    const autre = await creerInvitation(db, s, { ...chef, courriel: "s@megga.test" }, T0);
    expect(await refusAsync(() => accepterInvitation(db, autre.jeton, { id: "s", email: "s@megga.test" }, T0)))
      .toMatchObject({ statut: 409, message: TA.dejaMembre });
    expect(await lireInvitation(db, autre.jeton, T0)).toBeDefined();
  });

  it("garde les règles d'un membre : pas d'escalade, un externe a un périmètre", async () => {
    const s = await membre(db, { utilisateur: "s", role: "superadmin" });
    const gestion = await creerRole(db, s, { nom: "Gestion", droits: ["clients.voir", "equipe.gerer"] });
    const petit = await creerRole(db, s, { nom: "Petit", droits: ["clients.voir"] });
    const m = await membre(db, { utilisateur: "m", role: gestion.id, perimetre: ["a1"] });
    const corps = { courriel: "n@megga.test", externe: false, perimetre: ["a1"], finAcces: null };
    expect(await refusAsync(() => creerInvitation(db, m, { ...corps, role: "superadmin" }, T0))).toMatchObject({ statut: 403, message: TA.escalade });
    expect(await refusAsync(() => creerInvitation(db, m, { ...corps, role: "lecture" }, T0))).toMatchObject({ statut: 403, message: TA.escalade });
    expect(await refusAsync(() => creerInvitation(db, m, { ...corps, role: petit.id, perimetre: ["b2"] }, T0))).toMatchObject({ statut: 403, message: TA.escalade });
    expect((await refusAsync(() => creerInvitation(db, m, { ...corps, role: petit.id, externe: true, perimetre: "tous" }, T0))).statut).toBe(400);
    expect(await refusAsync(() => creerInvitation(db, s, { ...corps, role: "superadmin", externe: true, perimetre: ["a1"] }, T0)))
      .toMatchObject({ statut: 400, message: TA.externeSuperadmin });
    expect(await refusAsync(() => creerInvitation(db, s, { ...corps, role: "absent" }, T0))).toMatchObject({ statut: 400, message: TA.roleInconnu });
    expect(await refusAsync(() => creerInvitation(db, s, { ...corps, role: petit.id, finAcces: "demain" }, T0)))
      .toMatchObject({ statut: 400, message: TA.finAccesInvalide });
    const { invitation } = await creerInvitation(db, m, { ...corps, role: petit.id, externe: true, finAcces: "2026-12-31" }, T0);
    expect(invitation).toMatchObject({ role: petit.id, externe: true, perimetre: ["a1"], finAcces: "2026-12-31", creeePar: "m" });
    const large = await creerInvitation(db, s, { ...corps, role: "administration", perimetre: "tous" }, T0);
    expect(await refusAsync(() => retirerInvitation(db, m, large.invitation.id, T0))).toMatchObject({ statut: 403, message: TA.escalade });
    await retirerInvitation(db, m, invitation.id, T0);
  });

  it("tient son rôle : il ne se retire pas tant qu'elle est en attente", async () => {
    const s = await membre(db, { utilisateur: "s", role: "superadmin" });
    const petit = await creerRole(db, s, { nom: "Petit", droits: ["clients.voir"] });
    const { invitation } = await creerInvitation(db, s, { ...chef, role: petit.id }, T0);
    expect(await refusAsync(() => retirerRole(db, s, petit.id, T0))).toMatchObject({ statut: 409, message: TA.rolePorte });
    await retirerInvitation(db, s, invitation.id, T0);
    await retirerRole(db, s, petit.id, T0);
    expect(await lireRole(db, petit.id)).toBeUndefined();
    const autre = await creerRole(db, s, { nom: "Autre", droits: ["clients.voir"] });
    await creerInvitation(db, s, { ...chef, role: autre.id }, T0);
    expect((await refusAsync(() => retirerRole(db, s, autre.id, apres(7 * JOUR - 1)))).statut).toBe(409);
    await retirerRole(db, s, autre.id, apres(7 * JOUR + 1));
    expect(await lireRole(db, autre.id)).toBeUndefined();
  });

  it("au rôle superadmin, vaut pour tous les clients et sans fin", async () => {
    const s = await membre(db, { utilisateur: "s", role: "superadmin" });
    const { invitation, jeton } = await creerInvitation(db, s, { ...chef, role: "superadmin", perimetre: ["a1"], finAcces: "2026-12-31" }, T0);
    expect(invitation).toMatchObject({ perimetre: "tous", finAcces: null });
    await compte(db, { id: "c", courriel: "chef@megga.test" });
    expect(await accepterInvitation(db, jeton, { id: "c", email: "chef@megga.test" }, T0)).toMatchObject({ role: "superadmin", perimetre: "tous" });
  });
});

describe("la commande des premiers superadmins", () => {
  it("imprime un lien complet d'invitation superadmin", async () => {
    const lien = await inviterSuperadmin(db, "chef@megga.test", "http://localhost:3000", T0);
    expect(lien).toMatch(/^http:\/\/localhost:3000\/admin\/invitation\/[A-Za-z0-9_-]{43}$/);
    const i = (await lireInvitation(db, lien.split("/").at(-1)!, T0))!;
    expect(i).toMatchObject({ courriel: "chef@megga.test", role: "superadmin", externe: false, perimetre: "tous", finAcces: null, creeePar: null });
    expect(await refusAsync(() => inviterSuperadmin(db, "chef.megga.test", "http://localhost:3000", T0))).toMatchObject({ statut: 400, message: TA.courrielInvalide });
    await compte(db, { id: "c", courriel: "chef@megga.test" });
    await accepterInvitation(db, lien.split("/").at(-1)!, { id: "c", email: "chef@megga.test" }, T0);
    expect(await membreEnCours(db, "c", T0)).toMatchObject({ role: "superadmin", ajoutePar: null });
  });
});

describe("la page du lien", () => {
  it("sait quoi montrer", async () => {
    const s = await membre(db, { utilisateur: "s", role: "superadmin" });
    const { jeton } = await creerInvitation(db, s, chef, T0);
    const i = await lireInvitation(db, jeton, T0);
    expect(etatInvitation(undefined, null)).toBe("invalide");
    expect(etatInvitation(undefined, "chef@megga.test")).toBe("invalide");
    expect(etatInvitation(i, "chef@megga.test")).toBe("rejoindre");
    expect(etatInvitation(i, " Chef@Megga.TEST")).toBe("rejoindre");
    expect(etatInvitation(i, "x@y.z")).toBe("autre_courriel");
    expect(etatInvitation(i, null)).toBe("sans_session");
  });
});
