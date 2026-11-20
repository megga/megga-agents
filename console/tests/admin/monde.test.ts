import { describe, expect, it } from "vitest";
import fond from "@/lib/admin/carte-monde.json";
import { vueMonde } from "@/lib/admin/monde";
import { CODES_PAYS, estPays, nomPays, paysTries } from "@/lib/admin/pays";
import type { LigneSante, Sante } from "@/lib/admin/releves";

// La carte du monde (20.11.2026) : les clients du périmètre par pays, sans réseau.

const ligne = (client: string, tours: number, sante: Sante = "ok"): LigneSante => ({
  client, entreprise: null, sante, soucis: [], tours, echecs: 0, secours: 0, reponse: null, reponseLente: null, releveLe: null,
});

describe("vueMonde", () => {
  it("range les clients par pays, le plus fourni d'abord, et compte ceux sans pays", () => {
    const v = vueMonde(
      [ligne("a", 10), ligne("b", 5, "panne"), ligne("c", 40), ligne("d", 1), ligne("e", 3)],
      [{ id: "a", pays: "CH" }, { id: "b", pays: "CH" }, { id: "c", pays: "ES" }, { id: "d", pays: null }],
    );
    expect(v.pays).toEqual([
      { code: "CH", clients: 2, tours: 15, aSurveiller: 1 },
      { code: "ES", clients: 1, tours: 40, aSurveiller: 0 },
    ]);
    expect(v.sansPays).toBe(2); // d sans pays, e absent de la liste
  });

  it("une installation suivie à part ne compte pas à surveiller", () => {
    expect(vueMonde([ligne("a", 0, "installation")], [{ id: "a", pays: "CH" }]).pays[0].aSurveiller).toBe(0);
  });
});

describe("pays", () => {
  it("connaît les codes ISO et les nomme en français", () => {
    expect(CODES_PAYS).toHaveLength(250);
    expect(estPays("CH") && !estPays("ch") && !estPays("ZZ") && !estPays(41)).toBe(true);
    expect(nomPays("CH")).toBe("Suisse");
    expect(nomPays("AE")).toBe("Émirats arabes unis");
    const noms = paysTries().map((p) => p.nom);
    expect(noms).toEqual([...noms].sort((x, y) => x.localeCompare(y, "fr")));
  });

  it("le fond de carte ne trace que des codes connus", () => {
    const codes = Object.keys(fond.pays);
    expect(codes.length).toBeGreaterThan(170);
    expect(codes.every(estPays)).toBe(true);
    expect(codes).toContain("CH");
    expect(codes).not.toContain("AQ");
  });
});
