import { describe, expect, it } from "vitest";
import { COULEURS, teteSvg, YEUX } from "@/lib/mascotte/couleurs";
import { TETE_SVG } from "@/lib/mascotte/tete-source";

const formes = (s: string) => s.replace(/#[0-9A-Fa-f]{6}/g, "#");

describe("la tête de la mascotte", () => {
  it("garde la forme du logo GG : seules les couleurs changent", () => {
    for (let c = 0; c < COULEURS.length; c++)
      for (let y = 0; y < YEUX.length; y++)
        for (const sombre of [false, true]) expect(formes(teteSvg(c, y, sombre))).toBe(formes(TETE_SVG));
  });

  it("prend la couleur et les yeux choisis", () => {
    const s = teteSvg(2, 1, false);
    expect(s).toContain(COULEURS[2][1][0]);
    expect(s).not.toContain(COULEURS[0][1][0]);
    expect(s).toContain(YEUX[1][1][0]);
  });

  it("éclaircit les sourcils en sombre, comme la maquette", () => {
    expect(teteSvg(0, 0, true)).toMatch(/id="sourcilG" fill="#F0584A"/);
    expect(teteSvg(0, 0, false)).toMatch(/id="sourcilG" fill="#871510"/);
  });

  it("retombe sur le rouge et le marron pour une valeur inconnue", () => {
    expect(teteSvg(99, -1, false)).toBe(teteSvg(0, 0, false));
  });
});
