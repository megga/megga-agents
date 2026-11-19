import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";

// /api/sante : ce que le Worker attend avant de transmettre. Sans session, sans base : Neon n'a pas à se réveiller pour
// dire que le conteneur est prêt. Une base touchée ferait échouer l'essai.
vi.mock("@/lib/base", () => {
  const interdit = () => {
    throw new Error("/api/sante ne touche pas à la base");
  };
  return { donnees: interdit, pret: interdit, preparer: interdit, cheminBase: interdit };
});
vi.mock("@/lib/donnees/base", () => ({
  ouvrirBase: () => {
    throw new Error("/api/sante ne touche pas à la base");
  },
}));
vi.mock("next/server", async (original) => ({ ...(await original<typeof import("next/server")>()), connection: async () => {} }));

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("GET /api/sante", () => {
  it("dit que la console tourne, avec la révision de l'image, sans base ouverte", async () => {
    vi.stubEnv("CONSOLE_REVISION", "abc");
    const { GET } = await import("@/app/api/sante/route");
    const r = await GET();
    expect(r.status).toBe(200);
    expect(await r.json()).toEqual({ ok: true, revision: "abc" });
    expect(r.headers.get("cache-control")).toBe("no-store");
  });

  it("rend une révision nulle quand l'image n'en a pas", async () => {
    vi.stubEnv("CONSOLE_REVISION", undefined);
    const { GET } = await import("@/app/api/sante/route");
    expect(await (await GET()).json()).toEqual({ ok: true, revision: null });
  });

  it("n'importe ni la base ni l'authentification", () => {
    const code = readFileSync(join(__dirname, "../src/app/api/sante/route.ts"), "utf8");
    expect(code).not.toMatch(/@\/lib\/(base|auth|donnees)/);
  });
});
