import { describe, expect, it } from "vitest";
import { ROLES_DE_DEPART, SUPERADMIN } from "@/lib/admin/droits";
import { creerTablesAdmin } from "@/lib/admin/tables";
import { moteursEssai } from "../moteurs";
import { baseEssai, T0 } from "./aides";

// Les tables de l'admin, sous chaque moteur d'essai (Postgres seulement si CONSOLE_BASE_ESSAI_URL est posée).

const ROLE = "INSERT INTO admin_role (id, nom, description, droits, systeme, cree_le, modifie_le) VALUES (?, ?, '', '[]', 0, ?, ?)";

describe.each(moteursEssai())("les tables de l'admin, sous %s", (moteur) => {
  it("ont le superadmin et les rôles de départ", async () => {
    const b = await baseEssai(moteur);
    const ids = (await b.tous<{ id: string }>("SELECT id FROM admin_role ORDER BY id")).map((r) => r.id);
    expect(ids).toEqual([SUPERADMIN, ...ROLES_DE_DEPART.map((r) => r.id)].sort());
  });

  it("refusent deux rôles du même nom, sans tenir compte de la casse", async () => {
    const b = await baseEssai(moteur);
    await b.ecrire(ROLE, "r1", "Revue", T0.toISOString(), T0.toISOString());
    await expect(b.ecrire(ROLE, "r2", "revue", T0.toISOString(), T0.toISOString())).rejects.toThrow();
    expect(await b.tous("SELECT id FROM admin_role WHERE lower(nom) = 'revue'")).toEqual([{ id: "r1" }]);
  });

  it("se recréent sans rien doubler ni remettre un rôle de départ retiré", async () => {
    const b = await baseEssai(moteur);
    await b.ecrire("DELETE FROM admin_role WHERE id = ?", "finance");
    await creerTablesAdmin(b, T0);
    await creerTablesAdmin(b, T0);
    const ids = (await b.tous<{ id: string }>("SELECT id FROM admin_role ORDER BY id")).map((r) => r.id);
    expect(ids).toEqual([SUPERADMIN, ...ROLES_DE_DEPART.map((r) => r.id)].filter((id) => id !== "finance").sort());
  });

  it("numérotent le journal", async () => {
    const b = await baseEssai(moteur);
    const ligne = "INSERT INTO admin_journal (quand, action, resultat) VALUES (?, 'essai', 'ok')";
    await b.ecrire(ligne, T0.toISOString());
    await b.ecrire(ligne, T0.toISOString());
    expect(await b.tous("SELECT id FROM admin_journal ORDER BY id")).toEqual([{ id: 1 }, { id: 2 }]);
  });
});
