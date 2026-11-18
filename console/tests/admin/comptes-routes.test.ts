import type { DatabaseSync } from "node:sqlite";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DELETE as deconnecter } from "@/app/api/admin/comptes/[id]/sessions/route";
import { DELETE as reactiver, POST as suspendre } from "@/app/api/admin/comptes/[id]/suspension/route";
import { lireJournal } from "@/lib/admin/journal";
import { TA } from "@/lib/admin/textes";
import { acces, baseEssai, compte, membre } from "./aides";

// Les routes des comptes, appelées comme Next.js les appelle : la session vient de l'en-tête x-essai-qui, la base est celle de
// l'essai, l'adaptateur de Better Auth est simulé. Le journal note le motif d'une suspension (coupé), rien d'autre.

const etat = vi.hoisted(() => ({ db: undefined as unknown as DatabaseSync, appels: [] as unknown[][] }));
vi.mock("@/lib/base", async (original) => ({ ...(await original<typeof import("@/lib/base")>()), base: () => etat.db }));
vi.mock("@/lib/auth", async (original) => ({
  ...(await original<typeof import("@/lib/auth")>()),
  sessionDe: async (r: Request) => {
    const qui = r.headers.get("x-essai-qui");
    return qui ? { user: { id: qui, email: `${qui}@megga.test`, name: qui } } : null;
  },
}));
vi.mock("@/lib/admin/comptes", async (original) => ({
  ...(await original<typeof import("@/lib/admin/comptes")>()),
  adaptateurComptes: async () => ({
    updateUser: async (...a: unknown[]) => etat.appels.push(["updateUser", ...a]),
    deleteUserSessions: async (...a: unknown[]) => etat.appels.push(["deleteUserSessions", ...a]),
  }),
}));

type Route<P> = (r: Request, ctx: { params: Promise<P> }) => Promise<Response>;

function appeler<P>(route: Route<P>, methode: string, params: P, qui: string, corps?: unknown) {
  const requete = new Request("http://localhost/api/admin/comptes/essai", {
    method: methode,
    headers: { origin: "http://localhost", "x-essai-qui": qui },
    body: corps === undefined ? undefined : JSON.stringify(corps),
  });
  return route(requete, { params: Promise.resolve(params) });
}

const journal = () => lireJournal(etat.db, acces({ superadmin: true }), { page: 1 }).lignes.map((l) => [l.qui, l.action, l.cible, l.resultat, l.detail]);

beforeEach(async () => {
  etat.db = await baseEssai();
  etat.appels = [];
  compte(etat.db, { id: "c", courriel: "garage@exemple.test" });
  membre(etat.db, { utilisateur: "exploitant", role: "exploitation" });
  membre(etat.db, { utilisateur: "lecteur", role: "lecture" });
  membre(etat.db, { utilisateur: "chef", role: "superadmin" });
});

describe("suspendre un compte", () => {
  it("un membre Exploitation suspend un compte ordinaire : 200, l'adaptateur appelé, le motif au journal", async () => {
    const r = await appeler(suspendre, "POST", { id: "c" }, "exploitant", { motif: "Abus répétés", autre: "rien" });
    expect([r.status, await r.json()]).toEqual([200, { ok: true }]);
    expect(etat.appels).toEqual([["updateUser", "c", { banned: true, banReason: "Abus répétés", banExpires: null }], ["deleteUserSessions", "c"]]);
    expect(journal()).toEqual([["exploitant", "comptes.suspendu", "compte:c", "ok", { motif: "Abus répétés" }]]);
  });

  it("le compte d'un membre, par un membre qui n'est pas superadmin : 403, rien n'est écrit, la tentative notée", async () => {
    const r = await appeler(suspendre, "POST", { id: "lecteur" }, "exploitant", { motif: "Abus" });
    expect([r.status, await r.json()]).toEqual([403, { erreur: TA.suspensionInterdite }]);
    for (const [route, methode] of [[reactiver, "DELETE"], [deconnecter, "DELETE"]] as const) {
      expect((await appeler(route, methode, { id: "lecteur" }, "exploitant")).status).toBe(403);
      expect((await appeler(route, methode, { id: "chef" }, "exploitant")).status).toBe(403);
    }
    expect((await appeler(suspendre, "POST", { id: "chef" }, "chef", { motif: "Abus" })).status).toBe(403);
    expect(etat.appels).toEqual([]);
    expect(journal().at(-1)).toEqual(["exploitant", "comptes.suspendu", "compte:lecteur", "refuse 403", { motif: "Abus" }]);
  });

  it("un motif trop long : 400 ; le journal n'en garde qu'un texte court", async () => {
    const r = await appeler(suspendre, "POST", { id: "c" }, "exploitant", { motif: "x".repeat(5000) });
    expect([r.status, await r.json()]).toEqual([400, { erreur: TA.motifManquant }]);
    const [ligne] = journal();
    expect(ligne[3]).toBe("refuse 400");
    expect((ligne[4] as { motif: string }).motif.length).toBeLessThanOrEqual(200);
  });

  it("sans comptes.gerer (Lecture) : 403 ; un compte inconnu : 404", async () => {
    expect((await appeler(suspendre, "POST", { id: "c" }, "lecteur", { motif: "Abus" })).status).toBe(403);
    const r = await appeler(suspendre, "POST", { id: "personne" }, "exploitant", { motif: "Abus" });
    expect([r.status, await r.json()]).toEqual([404, { erreur: TA.compteInconnu }]);
    expect(etat.appels).toEqual([]);
  });
});

describe("réactiver et déconnecter partout", () => {
  it("DELETE suspension réactive ; rien du corps au journal", async () => {
    const r = await appeler(reactiver, "DELETE", { id: "c" }, "exploitant", { motif: "à ne pas noter" });
    expect([r.status, await r.json()]).toEqual([200, { ok: true }]);
    expect(etat.appels).toEqual([["updateUser", "c", { banned: false, banReason: null, banExpires: null }]]);
    expect(journal()).toEqual([["exploitant", "comptes.reactive", "compte:c", "ok", null]]);
  });

  it("DELETE sessions appelle deleteUserSessions ; rien du corps au journal", async () => {
    const r = await appeler(deconnecter, "DELETE", { id: "c" }, "exploitant", { secret: "à ne pas noter" });
    expect([r.status, await r.json()]).toEqual([200, { ok: true }]);
    expect(etat.appels).toEqual([["deleteUserSessions", "c"]]);
    expect(journal()).toEqual([["exploitant", "comptes.deconnecte", "compte:c", "ok", null]]);
  });

  it("le compte d'un membre, par un superadmin : permis", async () => {
    expect((await appeler(deconnecter, "DELETE", { id: "lecteur" }, "chef")).status).toBe(200);
    expect(etat.appels).toEqual([["deleteUserSessions", "lecteur"]]);
  });
});
