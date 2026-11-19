import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { DatabaseSync } from "node:sqlite";
import { betterAuth } from "better-auth";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TA } from "@/lib/admin/textes";
import { agentDuTour, compterSansBloquer, compterTour, jourZurich, joursZurich, messagesDepuis, messagesParJour, noterConnexion } from "@/lib/admin/usage";
import { creer } from "@/lib/agents";
import { optionsAuth } from "@/lib/auth";
import type { Base } from "@/lib/donnees/base";
import { baseVide, moteurParDefaut } from "../moteurs";
import { baseDe, colonnes, compte, dbEssai, T0 } from "./aides";

// Le compteur de messages (usage_agent) et la dernière connexion (compte_connexion). Le compteur s'écrit après la réponse de
// l'agent (after de Next.js), sans texte, et une panne du compteur ne fait jamais échouer ni attendre une conversation.

const etat = vi.hoisted(() => ({
  db: undefined as unknown as DatabaseSync,
  b: undefined as unknown as Base,
  qui: null as string | null,
  apres: [] as (() => unknown)[],
  statut: 200,
}));
vi.mock("next/server", async (original) => ({
  ...(await original<typeof import("next/server")>()),
  after: (f: () => unknown) => {
    etat.apres.push(f);
  },
}));
vi.mock("@/lib/base", async (original) => ({
  ...(await original<typeof import("@/lib/base")>()),
  base: () => etat.db,
  pret: async () => etat.b,
}));
vi.mock("@/lib/auth", async (original) => ({
  ...(await original<typeof import("@/lib/auth")>()),
  sessionDe: async () => (etat.qui ? { user: { id: etat.qui, email: `${etat.qui}@megga.test`, name: etat.qui } } : null),
}));
// CopilotKit répond tout de suite, comme le flux d'un agent qui commence (ou le refuse, au statut de etat.statut).
vi.mock("@copilotkit/runtime/v2", () => ({
  CopilotRuntime: class {},
  createCopilotRuntimeHandler: () => async () => new Response("flux de l'agent", { status: etat.statut }),
}));

let db: DatabaseSync;
let b: Base;
beforeEach(async () => {
  db = await dbEssai();
  b = baseDe(db);
  etat.db = db;
  etat.b = b;
  etat.qui = null;
  etat.apres = [];
  etat.statut = 200;
});
afterEach(() => vi.restoreAllMocks());

const lignes = () => b.tous("SELECT agent, jour, messages FROM usage_agent ORDER BY agent, jour");

describe("le tour d'un agent dans une requête de CopilotKit", () => {
  it("est un POST sur /api/copilotkit/agent/<id>/run", () => {
    expect(agentDuTour("POST", "/api/copilotkit/agent/ag_123/run")).toBe("ag_123");
  });

  it("n'est ni un GET, ni une autre route de CopilotKit, ni une adresse hors de /api/copilotkit", () => {
    expect(agentDuTour("GET", "/api/copilotkit/agent/ag_123/run")).toBeNull();
    expect(agentDuTour("POST", "/api/copilotkit/info")).toBeNull();
    expect(agentDuTour("POST", "/api/copilotkit/agent/ag_1/connect")).toBeNull();
    expect(agentDuTour("POST", "/api/copilotkit/agent/ag_1/stop/fil")).toBeNull();
    expect(agentDuTour("POST", "/api/copilotkitx/agent/ag_1/run")).toBeNull();
    expect(agentDuTour("POST", "/autre/agent/ag_1/run")).toBeNull();
    expect(agentDuTour("POST", "/api/copilotkit/agent//run")).toBeNull();
  });

  it("décode un identifiant encodé ; un encodage illisible n'est pas un tour", () => {
    expect(agentDuTour("POST", "/api/copilotkit/agent/ag%5F1/run")).toBe("ag_1");
    expect(agentDuTour("POST", "/api/copilotkit/agent/%E0%A4%A/run")).toBeNull();
  });

  it("suit la règle de CopilotKit : les trois derniers segments, une barre finale permise", () => {
    expect(agentDuTour("POST", "/api/copilotkit/agent/ag_1/run/")).toBe("ag_1");
    expect(agentDuTour("POST", "/api/copilotkit/x/agent/ag_1/run")).toBe("ag_1");
  });
});

