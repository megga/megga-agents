import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Avatar, initiale } from "@/components/console/avatar";

// L'avatar d'un compte : sa photo quand il en a une, sinon l'initiale de son nom.

const rendu = (p: { nom: string; image?: string | null; taille: number }) => renderToStaticMarkup(createElement(Avatar, p));

describe("l'avatar", () => {
  it("rend la photo quand elle existe, sans texte de remplacement (le nom est à côté)", () => {
    const h = rendu({ nom: "Alix", image: "/api/compte/photo/u1?v=abc123def456", taille: 36 });
    expect(h).toMatch(/<img[^>]*src="\/api\/compte\/photo\/u1\?v=abc123def456"/);
    expect(h).toMatch(/<img[^>]*alt=""/);
    expect(h).toMatch(/width="36"/);
    expect(h).not.toContain(">A<");
  });

  it("rend l'initiale sinon", () => {
    for (const image of [undefined, null, ""]) {
      const h = rendu({ nom: " alix", image, taille: 30 });
      expect(h).not.toContain("<img");
      expect(h).toContain(">A<");
    }
  });

  it("l'initiale d'un nom vide est M, celle d'un nom qui commence par un emoji est l'emoji entier", () => {
    expect(initiale("")).toBe("M");
    expect(initiale("  ")).toBe("M");
    expect(initiale("élodie")).toBe("É");
    expect(initiale("🙂 Joie")).toBe("🙂");
  });
});
