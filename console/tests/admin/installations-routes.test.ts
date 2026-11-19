import { beforeEach, describe, expect, it, vi } from "vitest";
import { POST as proposerImage } from "@/app/api/admin/clients/[id]/installation/image/route";
import { DELETE as revoquer, PUT as enregistrer } from "@/app/api/admin/clients/[id]/installation/route";
import { POST as creerClient } from "@/app/api/admin/clients/route";
import { RefusChamps } from "@/lib/admin/atelier";
import { lireJournal } from "@/lib/admin/journal";
import { TA } from "@/lib/admin/textes";
import type { Base } from "@/lib/donnees/base";
import { acces, baseEssai, membre } from "./aides";

// Le nouveau client et les gestes d'une installation hors Cloudflare, appelés comme Next.js les appelle (session par l'en-tête
// x-essai-qui, base de l'essai, atelier simulé). Le journal ne garde ni la configuration collée, ni la clé publique.

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

const simule = vi.hoisted(() => ({ creerClient: vi.fn(), enregistrerInstallation: vi.fn(), revoquerInstallation: vi.fn(), proposerImage: vi.fn() }));
vi.mock("@/lib/admin/atelier", async (original) => {
  const vrai = await original<typeof import("@/lib/admin/atelier")>();
  return { ...vrai, atelier: { ...vrai.atelier, ...simule } };
});

const CLE_PUBLIQUE = "MCowBQYDK2VwAyEAcleDePilotageDeEssaiQuiNeDoitPasAllerAuJournal=";
const IMAGE = `ghcr.io/megga/megga-agents@sha256:${"a1".repeat(32)}`;
const NOUVEAU = { gabarit: "generaliste", client: { id: "nouveau-essai", entreprise: "Nouveau des Essais", zone: "europe", numero_id: "100000000000099" },
  nom_agent: "Ana" };
const CONSIGNES = "Des consignes collées qui ne doivent jamais aller au journal";
const CONFIG = { id: "colle-essai", entreprise: "Collé des Essais", zone: "client", nom_agent: "Eva", consignes: CONSIGNES };

type Route<P> = (r: Request, ctx: { params: Promise<P> }) => Promise<Response>;

function appeler<P>(route: Route<P>, methode: string, params: P, qui: string, corps?: unknown) {
  const requete = new Request("http://localhost/api/admin/essai", {
    method: methode,
    headers: { origin: "http://localhost", "x-essai-qui": qui },
    body: corps === undefined ? undefined : JSON.stringify(corps),
  });
  return route(requete, { params: Promise.resolve(params) });
}

const CHALET = { id: "chalet-essai" };
const journal = async () => (await lireJournal(etat.db, acces({ superadmin: true }), { page: 1 })).lignes;
const tableJournal = async () => JSON.stringify((await etat.db.tous("SELECT * FROM admin_journal")));

beforeEach(async () => {
  for (const f of Object.values(simule)) f.mockReset();
  simule.creerClient.mockImplementation(async (c: { client?: { id: string }; config?: { id: string } }) =>
    ({ client: c.client?.id ?? c.config?.id, version: 1, etat: "brouillon" }));
  simule.enregistrerInstallation.mockResolvedValue({ client: "chalet-essai", cle: "263dfa8b264b31a1" });
  simule.revoquerInstallation.mockResolvedValue({ client: "chalet-essai", revoquee: true });
  simule.proposerImage.mockResolvedValue({ client: "chalet-essai", ordre: 3, version: "0.3.0", image: IMAGE });
  etat.db = await baseEssai();
  await membre(etat.db, { utilisateur: "chef", role: "superadmin" });
  await membre(etat.db, { utilisateur: "limite", role: "administration", perimetre: ["garage-essai", "chalet-essai"] });
  await membre(etat.db, { utilisateur: "exploitant", role: "exploitation" });
  await membre(etat.db, { utilisateur: "invite", role: "administration", externe: true, perimetre: ["chalet-essai"] });
});