describe("le compteur de messages", () => {
  it("compte par agent et par jour de Zurich : deux tours le même jour, puis un le lendemain", async () => {
    await compterTour(b, "ag_1", T0);
    await compterTour(b, "ag_1", new Date("2026-11-18T22:59:00Z")); // 23 h 59 à Zurich
    await compterTour(b, "ag_1", new Date("2026-11-18T23:01:00Z")); // 0 h 01 le 19 à Zurich
    await compterTour(b, "ag_2", T0);
    expect(await lignes()).toEqual([
      { agent: "ag_1", jour: "2026-11-18", messages: 2 },
      { agent: "ag_1", jour: "2026-11-19", messages: 1 },
      { agent: "ag_2", jour: "2026-11-18", messages: 1 },
    ]);
  });

  it("ne garde aucun texte : seulement l'agent, le jour et un nombre", async () => {
    expect(await colonnes(b, "usage_agent")).toEqual(["agent", "jour", "messages"]);
  });

  it("sans bloquer : une base sans la table, ou une base qui ne s'ouvre pas, ne lève rien et part à console.error", async () => {
    const erreur = vi.spyOn(console, "error").mockImplementation(() => {});
    const sansTable = await baseVide(moteurParDefaut());
    await expect(compterSansBloquer(() => sansTable, "ag_1")).resolves.toBeUndefined();
    await expect(
      compterSansBloquer(() => {
        throw new Error("base fermée");
      }, "ag_1"),
    ).resolves.toBeUndefined();
    expect(erreur).toHaveBeenCalledTimes(2);
  });

  it("sans bloquer, sur une bonne base : compte", async () => {
    await compterSansBloquer(() => b, "ag_1");
    expect(await lignes()).toEqual([{ agent: "ag_1", jour: jourZurich(new Date()), messages: 1 }]);
  });

  it("messagesDepuis : la somme de chaque agent demandé depuis un jour inclus, zéro sans message", async () => {
    await compterTour(b, "ag_1", new Date("2026-10-01T10:00:00Z"));
    await compterTour(b, "ag_1", new Date("2026-11-01T10:00:00Z"));
    await compterTour(b, "ag_1", T0);
    await compterTour(b, "ag_2", T0);
    await compterTour(b, "ag_3", T0);
    expect(await messagesDepuis(b, ["ag_1", "ag_2", "ag_4"], "2026-11-01")).toEqual({ ag_1: 2, ag_2: 1, ag_4: 0 });
    expect(await messagesDepuis(b, [], "2026-11-01")).toEqual({});
  });

  it("messagesParJour : les derniers jours de Zurich, zéros compris, le plus ancien d'abord, tous agents ensemble", async () => {
    await compterTour(b, "ag_1", new Date("2026-11-11T22:59:00Z")); // 23 h 59 le 11 à Zurich : hors des 7 jours
    await compterTour(b, "ag_1", new Date("2026-11-13T10:00:00Z"));
    await compterTour(b, "ag_1", T0);
    await compterTour(b, "ag_2", T0);
    expect(await messagesParJour(b, 7, T0)).toEqual([
      { jour: "2026-11-12", messages: 0 },
      { jour: "2026-11-13", messages: 1 },
      { jour: "2026-11-14", messages: 0 },
      { jour: "2026-11-15", messages: 0 },
      { jour: "2026-11-16", messages: 0 },
      { jour: "2026-11-17", messages: 0 },
      { jour: "2026-11-18", messages: 2 },
    ]);
    expect(await messagesParJour(b, 1, T0)).toEqual([{ jour: "2026-11-18", messages: 2 }]);
    expect(await messagesParJour(b, 30, T0)).toHaveLength(30);
    expect((await messagesParJour(b, 30, T0))[0].jour).toBe("2026-10-20");
  });
});

