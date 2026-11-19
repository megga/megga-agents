import { beforeEach, describe, expect, it, vi } from "vitest";
import { DELETE as retirerCle } from "@/app/api/admin/clients/[id]/cles/[cle]/route";
import { POST as creerCle } from "@/app/api/admin/clients/[id]/cles/route";
import { DELETE as retirerJetons, POST as creerJeton } from "@/app/api/admin/clients/[id]/jetons/route";
import { POST as reprise } from "@/app/api/admin/clients/[id]/reprise/route";
import { RefusChamps } from "@/lib/admin/atelier";
import { lireJournal } from "@/lib/admin/journal";
import { TA } from "@/lib/admin/textes";
import type { Base } from "@/lib/donnees/base";
import { acces, baseEssai, membre } from "./aides";

// La main, les jetons et les clés, appelés comme Next.js les appelle (session par l'en-tête x-essai-qui, base de l'essai,
// atelier simulé). Un jeton ou une clé n'est que dans la réponse du geste qui le crée : ni au journal, ni dans une erreur.

const etat = vi.hoisted(() => ({ db: undefined as unknown as Base }));
vi.mock("@/lib/base", async (original) => ({
  ...(await original<typeof import("@/lib/base")>()),
  pret: async () => etat.db,
  donnees: () => etat.db,
}));
vi.mock("@/lib/auth", async (original) => ({
  ...(await original<typeof import("@/lib/auth")>()),
  sessionDe: async (r: Request) => {
    const qui = r.headers.get("x-essai-qui");
    return qui ? { user: { id: qui, email: `${qui}@megga.test`, name: qui } } : null;
  },
}));

const simule = vi.hoisted(() => ({ reprise: vi.fn(), creerJeton: vi.fn(), retirerJetons: vi.fn(), creerCle: vi.fn(), retirerCle: vi.fn() }));
vi.mock("@/lib/admin/atelier", async (original) => {
  const vrai = await original<typeof import("@/lib/admin/atelier")>();
  return { ...vrai, atelier: { ...vrai.atelier, ...simule } };
});

const JETON = "jeton-client-123";
const CLE = "cle-logiciel-456";
const HORS_CLOUDFLARE = "hors Cloudflare, les clés se créent chez le client : python -m noyau.cles creer <logiciel> (docs/api.md)";

type Route<P> = (r: Request, ctx: { params: Promise<P> }) => Promise<Response>;

function appeler<P>(route: Route<P>, methode: string, params: P, qui: string, corps?: unknown) {
  const requete = new Request("http://localhost/api/admin/essai", {
    method: methode,
    headers: { origin: "http://localhost", "x-essai-qui": qui },
    body: corps === undefined ? undefined : JSON.stringify(corps),
  });
  return route(requete, { params: Promise.resolve(params) });
}

const GARAGE = { id: "garage-essai" };
const journal = async () => (await lireJournal(etat.db, acces({ superadmin: true }), { page: 1 })).lignes;
const tableJournal = async () => JSON.stringify((await etat.db.tous("SELECT * FROM admin_journal")));

beforeEach(async () => {
  for (const f of Object.values(simule)) f.mockReset();
  simule.reprise.mockImplementation(async (client: string, corps: { gere_par_megga: boolean }) => ({ client, gere_par_megga: corps.gere_par_megga }));
  simule.creerJeton.mockResolvedValue({ client: "garage-essai", jeton: JETON });
  simule.retirerJetons.mockResolvedValue({ client: "garage-essai", retires: 2 });
  simule.creerCle.mockResolvedValue({ client: "garage-essai", id: "d15a76f57ee4", logiciel: "caisse", par_minute: 60, cle: CLE });
  simule.retirerCle.mockResolvedValue({ client: "garage-essai", id: "d15a76f57ee4", retiree: true });
  etat.db = await baseEssai();
  await membre(etat.db, { utilisateur: "exploitant", role: "exploitation" });
  await membre(etat.db, { utilisateur: "invite", role: "administration", externe: true, perimetre: ["garage-essai"] });
});

describe("les jetons d'un client", () => {
  it("un jeton créé est rendu une fois, 201, et le journal ne le contient pas", async () => {
    const r = await appeler(creerJeton, "POST", GARAGE, "exploitant");
    expect([r.status, await r.json()]).toEqual([201, { client: "garage-essai", jeton: JETON }]);
    expect(simule.creerJeton.mock.calls).toEqual([["garage-essai"]]);
    expect(JSON.stringify((await lireJournal(etat.db, acces({ superadmin: true }), { page: 1 })))).not.toContain(JETON);
    expect(await tableJournal()).not.toContain(JETON);
    expect((await journal()).map((l) => [l.qui, l.action, l.cible, l.resultat, l.detail])).toEqual([
      ["exploitant", "acces.jeton_cree", "client:garage-essai", "ok", null],
    ]);
  });

  it("retirer les jetons rend le nombre retiré, noté sans détail", async () => {
    const r = await appeler(retirerJetons, "DELETE", GARAGE, "exploitant");
    expect([r.status, await r.json()]).toEqual([200, { client: "garage-essai", retires: 2 }]);
    expect((await journal()).map((l) => [l.action, l.resultat, l.detail])).toEqual([["acces.jetons_retires", "ok", null]]);
  });
});

