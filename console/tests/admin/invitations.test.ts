import { createHash } from "node:crypto";
import type { DatabaseSync } from "node:sqlite";
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
import { creerRole } from "@/lib/admin/roles";
import { TA } from "@/lib/admin/textes";
import { baseEssai, compte, membre, refus, T0 } from "./aides";

let db: DatabaseSync;
beforeEach(async () => {
  db = await baseEssai();
});

const JOUR = 24 * 3600 * 1000;
const apres = (ms: number) => new Date(T0.getTime() + ms);
const chef = { courriel: "Chef@Megga.test ", role: "administration", externe: false, perimetre: "tous", finAcces: null };

describe("une invitation", () => {
  it("donne un lien montré une fois ; la base n'en garde que l'empreinte", () => {
    const s = membre(db, { utilisateur: "s", role: "superadmin" });
    const { invitation, jeton, lien } = creerInvitation(db, s, chef, T0);
    expect(jeton).toMatch(/^[A-Za-z0-9_-]{43}$/);
    expect(lien).toBe("/admin/invitation/" + jeton);
    expect(invitation).toMatchObject({ courriel: "chef@megga.test", role: "administration", externe: false, perimetre: "tous", finAcces: null,
      creeePar: "s", creeeLe: T0.toISOString() });
    const lignes = db.prepare("SELECT * FROM admin_invitation").all() as Record<string, unknown>[];
    expect(lignes).toHaveLength(1);
    expect(lignes[0].empreinte).toBe(createHash("sha256").update(jeton).digest("hex"));
    expect(empreinte(jeton)).toBe(lignes[0].empreinte);
    for (const v of Object.values(lignes[0])) expect(String(v)).not.toContain(jeton);
  });

  it("vaut sept jours", () => {
    const s = membre(db, { utilisateur: "s", role: "superadmin" });
    const { invitation, jeton } = creerInvitation(db, s, chef, T0);
    expect(DUREE_INVITATION_JOURS).toBe(7);
    expect(invitation.valableJusqua).toBe(apres(7 * JOUR).toISOString());
    expect(lireInvitation(db, jeton, apres(7 * JOUR - 1))).toBeDefined();
    expect(lireInvitation(db, jeton, apres(7 * JOUR + 1))).toBeUndefined();
    expect(invitationsEnAttente(db, apres(7 * JOUR - 1)).map((i) => i.id)).toEqual([invitation.id]);
    expect(invitationsEnAttente(db, apres(7 * JOUR + 1))).toEqual([]);
    expect(lireInvitation(db, "inconnu", T0)).toBeUndefined();
    expect(refus(() => accepterInvitation(db, jeton, { id: "c", email: "chef@megga.test" }, apres(7 * JOUR + 1))))
      .toMatchObject({ statut: 404, message: TA.invitationInvalide });
  });

  it("s'accepte une seule fois, par le courriel invité, quelle que soit sa casse", () => {
    const s = membre(db, { utilisateur: "s", role: "superadmin" });
    const { jeton } = creerInvitation(db, s, chef, T0);
    compte(db, { id: "c", courriel: "chef@megga.test" });
    expect(refus(() => accepterInvitation(db, jeton, { id: "a", email: "autre@megga.test" }, T0)))
      .toMatchObject({ statut: 403, message: TA.autreCourriel });
    const m = accepterInvitation(db, jeton, { id: "c", email: "CHEF@megga.test" }, T0);
    expect(m).toMatchObject({ utilisateur: "c", role: "administration", externe: false, perimetre: "tous", ajoutePar: "s" });
    expect(accesDe(db, { id: "c", email: "chef@megga.test", name: "C" }, T0)?.role.id).toBe("administration");
    expect(refus(() => accepterInvitation(db, jeton, { id: "c", email: "chef@megga.test" }, T0)))
      .toMatchObject({ statut: 404, message: TA.invitationInvalide });
    expect(invitationsEnAttente(db, T0)).toEqual([]);
  });

  it("se retire, et ne vaut plus rien ensuite ; un membre en cours ne la reprend pas", () => {
    const s = membre(db, { utilisateur: "s", role: "superadmin" });
    const { invitation, jeton } = creerInvitation(db, s, chef, T0);
    retirerInvitation(db, s, invitation.id, T0);
    expect(refus(() => accepterInvitation(db, jeton, { id: "c", email: "chef@megga.test" }, T0)))
      .toMatchObject({ statut: 404, message: TA.invitationInvalide });
    expect(refus(() => retirerInvitation(db, s, invitation.id, T0))).toMatchObject({ statut: 404, message: TA.invitationInvalide });
    const autre = creerInvitation(db, s, { ...chef, courriel: "s@megga.test" }, T0);
    expect(refus(() => accepterInvitation(db, autre.jeton, { id: "s", email: "s@megga.test" }, T0)))
      .toMatchObject({ statut: 409, message: TA.dejaMembre });
    expect(lireInvitation(db, autre.jeton, T0)).toBeDefined();
  });

  it("garde les règles d'un membre : pas d'escalade, un externe a un périmètre", () => {
    const s = membre(db, { utilisateur: "s", role: "superadmin" });
    const gestion = creerRole(db, s, { nom: "Gestion", droits: ["clients.voir", "equipe.gerer"] });
    const petit = creerRole(db, s, { nom: "Petit", droits: ["clients.voir"] });
    const m = membre(db, { utilisateur: "m", role: gestion.id, perimetre: ["a1"] });
    const corps = { courriel: "n@megga.test", externe: false, perimetre: ["a1"], finAcces: null };
    expect(refus(() => creerInvitation(db, m, { ...corps, role: "superadmin" }, T0))).toMatchObject({ statut: 403, message: TA.escalade });
    expect(refus(() => creerInvitation(db, m, { ...corps, role: "lecture" }, T0))).toMatchObject({ statut: 403, message: TA.escalade });
    expect(refus(() => creerInvitation(db, m, { ...corps, role: petit.id, perimetre: ["b2"] }, T0))).toMatchObject({ statut: 403, message: TA.escalade });
    expect(refus(() => creerInvitation(db, m, { ...corps, role: petit.id, externe: true, perimetre: "tous" }, T0)).statut).toBe(400);
    expect(refus(() => creerInvitation(db, s, { ...corps, role: "superadmin", externe: true, perimetre: ["a1"] }, T0)))
      .toMatchObject({ statut: 400, message: TA.externeSuperadmin });
    expect(refus(() => creerInvitation(db, s, { ...corps, role: "absent" }, T0))).toMatchObject({ statut: 400, message: TA.roleInconnu });
    expect(refus(() => creerInvitation(db, s, { ...corps, role: petit.id, finAcces: "demain" }, T0)))
      .toMatchObject({ statut: 400, message: TA.finAccesInvalide });
    const { invitation } = creerInvitation(db, m, { ...corps, role: petit.id, externe: true, finAcces: "2026-12-31" }, T0);
    expect(invitation).toMatchObject({ role: petit.id, externe: true, perimetre: ["a1"], finAcces: "2026-12-31", creeePar: "m" });
    const large = creerInvitation(db, s, { ...corps, role: "administration", perimetre: "tous" }, T0);
    expect(refus(() => retirerInvitation(db, m, large.invitation.id, T0))).toMatchObject({ statut: 403, message: TA.escalade });
    retirerInvitation(db, m, invitation.id, T0);
  });

  it("au rôle superadmin, vaut pour tous les clients et sans fin", () => {
    const s = membre(db, { utilisateur: "s", role: "superadmin" });
    const { invitation, jeton } = creerInvitation(db, s, { ...chef, role: "superadmin", perimetre: ["a1"], finAcces: "2026-12-31" }, T0);
    expect(invitation).toMatchObject({ perimetre: "tous", finAcces: null });
    compte(db, { id: "c", courriel: "chef@megga.test" });
    expect(accepterInvitation(db, jeton, { id: "c", email: "chef@megga.test" }, T0)).toMatchObject({ role: "superadmin", perimetre: "tous" });
  });
});

