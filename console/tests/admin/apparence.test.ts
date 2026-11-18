import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

// L'apparence de l'admin ne sort jamais des jetons de globals.css : ni couleur écrite en dur, ni police à part.

const CONSOLE = join(__dirname, "../..");
const COULEUR = /#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(|oklch\(/;

function fichiers(dossier: string): string[] {
  if (!existsSync(dossier)) return []; // pas encore écrit : rien à vérifier
  return readdirSync(dossier).flatMap((n) => {
    const c = join(dossier, n);
    return statSync(c).isDirectory() ? fichiers(c) : /\.(tsx?|css)$/.test(n) ? [c] : [];
  });
}

describe("l'apparence de l'admin", () => {
  const tous = ["src/components/admin", "src/app/admin"].flatMap((d) => fichiers(join(CONSOLE, d)));

  it("n'a aucune couleur écrite en dur", () => {
    for (const f of tous) expect(readFileSync(f, "utf8"), f).not.toMatch(COULEUR);
  });

  it("n'a aucune police à part", () => {
    for (const f of tous) expect(readFileSync(f, "utf8"), f).not.toMatch(/font-family/);
  });

  it("repère bien une couleur écrite en dur", () => {
    for (const c of ["color: #e03e2a", "bg-[#fff]", "shadow-[0_1px_2px_rgba(0,0,0,.1)]", "hsl(0 0% 0%)", "oklch(0.5 0.1 20)"]) expect(c).toMatch(COULEUR);
    for (const c of ["bg-side text-muted-ink", "var(--accent)", "trait rounded-2xl"]) expect(c).not.toMatch(COULEUR);
  });
});
