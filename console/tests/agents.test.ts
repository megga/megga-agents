import { DatabaseSync } from "node:sqlite";
import { beforeEach, describe, expect, it } from "vitest";
import { creer, epingler, lister, Refus, trouver, valider } from "@/lib/agents";

let db: DatabaseSync;
beforeEach(() => {
  db = new DatabaseSync(":memory:");
  db.exec(`CREATE TABLE agent (id TEXT PRIMARY KEY, utilisateur TEXT NOT NULL, prenom TEXT NOT NULL, metier TEXT NOT NULL,
    couleur INTEGER NOT NULL DEFAULT 0, yeux INTEGER NOT NULL DEFAULT 0, epingle INTEGER NOT NULL DEFAULT 0, cree_le TEXT NOT NULL)`);
});

function refus(f: () => unknown): Refus {
  try {
    f();
  } catch (e) {
    if (e instanceof Refus) return e;
    throw e;
  }
  throw new Error("aucun refus");
}

describe("la création d'un agent", () => {
  it("demande un prénom et un métier, rien d'autre", () => {
    expect(refus(() => valider({ metier: "garage" })).message).toBe("Donnez-lui un prénom.");
    expect(refus(() => valider({ prenom: "Lou" })).message).toBe("Choisissez un métier.");
    expect(refus(() => valider({ prenom: "Lou", metier: "boulangerie" })).statut).toBe(400);
    expect(valider({ prenom: "  Lou  ", metier: "garage" })).toEqual({ prenom: "Lou", metier: "garage", couleur: 0, yeux: 0 });
  });

  it("borne le prénom à 20 caractères et ignore une couleur inconnue", () => {
    expect(refus(() => valider({ prenom: "x".repeat(21), metier: "sante" })).message).toContain("20");
    expect(valider({ prenom: "Éloïse", metier: "sante", couleur: 42, yeux: 2 })).toMatchObject({ couleur: 0, yeux: 2 });
  });

  it("range l'agent dans le compte, en service tout de suite, le plus récent en premier", () => {
    const a = creer(db, "u1", { prenom: "Alix", metier: "immobilier" }, new Date("2026-11-17T10:00:00Z"));
    const b = creer(db, "u1", { prenom: "Léa", metier: "sante", couleur: 1 }, new Date("2026-11-17T11:00:00Z"));
    expect(a.id).toMatch(/^ag_[0-9a-f]{20}$/);
    expect(lister(db, "u1").map((x) => x.prenom)).toEqual(["Léa", "Alix"]);
    expect(b).toMatchObject({ couleur: 1, epingle: false });
  });

  it("ne montre jamais l'agent d'un autre compte", () => {
    const a = creer(db, "u1", { prenom: "Alix", metier: "immobilier" });
    expect(lister(db, "u2")).toEqual([]);
    expect(trouver(db, "u2", a.id)).toBeUndefined();
    expect(refus(() => epingler(db, "u2", a.id, true)).statut).toBe(404);
  });
});

describe("les épinglés", () => {
  it("sont trois au plus", () => {
    const ids = ["A", "B", "C", "D"].map((p) => creer(db, "u1", { prenom: p, metier: "commerce" }).id);
    for (const id of ids.slice(0, 3)) expect(epingler(db, "u1", id, true).epingle).toBe(true);
    const r = refus(() => epingler(db, "u1", ids[3], true));
    expect(r.statut).toBe(409);
    expect(r.message).toBe("3 agents épinglés au maximum. Désépinglez-en un d'abord.");
    expect(epingler(db, "u1", ids[0], false).epingle).toBe(false);
    expect(epingler(db, "u1", ids[3], true).epingle).toBe(true);
  });
});