describe("la commande des premiers superadmins", () => {
  it("imprime un lien complet d'invitation superadmin", () => {
    const lien = inviterSuperadmin(db, "chef@megga.test", "http://localhost:3000", T0);
    expect(lien).toMatch(/^http:\/\/localhost:3000\/admin\/invitation\/[A-Za-z0-9_-]{43}$/);
    const i = lireInvitation(db, lien.split("/").at(-1)!, T0)!;
    expect(i).toMatchObject({ courriel: "chef@megga.test", role: "superadmin", externe: false, perimetre: "tous", finAcces: null, creeePar: null });
    expect(refus(() => inviterSuperadmin(db, "chef.megga.test", "http://localhost:3000", T0))).toMatchObject({ statut: 400, message: TA.courrielInvalide });
    compte(db, { id: "c", courriel: "chef@megga.test" });
    accepterInvitation(db, lien.split("/").at(-1)!, { id: "c", email: "chef@megga.test" }, T0);
    expect(membreEnCours(db, "c", T0)).toMatchObject({ role: "superadmin", ajoutePar: null });
  });
});

describe("la page du lien", () => {
  it("sait quoi montrer", () => {
    const s = membre(db, { utilisateur: "s", role: "superadmin" });
    const { jeton } = creerInvitation(db, s, chef, T0);
    const i = lireInvitation(db, jeton, T0);
    expect(etatInvitation(undefined, null)).toBe("invalide");
    expect(etatInvitation(undefined, "chef@megga.test")).toBe("invalide");
    expect(etatInvitation(i, "chef@megga.test")).toBe("rejoindre");
    expect(etatInvitation(i, " Chef@Megga.TEST")).toBe("rejoindre");
    expect(etatInvitation(i, "x@y.z")).toBe("autre_courriel");
    expect(etatInvitation(i, null)).toBe("sans_session");
  });
});
