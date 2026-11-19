import { afterEach, describe, expect, it, vi } from "vitest";
import { assurerInscriptions } from "@/lib/serveur-agents";

afterEach(() => vi.unstubAllGlobals());

describe("la réinscription des agents d'un compte", () => {
  it("inscrit chaque agent une fois avec son compte, et retente après un échec", async () => {
    const appels: { url: string; corps: Record<string, string> }[] = [];
    let panne = true;
    vi.stubGlobal("fetch", async (url: string, init: RequestInit) => {
      appels.push({ url, corps: JSON.parse(String(init.body)) });
      if (url.includes("ag_lea") && panne) return new Response("", { status: 503 });
      return new Response("{}", { status: 200 });
    });
    vi.spyOn(console, "error").mockImplementation(() => {});
    const agents = [
      { id: "ag_alix", prenom: "Alix", metier: "immobilier" },
      { id: "ag_lea", prenom: "Léa", metier: "fiduciaire" },
    ];
    await assurerInscriptions(agents, "Agence", "compte-1");
    expect(appels.map((a) => a.corps)).toEqual([
      { prenom: "Alix", metier: "immobilier", entreprise: "Agence", compte: "compte-1" },
      { prenom: "Léa", metier: "fiduciaire", entreprise: "Agence", compte: "compte-1" },
    ]);
    panne = false;
    await assurerInscriptions(agents, "Agence", "compte-1");
    expect(appels.slice(2).map((a) => a.url)).toEqual([expect.stringContaining("ag_lea")]); // Alix une seule fois, Léa retentée
    await assurerInscriptions(agents, "Agence", "compte-1");
    expect(appels).toHaveLength(3);
  });
});