describe("les jours de Zurich", () => {
  it("un tour à 0 h 30 de Zurich compte dans le jour affiché, en hiver comme en été", async () => {
    await compterTour(b, "hiver", new Date("2026-11-17T23:30:00Z")); // 0 h 30 le 18 novembre, heure d'hiver (+1)
    await compterTour(b, "ete", new Date("2026-07-14T22:30:00Z")); // 0 h 30 le 15 juillet, heure d'été (+2)
    expect(await lignes()).toEqual([
      { agent: "ete", jour: "2026-07-15", messages: 1 },
      { agent: "hiver", jour: "2026-11-18", messages: 1 },
    ]);
    expect(await messagesParJour(b, 1, T0)).toEqual([{ jour: "2026-11-18", messages: 1 }]);
    expect(await messagesParJour(b, 1, new Date("2026-07-15T08:00:00Z"))).toEqual([{ jour: "2026-07-15", messages: 1 }]);
    expect(TA.jour(jourZurich(new Date("2026-11-17T23:30:00Z")))).toBe("18.11.2026");
  });

  it("les périodes : aujourd'hui ; aujourd'hui et les 6 jours d'avant ; aujourd'hui et les 29 jours d'avant", () => {
    expect(joursZurich(1, T0)).toEqual(["2026-11-18"]);
    expect(joursZurich(7, T0)).toEqual(["2026-11-12", "2026-11-13", "2026-11-14", "2026-11-15", "2026-11-16", "2026-11-17", "2026-11-18"]);
    const trente = joursZurich(30, T0);
    expect([trente.length, trente[0], trente[29]]).toEqual([30, "2026-10-20", "2026-11-18"]);
    // Tard le soir en UTC, c'est déjà demain à Zurich ; un changement d'heure ne saute ni ne double un jour.
    expect(joursZurich(1, new Date("2026-11-18T23:30:00Z"))).toEqual(["2026-11-19"]);
    expect(joursZurich(3, new Date("2026-10-26T10:00:00Z"))).toEqual(["2026-10-24", "2026-10-25", "2026-10-26"]);
    expect(joursZurich(3, new Date("2026-03-30T10:00:00Z"))).toEqual(["2026-03-28", "2026-03-29", "2026-03-30"]);
  });

  it("les bornes : le premier instant du premier jour compte, celui d'avant non", async () => {
    const bornes: [1 | 7 | 30, string, string][] = [
      [1, "2026-11-17T23:00:00Z", "2026-11-17T22:59:59Z"], // le 18, heure d'hiver
      [7, "2026-11-11T23:00:00Z", "2026-11-11T22:59:59Z"], // le 12
      [30, "2026-10-19T22:00:00Z", "2026-10-19T21:59:59Z"], // le 20 octobre, encore en heure d'été
    ];
    for (const [jours, dedans, dehors] of bornes) {
      const d = await baseVide(moteurParDefaut());
      await d.executer("CREATE TABLE usage_agent (agent TEXT NOT NULL, jour TEXT NOT NULL, messages INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (agent, jour))");
      await compterTour(d, "dedans", new Date(dedans));
      await compterTour(d, "dehors", new Date(dehors));
      const total = (await messagesParJour(d, jours, T0)).reduce((n, j) => n + j.messages, 0);
      expect(total, `${jours} jours`).toBe(1);
    }
  });
});

describe("la dernière connexion", () => {
  it("noterConnexion garde la plus récente", async () => {
    await noterConnexion(b, "u1", T0);
    await noterConnexion(b, "u1", new Date("2026-11-18T12:00:00Z"));
    await noterConnexion(b, "u1", new Date("2026-11-01T12:00:00Z")); // une date plus ancienne n'efface pas la dernière
    await noterConnexion(b, "u2", T0);
    expect(await b.tous("SELECT * FROM compte_connexion ORDER BY utilisateur")).toEqual([
      { utilisateur: "u1", derniere: "2026-11-18T12:00:00.000Z" },
      { utilisateur: "u2", derniere: T0.toISOString() },
    ]);
  });

  it("est notée à chaque session créée par Better Auth (inscription, connexion)", async () => {
    const auth = betterAuth({ ...optionsAuth(b), secret: "secret-des-essais-de-la-console-assez-long" });
    const { user } = await auth.api.signUpEmail({ body: { name: "Garage", email: "garage@exemple.test", password: "motdepasse" } });
    const premiere = (await b.un<{ derniere: string }>("SELECT derniere FROM compte_connexion WHERE utilisateur = ?", user.id))!;
    expect(Date.parse(premiere.derniere)).toBeGreaterThan(Date.now() - 60_000);
    await auth.api.signInEmail({ body: { email: "garage@exemple.test", password: "motdepasse" } });
    const seconde = (await b.un<{ derniere: string }>("SELECT derniere FROM compte_connexion WHERE utilisateur = ?", user.id))!;
    expect(seconde.derniere >= premiere.derniere).toBe(true);
  });

  it("une panne de la dernière connexion ne refuse pas la connexion", async () => {
    const erreur = vi.spyOn(console, "error").mockImplementation(() => {});
    const auth = betterAuth({ ...optionsAuth(b), secret: "secret-des-essais-de-la-console-assez-long" });
    await b.executer("DROP TABLE compte_connexion");
    const r = await auth.api.signUpEmail({ body: { name: "Garage", email: "garage@exemple.test", password: "motdepasse" } });
    expect(r.token).toBeTruthy();
    expect(erreur).toHaveBeenCalled();
  });
});