describe("les clés des logiciels", () => {
  it("une clé créée est rendue une fois ; seuls le logiciel et le débit partent à l'atelier et au journal, jamais la clé", async () => {
    const r = await appeler(creerCle, "POST", GARAGE, "exploitant", { logiciel: "caisse", par_minute: 60, cle: "une-autre", id: "x" });
    expect([r.status, await r.json()]).toEqual([201, { client: "garage-essai", id: "d15a76f57ee4", logiciel: "caisse", par_minute: 60, cle: CLE }]);
    expect(simule.creerCle.mock.calls).toEqual([["garage-essai", { logiciel: "caisse", par_minute: 60 }]]);
    expect(JSON.stringify((await lireJournal(etat.db, acces({ superadmin: true }), { page: 1 })))).not.toContain(CLE);
    expect(await tableJournal()).not.toContain(CLE);
    expect((await journal()).map((l) => [l.action, l.cible, l.resultat, l.detail])).toEqual([
      ["acces.cle_creee", "client:garage-essai", "ok", { logiciel: "caisse", par_minute: 60 }],
    ]);
  });

  it("le refus 409 de l'atelier (hors Cloudflare, ou jamais mis en service) rend sa phrase", async () => {
    simule.creerCle.mockRejectedValue(new RefusChamps(409, HORS_CLOUDFLARE));
    const r = await appeler(creerCle, "POST", GARAGE, "exploitant", { logiciel: "caisse" });
    expect([r.status, await r.json()]).toEqual([409, { erreur: HORS_CLOUDFLARE }]);
    expect((await journal()).map((l) => [l.resultat, l.detail])).toEqual([["refuse 409", { logiciel: "caisse", par_minute: null }]]);
  });

  it("retirer une clé par son identifiant ; un identifiant mal formé : 400, rien ne part", async () => {
    const r = await appeler(retirerCle, "DELETE", { id: "garage-essai", cle: "d15a76f57ee4" }, "exploitant");
    expect([r.status, await r.json()]).toEqual([200, { client: "garage-essai", id: "d15a76f57ee4", retiree: true }]);
    expect(simule.retirerCle.mock.calls).toEqual([["garage-essai", "d15a76f57ee4"]]);
    for (const cle of ["xyz", "D15A76F57EE4", "d15a76f57ee4a", "..%2Fx"]) {
      const refus = await appeler(retirerCle, "DELETE", { id: "garage-essai", cle }, "exploitant");
      expect([refus.status, await refus.json()], cle).toEqual([400, { erreur: TA.cleInvalide }]);
    }
    expect(simule.retirerCle).toHaveBeenCalledTimes(1);
    expect((await journal()).map((l) => [l.action, l.resultat, l.detail]).reverse()).toEqual([
      ["acces.cle_retiree", "ok", { id: "d15a76f57ee4" }],
      ...["xyz", "D15A76F57EE4", "d15a76f57ee4a", "..%2Fx"].map(() => ["acces.cle_retiree", "refuse 400", { id: null }]),
    ]);
  });
});

describe("reprendre ou rendre la main", () => {
  it("le choix part tel quel à l'atelier et se note", async () => {
    const r = await appeler(reprise, "POST", GARAGE, "exploitant", { gere_par_megga: true });
    expect([r.status, await r.json()]).toEqual([200, { client: "garage-essai", gere_par_megga: true }]);
    await appeler(reprise, "POST", GARAGE, "exploitant", { gere_par_megga: false, autre: 1 });
    expect(simule.reprise.mock.calls).toEqual([["garage-essai", { gere_par_megga: true }], ["garage-essai", { gere_par_megga: false }]]);
    expect((await journal()).map((l) => [l.action, l.cible, l.detail])).toEqual([
      ["clients.reprise", "client:garage-essai", { gere_par_megga: false }],
      ["clients.reprise", "client:garage-essai", { gere_par_megga: true }],
    ]);
  });

  it("autre chose qu'un booléen : 400, rien ne part (l'atelier reprendrait la main par défaut)", async () => {
    for (const corps of [{}, { gere_par_megga: "false" }, { gere_par_megga: null }, null]) {
      const r = await appeler(reprise, "POST", GARAGE, "exploitant", corps);
      expect([r.status, await r.json()], JSON.stringify(corps)).toEqual([400, { erreur: TA.repriseInvalide }]);
    }
    expect(simule.reprise).not.toHaveBeenCalled();
  });
});

describe("un externe", () => {
  it("ni la main, ni un jeton, ni une clé, même d'un corps écrit à la main : 403, l'atelier jamais appelé", async () => {
    expect((await appeler(reprise, "POST", GARAGE, "invite", { gere_par_megga: false })).status).toBe(403);
    expect((await appeler(creerJeton, "POST", GARAGE, "invite")).status).toBe(403);
    expect((await appeler(retirerJetons, "DELETE", GARAGE, "invite")).status).toBe(403);
    expect((await appeler(creerCle, "POST", GARAGE, "invite", { logiciel: "caisse" })).status).toBe(403);
    expect((await appeler(retirerCle, "DELETE", { id: "garage-essai", cle: "d15a76f57ee4" }, "invite")).status).toBe(403);
    for (const f of Object.values(simule)) expect(f).not.toHaveBeenCalled();
  });
});
