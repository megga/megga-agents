import { describe, expect, it } from "vitest";
import { DROITS, DROITS_EXTERNE, estDroit, GROUPES_DE_DROITS, ROLES_DE_DEPART, SUPERADMIN } from "@/lib/admin/droits";

describe("les droits de l'admin", () => {
  it("sont treize, fixés dans le code, chacun dans un seul groupe ; un externe n'en garde que deux", () => {
    expect(DROITS).toEqual(["clients.voir", "couts.voir", "clients.creer", "versions.preparer", "clients.piloter",
      "acces.gerer", "installations.gerer", "tarifs.regler", "comptes.voir", "comptes.gerer", "equipe.gerer", "journal.voir", "alertes.regler"]);
    expect([estDroit("couts.voir"), estDroit("couts.voir ")]).toEqual([true, false]);
    expect([estDroit(undefined), estDroit(3), estDroit("toString")]).toEqual([false, false, false]);
    expect(GROUPES_DE_DROITS.flatMap((g) => g.droits).sort()).toEqual([...DROITS].sort());
    expect(DROITS_EXTERNE).toEqual(["clients.voir", "versions.preparer"]);
    expect(estDroit("conversations.lire")).toBe(false); // MEGGA ne lit jamais une conversation (20.11.2026)
  });

  it("des quatre rôles de départ sont ceux de la conception", () => {
    const r = Object.fromEntries(ROLES_DE_DEPART.map((x) => [x.id, [...x.droits].sort()]));
    expect(Object.keys(r)).toEqual(["administration", "exploitation", "finance", "lecture"]);
    expect(r.administration).toEqual([...DROITS].sort());
    expect(r.exploitation).toEqual(["acces.gerer", "alertes.regler", "clients.creer", "clients.piloter", "clients.voir", "comptes.gerer", "comptes.voir",
      "installations.gerer", "versions.preparer"]);
    expect(r.finance).toEqual(["clients.voir", "comptes.voir", "couts.voir", "tarifs.regler"]);
    expect(r.lecture).toEqual(["clients.voir", "comptes.voir"]);
    expect(SUPERADMIN).toBe("superadmin");
    expect(ROLES_DE_DEPART.map((x) => x.id)).not.toContain(SUPERADMIN);
  });
});