describe("créer un client", () => {
  it("un membre limité à une liste, même avec clients.creer : 403, l'atelier jamais appelé", async () => {
    const r = await appeler(creerClient, "POST", {}, "limite", NOUVEAU);
    expect([r.status, await r.json()]).toEqual([403, { erreur: TA.creationPerimetre }]);
    expect(simule.creerClient).not.toHaveBeenCalled();
    expect((await journal()).map((l) => [l.qui, l.action, l.cible, l.resultat])).toEqual([["limite", "clients.creer", "client:nouveau-essai", "refuse 403"]]);
  });

  it("un superadmin, d'après un modèle par métier : 201, la ligne clients.creer de cible client:nouveau-essai", async () => {
    const r = await appeler(creerClient, "POST", {}, "chef", { ...NOUVEAU, autre: "x" });
    expect([r.status, await r.json()]).toEqual([201, { client: "nouveau-essai", version: 1, etat: "brouillon" }]);
    expect(simule.creerClient.mock.calls).toEqual([[NOUVEAU]]);
    expect((await journal()).map((l) => [l.action, l.cible, l.resultat, l.detail])).toEqual([
      ["clients.creer", "client:nouveau-essai", "ok", { id: "nouveau-essai", entreprise: "Nouveau des Essais", zone: "europe", gabarit: "generaliste" }],
    ]);
  });

  it("d'une configuration collée : elle part entière, le journal n'en garde que l'identité", async () => {
    const r = await appeler(creerClient, "POST", {}, "exploitant", { config: CONFIG });
    expect(r.status).toBe(201);
    expect(simule.creerClient.mock.calls).toEqual([[{ config: CONFIG }]]);
    expect((await journal()).map((l) => [l.cible, l.detail])).toEqual([["client:colle-essai", { id: "colle-essai", entreprise: "Collé des Essais", zone: "client", gabarit: null }]]);
    expect(await tableJournal()).not.toContain("consignes collées");
  });

  it("un refus de l'atelier rend ses messages champ par champ ; un corps qui n'est pas un objet : 400 avant lui", async () => {
    const champs = [{ champ: "nom_agent", message: "Donnez un prénom à votre agent." }];
    simule.creerClient.mockRejectedValueOnce(new RefusChamps(422, "configuration invalide", champs));
    const r = await appeler(creerClient, "POST", {}, "chef", { ...NOUVEAU, nom_agent: "" });
    expect([r.status, await r.json()]).toEqual([422, { erreur: "configuration invalide", champs }]);
    for (const corps of [null, [], "x"]) expect((await appeler(creerClient, "POST", {}, "chef", corps)).status).toBe(400);
    expect(simule.creerClient).toHaveBeenCalledTimes(1);
  });

  it("une cible mal formée n'entre pas au journal telle quelle", async () => {
    await appeler(creerClient, "POST", {}, "chef", { ...NOUVEAU, client: { ...NOUVEAU.client, id: "../Mauvais" } });
    expect((await journal())[0].cible).toBeNull();
  });
});

describe("l'installation d'un client", () => {
  it("enregistrer la clé publique : elle part à l'atelier, le journal n'en garde rien", async () => {
    const r = await appeler(enregistrer, "PUT", CHALET, "exploitant", { cle_publique: CLE_PUBLIQUE, autre: 1 });
    expect([r.status, await r.json()]).toEqual([200, { client: "chalet-essai", cle: "263dfa8b264b31a1" }]);
    expect(simule.enregistrerInstallation.mock.calls).toEqual([["chalet-essai", { cle_publique: CLE_PUBLIQUE }]]);
    expect((await journal()).map((l) => [l.action, l.cible, l.resultat, l.detail])).toEqual([["installation.enregistree", "client:chalet-essai", "ok", null]]);
    expect(await tableJournal()).not.toContain("cleDePilotage");
  });

  it("révoquer la clé ; la réponse de l'atelier", async () => {
    const r = await appeler(revoquer, "DELETE", CHALET, "exploitant");
    expect([r.status, await r.json()]).toEqual([200, { client: "chalet-essai", revoquee: true }]);
    expect((await journal()).map((l) => [l.action, l.resultat, l.detail])).toEqual([["installation.revoquee", "ok", null]]);
  });

  it("proposer une image : la version et l'image partent, et se notent", async () => {
    const r = await appeler(proposerImage, "POST", CHALET, "exploitant", { version: "0.3.0", image: IMAGE, ordre: 9 });
    expect([r.status, await r.json()]).toEqual([201, { client: "chalet-essai", ordre: 3, version: "0.3.0", image: IMAGE }]);
    expect(simule.proposerImage.mock.calls).toEqual([["chalet-essai", { version: "0.3.0", image: IMAGE }]]);
    expect((await journal()).map((l) => [l.action, l.resultat, l.detail])).toEqual([["installation.image", "ok", { version: "0.3.0", image: IMAGE }]]);
  });

  it("une image de mauvaise forme : la console ne juge pas, l'atelier le fait et sa phrase est rendue", async () => {
    const phrase = "version : celle de l'image, par exemple 0.2.0";
    simule.proposerImage.mockRejectedValueOnce(new RefusChamps(400, phrase));
    const r = await appeler(proposerImage, "POST", CHALET, "exploitant", { version: "v3", image: "docker.io/autre:latest" });
    expect([r.status, await r.json()]).toEqual([400, { erreur: phrase }]);
    expect(simule.proposerImage.mock.calls).toEqual([["chalet-essai", { version: "v3", image: "docker.io/autre:latest" }]]);
    expect((await journal()).map((l) => [l.resultat, l.detail])).toEqual([["refuse 400", { version: "v3", image: "docker.io/autre:latest" }]]);
  });

  it("un externe n'enregistre, ne révoque ni ne propose rien, même d'un corps écrit à la main : 403", async () => {
    expect((await appeler(enregistrer, "PUT", CHALET, "invite", { cle_publique: CLE_PUBLIQUE })).status).toBe(403);
    expect((await appeler(revoquer, "DELETE", CHALET, "invite")).status).toBe(403);
    expect((await appeler(proposerImage, "POST", CHALET, "invite", { version: "0.3.0", image: IMAGE })).status).toBe(403);
    expect((await appeler(creerClient, "POST", {}, "invite", NOUVEAU)).status).toBe(403);
    for (const f of Object.values(simule)) expect(f).not.toHaveBeenCalled();
  });
});
