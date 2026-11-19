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

  it("rend l'initiale pour une image qui n'est pas une photo de la console", () => {
    for (const image of ["https://exemple.test/x.png", "data:image/png;base64,iVBORw0KGgo=", "/api/compte/photo/u1?v=abc", "//exemple.test/p.png",
      "/api/compte/photo/u1?v=abc123def456&x=1", "javascript:alert(1)"]) {
      const h = rendu({ nom: "Alix", image, taille: 36 });
      expect(h, image).not.toContain("<img");
      expect(h, image).toContain(">A<");
    }
  });

  it("rend l'aperçu local (blob:) d'une photo pas encore envoyée, et rien d'autre par cette voie", () => {
    const apercu = "blob:http://localhost:3000/0e5273fa-e86d-45e2-bcc2-8cd356c1256b";
    expect(renderToStaticMarkup(createElement(Avatar, { nom: "Alix", apercu, taille: 96 }))).toContain(`src="${apercu}"`);
    expect(renderToStaticMarkup(createElement(Avatar, { nom: "Alix", apercu: "https://exemple.test/x.png", taille: 96 }))).not.toContain("<img");
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
