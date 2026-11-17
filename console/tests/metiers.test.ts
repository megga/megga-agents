import { execFileSync } from "node:child_process";
import { describe, expect, it } from "vitest";
import { IDS_METIERS, METIERS } from "@/lib/metiers";

const LOT_10 = ["generaliste", "immobilier", "sante", "hotellerie", "juridique", "commerce", "fiduciaire", "garage"];

describe("les métiers", () => {
  it("sont exactement les huit du lot 10, dans son ordre", () => {
    expect(IDS_METIERS).toEqual(LOT_10);
  });

  it("portent les titres des gabarits du lot 10 quand sa branche est là", () => {
    let titres: Record<string, string> = {};
    try {
      for (const id of LOT_10) {
        const md = execFileSync("git", ["show", `origin/megga/lot-10-modeles:atelier/gabarits/${id}.md`], { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] });
        titres[id] = /^titre:\s*(.+)$/m.exec(md)![1].trim();
      }
    } catch {
      titres = {};
    }
    if (!Object.keys(titres).length) return; // branche absente (CI sans historique) : seul le premier test vaut
    for (const m of METIERS) expect(m.nom).toBe(titres[m.id]);
  });
});
