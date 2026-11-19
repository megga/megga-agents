import { afterEach, describe, expect, it, vi } from "vitest";
import { T } from "@/lib/textes";

// En ligne, AGENTS_URL n'est pas posée : l'équipe d'agents n'existe pas encore. La racine mène à /admin, les routes des
// agents disent qu'elles ne sont pas branchées (sans toucher à la base), et l'admin ne propose pas de retour vers elles.

vi.mock("@/lib/auth", async (original) => ({
  ...(await original<typeof import("@/lib/auth")>()),
  session: async () => ({ user: { id: "u", email: "u@megga.test", name: "U" } }),
  sessionDe: async () => ({ user: { id: "u", email: "u@megga.test", name: "U" } }),
}));
vi.mock("@/lib/base", () => {
  const interdit = () => {
    throw new Error("sans serveur d'agents, la base n'est pas touchée");
  };
  return { donnees: interdit, pret: interdit, preparer: interdit, cheminBase: interdit };
});
vi.mock("@/components/console/console", () => ({ Console: () => null }));
vi.mock("next/navigation", () => ({
  redirect: (url: string) => {
    throw new Error(`redirect:${url}`);
  },
}));
vi.mock("next/server", async (original) => ({ ...(await original<typeof import("next/server")>()), connection: async () => {} }));

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("sans serveur d'agents (AGENTS_URL vide)", () => {
  it("serveurAgents rend null ; posée, son adresse sans barre finale", async () => {
    const { serveurAgents } = await import("@/lib/serveur-agents");
    vi.stubEnv("AGENTS_URL", "");
    expect(serveurAgents()).toBeNull();
    vi.stubEnv("AGENTS_URL", "http://127.0.0.1:8100//");
    expect(serveurAgents()).toBe("http://127.0.0.1:8100");
  });

  it("la racine mène à /admin", async () => {
    vi.stubEnv("AGENTS_URL", "");
    const { default: Accueil } = await import("@/app/page");
    await expect(Accueil()).rejects.toThrow("redirect:/admin");
  });

  it("/api/agents répond 503, la phrase de T, sans toucher à la base", async () => {
    vi.stubEnv("AGENTS_URL", "");
    const agents = await import("@/app/api/agents/route");
    for (const r of [await agents.GET(new Request("http://x/api/agents")), await agents.POST(new Request("http://x/api/agents", { method: "POST", body: "{}" }))]) {
      expect(r.status).toBe(503);
      expect(await r.json()).toEqual({ erreur: T.agentsNonBranches });
    }
    const un = await import("@/app/api/agents/[id]/route");
    const r = await un.PATCH(new Request("http://x/api/agents/a", { method: "PATCH", body: "{}" }), { params: Promise.resolve({ id: "a" }) });
    expect(r.status).toBe(503);
  });

  it("/api/copilotkit répond 503, la phrase de T", async () => {
    vi.stubEnv("AGENTS_URL", "");
    const { POST } = await import("@/app/api/copilotkit/[[...chemin]]/route");
    const r = await POST(new Request("http://x/api/copilotkit", { method: "POST", body: "{}" }));
    expect(r.status).toBe(503);
    expect(await r.json()).toEqual({ erreur: T.agentsNonBranches });
  });
});

describe("avec un serveur d'agents", () => {
  it("la racine reste la console des agents", async () => {
    vi.stubEnv("AGENTS_URL", "http://127.0.0.1:8100");
    const { default: Accueil } = await import("@/app/page");
    // Elle passe la redirection et va chercher la base (ici interdite) : elle ne mène pas à /admin.
    await expect(Accueil()).rejects.toThrow("sans serveur d'agents, la base n'est pas touchée");
  });
});
