import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { METIERS } from "@/lib/metiers";
import { T } from "@/lib/textes";

function tousLesTextes(): string[] {
  const t: string[] = [];
  for (const v of Object.values(T)) {
    if (typeof v === "string") t.push(v);
    else t.push((v as (...a: unknown[]) => string)("Alix", "à l'accueil de votre agence"));
  }
  for (const m of METIERS) t.push(m.nom, m.sous, m.qui);
  return t;
}

function fichiers(dossier: string): string[] {
  return readdirSync(dossier).flatMap((n) => {
    const c = join(dossier, n);
    return statSync(c).isDirectory() ? fichiers(c) : /\.(tsx?|css)$/.test(n) ? [c] : [];
  });
}

describe("les textes visibles", () => {
  it("n'ont ni point médian, ni tiret long ou demi-cadratin", () => {
    for (const t of tousLesTextes()) expect(t, t).not.toMatch(/[·–—]/);
  });

  it("ont l'espace insécable de la typographie française", () => {
    for (const t of tousLesTextes()) {
      expect(t, t).not.toMatch(/ [?:!;»]/);
      expect(t, t).not.toMatch(/« /);
    }
  });

  it("sont en français dans tout le code de l'écran (ni point médian ni tiret long nulle part)", () => {
    for (const f of fichiers(join(__dirname, "../src"))) {
      if (f.includes("tete-source")) continue;
      expect(readFileSync(f, "utf8"), f).not.toMatch(/[·–—]/);
    }
  });
});