describe("la route de CopilotKit", () => {
  const ROUTE = join(__dirname, "../../src/app/api/copilotkit/[[...chemin]]/route.ts");

  async function envoyer(chemin: string, methode = "POST") {
    const { POST, GET } = await import("@/app/api/copilotkit/[[...chemin]]/route");
    const requete = new Request(`http://localhost${chemin}`, { method: methode, body: methode === "GET" ? undefined : "{}" });
    return (methode === "GET" ? GET : POST)(requete);
  }

  it("compte un tour après la réponse, jamais avant : la réponse part, le compteur attend after", async () => {
    compte(db, { id: "u1", courriel: "u1@exemple.test" });
    const agent = await creer(b, "u1", { prenom: "Lou", metier: "garage" }, T0);
    etat.qui = "u1";
    const r = await envoyer(`/api/copilotkit/agent/${agent.id}/run`);
    expect([r.status, await r.text()]).toEqual([200, "flux de l'agent"]);
    expect(await lignes()).toEqual([]); // rien d'écrit tant que la réponse n'est pas finie
    expect(etat.apres).toHaveLength(1);
    await etat.apres[0]();
    expect(await lignes()).toEqual([{ agent: agent.id, jour: jourZurich(new Date()), messages: 1 }]);
  });

  it("ne compte ni une autre route, ni l'agent d'un autre compte", async () => {
    compte(db, { id: "u1", courriel: "u1@exemple.test" });
    compte(db, { id: "u2", courriel: "u2@exemple.test" });
    const sien = await creer(b, "u1", { prenom: "Lou", metier: "garage" }, T0);
    const autre = await creer(b, "u2", { prenom: "Max", metier: "sante" }, T0);
    etat.qui = "u1";
    await envoyer("/api/copilotkit/info", "GET");
    await envoyer(`/api/copilotkit/agent/${sien.id}/connect`);
    await envoyer(`/api/copilotkit/agent/${autre.id}/run`);
    expect(etat.apres).toEqual([]);
  });

  it("un tour refusé par CopilotKit ne compte rien", async () => {
    compte(db, { id: "u1", courriel: "u1@exemple.test" });
    const agent = await creer(b, "u1", { prenom: "Lou", metier: "garage" }, T0);
    etat.qui = "u1";
    for (const statut of [400, 404, 500]) {
      etat.statut = statut;
      expect((await envoyer(`/api/copilotkit/agent/${agent.id}/run`)).status).toBe(statut);
    }
    expect(etat.apres).toEqual([]);
  });

  it("une panne du compteur ne change pas la réponse de l'agent", async () => {
    const erreur = vi.spyOn(console, "error").mockImplementation(() => {});
    compte(db, { id: "u1", courriel: "u1@exemple.test" });
    const agent = await creer(b, "u1", { prenom: "Lou", metier: "garage" }, T0);
    etat.qui = "u1";
    const r = await envoyer(`/api/copilotkit/agent/${agent.id}/run`);
    await b.executer("DROP TABLE usage_agent");
    await expect(Promise.resolve(etat.apres[0]())).resolves.toBeUndefined();
    expect(r.status).toBe(200);
    expect(erreur).toHaveBeenCalled();
  });

  it("appelle after( et n'attend jamais le compteur", () => {
    const code = readFileSync(ROUTE, "utf8");
    expect(code).toMatch(/\bafter\(/);
    expect(code).not.toMatch(/await\s+compter/);
    expect(code).not.toMatch(/compterTour\(/);
  });
});
