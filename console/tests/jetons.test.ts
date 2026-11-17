import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const css = readFileSync(join(__dirname, "../src/app/globals.css"), "utf8");
const JETONS = ["bg", "side", "hover", "line", "ink", "muted", "faint", "accent", "on-accent", "ok", "warn", "soft", "shadow", "trait", "trait-fort"];

function bloc(selecteur: string): string {
  const i = css.indexOf(selecteur + " {");
  expect(i, selecteur).toBeGreaterThanOrEqual(0);
  return css.slice(i, css.indexOf("}", i));
}

describe("les jetons de la maquette", () => {
  it("sont tous définis en clair et en Nuit douce", () => {
    const clair = bloc(":root");
    const sombre = bloc(':root[data-theme="douce"]');
    for (const j of JETONS) {
      expect(clair, j).toMatch(new RegExp(`--${j}:`));
      expect(sombre, j).toMatch(new RegExp(`--${j}:`));
    }
  });

  it("reprennent les couleurs de la maquette", () => {
    expect(bloc(":root")).toContain("--accent: #e03e2a");
    expect(bloc(":root")).toContain("--ink: #1b1b2f");
    expect(bloc(':root[data-theme="douce"]')).toContain("--bg: #0f1014");
    expect(bloc(':root[data-theme="douce"]')).toContain("--accent: #f0584a");
  });

  it("font des contours d'un seul point d'écran", () => {
    expect(css).toContain("--fin: 1px");
    expect(css).toContain("--fin: 0.5px");
    expect(css).toMatch(/@utility trait \{\s*border: var\(--fin\) solid var\(--trait\)/);
  });

  it("n'affichent l'anneau de focus qu'au clavier", () => {
    expect(css).toMatch(/html\.souris :focus-visible \{\s*outline: none/);
  });
});
