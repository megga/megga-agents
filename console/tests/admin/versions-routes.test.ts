import type { DatabaseSync } from "node:sqlite";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { POST as activer } from "@/app/api/admin/clients/[id]/versions/[numero]/activer/route";
import { POST as essayer } from "@/app/api/admin/clients/[id]/versions/[numero]/essai/route";
import { POST as preparer } from "@/app/api/admin/clients/[id]/versions/route";
import { POST as valider } from "@/app/api/admin/clients/[id]/valider/route";
import { RefusChamps } from "@/lib/admin/atelier";
import { lireJournal } from "@/lib/admin/journal";
import { TA } from "@/lib/admin/textes";
import { acces, baseEssai, membre } from "./aides";

// Les routes des versions, appelées comme Next.js les appelle : la session vient de l'en-tête x-essai-qui, la base est celle
// de l'essai, l'atelier est simulé. Un externe ne prépare que les réglages simples, ne met rien en service, et le journal ne
// garde ni la configuration, ni les consignes, ni le texte d'un essai.

const etat = vi.hoisted(() => ({ db: undefined as unknown as DatabaseSync }));
vi.mock("@/lib/base", async (original) => ({ ...(await original<typeof import("@/lib/base")>()), base: () => etat.db }));
vi.mock("@/lib/auth", async (original) => ({
  ...(await original<typeof import("@/lib/auth")>()),
  sessionDe: async (r: Request) => {
    const qui = r.headers.get("x-essai-qui");
    return qui ? { user: { id: qui, email: `${qui}@megga.test`, name: qui } } : null;
  },
}));

const simule = vi.hoisted(() => ({
  client: vi.fn(),
  version: vi.fn(),
  catalogue: vi.fn(),
  valider: vi.fn(),
  ajouterVersion: vi.fn(),
  depuisGabarit: vi.fn(),
  essai: vi.fn(),
  activer: vi.fn(),
}));
vi.mock("@/lib/admin/atelier", async (original) => {
  const vrai = await original<typeof import("@/lib/admin/atelier")>();
  return { ...vrai, atelier: { ...vrai.atelier, ...simule } };
});

const CONSIGNES = "Consignes sur mesure du garage, écrites par MEGGA";
const CONFIG = { id: "garage-essai", metier: "immobilier", outils: ["immobilier"], consignes: CONSIGNES, voix: { voix: "v0", stabilite: 0.5 } };
const CATALOGUE = { metiers: { general: [], immobilier: ["immobilier"] }, champs_client: ["metier", "nom_agent", "voix", "ton", "outils"],
  zones: ["europe", "client"], zones_porte: ["europe"], modeles: [] };
const BROUILLON = { version: 4, etat: "brouillon", auteur: "megga", base: 3, essais: 0, cree_le: null, manques: [] };
const MESSAGE = "Bonjour, un message d'essai qui ne doit jamais aller au journal";
const REPONSE = "Bien reçu, une réponse d'essai qui ne doit jamais aller au journal";

type Route<P> = (r: Request, ctx: { params: Promise<P> }) => Promise<Response>;

function appeler<P>(route: Route<P>, params: P, qui: string, corps?: unknown) {
  const requete = new Request("http://localhost/api/admin/essai", {
    method: "POST",
    headers: { origin: "http://localhost", "x-essai-qui": qui },
    body: corps === undefined ? undefined : JSON.stringify(corps),
  });
  return route(requete, { params: Promise.resolve(params) });
}

const journal = () => lireJournal(etat.db, acces({ superadmin: true }), { page: 1 }).lignes;
const tableJournal = () => JSON.stringify(etat.db.prepare("SELECT * FROM admin_journal").all());
const ecritures = () => [simule.valider, simule.ajouterVersion, simule.depuisGabarit, simule.essai, simule.activer].filter((f) => f.mock.calls.length);

beforeEach(async () => {
  for (const f of Object.values(simule)) f.mockReset();
  simule.client.mockResolvedValue({ id: "garage-essai", derniere_version: 3, version_en_service: 2, gere_par_megga: false, config: CONFIG });
  simule.version.mockImplementation(async (_: string, n: number) => ({ version: n, etat: "publiee", config: { ...CONFIG, ton: `ton ${n}` } }));
  simule.catalogue.mockResolvedValue(CATALOGUE);
  simule.valider.mockResolvedValue({ base: 3, config: CONFIG, manques: [] });
  simule.ajouterVersion.mockResolvedValue(BROUILLON);
  simule.depuisGabarit.mockResolvedValue({ ...BROUILLON, gabarit: "immobilier" });
  simule.essai.mockResolvedValue({ version: 2, conversation: "1", reponse: REPONSE });
  simule.activer.mockResolvedValue({ client: "boulangerie-essai", version_en_service: 2, retour: false, annuaire: {} });
  etat.db = await baseEssai();
  membre(etat.db, { utilisateur: "invite", role: "exploitation", externe: true, perimetre: ["garage-essai"] });
  membre(etat.db, { utilisateur: "exploitant", role: "exploitation" });
  membre(etat.db, { utilisateur: "chef", role: "superadmin" });
});

describe("préparer une version", () => {
  it("un externe qui touche aux consignes : 403, rien ne part à l'atelier, la tentative notée sans la valeur", async () => {
    const r = await appeler(preparer, { id: "garage-essai" }, "invite", { changements: { consignes: "Mes consignes à moi" } });
    expect([r.status, await r.json()]).toEqual([403, { erreur: TA.reglagesReserves("consignes") }]);
    expect(ecritures()).toEqual([]);
    expect(journal().map((l) => [l.qui, l.action, l.cible, l.resultat, l.detail])).toEqual([
      ["invite", "versions.preparer", "client:garage-essai", "refuse 403", { base: null, changements: ["consignes"] }],
    ]);
    expect(tableJournal()).not.toContain("Mes consignes");
  });

  it("un externe ne prépare pas d'après un modèle par métier, ne force rien, ne règle ni le numéro ni les modèles", async () => {
    for (const corps of [{ gabarit: "immobilier" }, { changements: { whatsapp: { numero_id: "1" } } }, { changements: { modeles: {} } },
      { changements: { ton: "x", id: "autre-essai" } }]) {
      expect((await appeler(preparer, { id: "garage-essai" }, "invite", corps)).status, JSON.stringify(corps)).toBe(403);
    }
    expect(ecritures()).toEqual([]);
  });

  it("un externe : sa base est la version en service, nommée à l'atelier ; la voix par son identifiant ; la réponse, 201", async () => {
    const r = await appeler(preparer, { id: "garage-essai" }, "invite", { changements: { voix: "v1" }, forcer: true });
    expect([r.status, await r.json()]).toEqual([201, BROUILLON]);
    expect(simule.ajouterVersion.mock.calls).toEqual([["garage-essai", { base: 2, changements: { voix: { voix: "v1" } } }]]);
    expect(simule.version.mock.calls).toEqual([["garage-essai", 2]]);
    expect(journal().map((l) => [l.action, l.resultat, l.detail])).toEqual([["versions.preparer", "ok", { base: 2, changements: ["voix"] }]]);
  });

  it("un externe qui nomme une base ancienne (d'autres consignes de MEGGA) : 403, l'atelier n'est pas appelé", async () => {
    simule.version.mockImplementation(async (_: string, n: number) =>
      ({ version: n, etat: "publiee", config: { ...CONFIG, consignes: n === 1 ? "Anciennes consignes de MEGGA" : CONSIGNES } }));
    for (const base of [1, 3, "2", 0, 1.5, "abc", {}]) {
      const r = await appeler(preparer, { id: "garage-essai" }, "invite", { base, changements: { ton: "x" } });
      expect([r.status, await r.json()], JSON.stringify(base)).toEqual([403, { erreur: TA.baseImposee }]);
      expect((await appeler(valider, { id: "garage-essai" }, "invite", { base, changements: { ton: "x" } })).status, JSON.stringify(base)).toBe(403);
    }
    expect(ecritures()).toEqual([]);
    expect(simule.version).not.toHaveBeenCalled();
  });

  it("un externe qui nomme la version en service, ou une base nulle : accepté, la base en service part", async () => {
    await appeler(preparer, { id: "garage-essai" }, "invite", { base: 2, changements: { ton: "x" } });
    await appeler(preparer, { id: "garage-essai" }, "invite", { base: null, changements: { ton: "y" } });
    expect(simule.ajouterVersion.mock.calls).toEqual([["garage-essai", { base: 2, changements: { ton: "x" } }],
      ["garage-essai", { base: 2, changements: { ton: "y" } }]]);
  });

  it("un externe : changer de métier retire les outils que ce métier ne permet pas, d'après la version en service", async () => {
    simule.version.mockResolvedValueOnce({ version: 2, etat: "publiee", config: { ...CONFIG, outils: ["immobilier"] } });
    await appeler(preparer, { id: "garage-essai" }, "invite", { changements: { metier: "general" } });
    expect(simule.ajouterVersion.mock.calls).toEqual([["garage-essai", { base: 2, changements: { metier: "general", outils: [] } }]]);
  });

  it("un client jamais mis en service : la base d'un externe est sa dernière version", async () => {
    simule.client.mockResolvedValue({ id: "garage-essai", derniere_version: 3, version_en_service: null, gere_par_megga: false, config: null });
    await appeler(preparer, { id: "garage-essai" }, "invite", { changements: { ton: "x" } });
    expect(simule.version.mock.calls).toEqual([["garage-essai", 3]]);
    expect(simule.ajouterVersion.mock.calls).toEqual([["garage-essai", { base: 3, changements: { ton: "x" } }]]);
  });

  it("un membre interne choisit sa base, sinon la dernière ; le corps envoyé la porte toujours, modèle par métier compris", async () => {
    const r = await appeler(preparer, { id: "garage-essai" }, "exploitant", { gabarit: "immobilier", nom_agent: "Max" });
    expect(r.status).toBe(201);
    expect(simule.depuisGabarit.mock.calls).toEqual([["garage-essai", { gabarit: "immobilier", nom_agent: "Max", base: 3 }]]);
    const changements = { consignes: CONSIGNES, whatsapp: { numero_id: "100000000000012" } };
    await appeler(preparer, { id: "garage-essai" }, "exploitant", { base: 1, changements });
    await appeler(preparer, { id: "garage-essai" }, "exploitant", { changements: { ton: "x" } });
    expect(simule.ajouterVersion.mock.calls).toEqual([["garage-essai", { base: 1, changements }], ["garage-essai", { base: 3, changements: { ton: "x" } }]]);
    expect([simule.version.mock.calls, simule.catalogue.mock.calls]).toEqual([[], []]);
    expect(journal().map((l) => l.detail)).toEqual([{ base: 3, changements: ["ton"] }, { base: 1, changements: ["consignes", "whatsapp"] },
      { base: 3, gabarit: "immobilier" }]);
    expect(tableJournal()).not.toContain("Consignes sur mesure");
  });

  it("un membre interne qui nomme une base qui n'est pas un numéro : 400, rien ne part", async () => {
    for (const base of ["2", 0, -1, 1.5, "abc", {}]) {
      const r = await appeler(preparer, { id: "garage-essai" }, "exploitant", { base, changements: { ton: "x" } });
      expect([r.status, await r.json()], JSON.stringify(base)).toEqual([400, { erreur: TA.baseInvalide }]);
    }
    expect(ecritures()).toEqual([]);
  });

  it("le journal note la base réellement envoyée à l'atelier, même refusée par lui ; rien d'envoyé, la base que le corps nomme", async () => {
    simule.ajouterVersion.mockRejectedValueOnce(new RefusChamps(422, "configuration invalide"));
    await appeler(preparer, { id: "garage-essai" }, "exploitant", { changements: { ton: "x" } });
    await appeler(preparer, { id: "garage-essai" }, "invite", { base: null, changements: { ton: "y" } });
    await appeler(preparer, { id: "garage-essai" }, "invite", { base: 1, changements: { ton: "z" } });
    expect(journal().map((l) => [l.qui, l.resultat, l.detail]).reverse()).toEqual([
      ["exploitant", "refuse 422", { base: 3, changements: ["ton"] }],
      ["invite", "ok", { base: 2, changements: ["ton"] }],
      ["invite", "refuse 403", { base: 1, changements: ["ton"] }],
    ]);
  });

  it("dans la table admin_journal, sans base nommée : la base réellement envoyée (la dernière pour un interne, celle en service pour un externe)", async () => {
    await appeler(preparer, { id: "garage-essai" }, "exploitant", { changements: { ton: "x" } });
    await appeler(preparer, { id: "garage-essai" }, "invite", { changements: { ton: "y" } });
    const lignes = (etat.db.prepare("SELECT qui, action, resultat, detail FROM admin_journal ORDER BY id").all() as
      { qui: string; action: string; resultat: string; detail: string }[]).map((l) => ({ ...l, detail: JSON.parse(l.detail) }));
    expect(lignes).toEqual([
      { qui: "exploitant", action: "versions.preparer", resultat: "ok", detail: { base: 3, changements: ["ton"] } },
      { qui: "invite", action: "versions.preparer", resultat: "ok", detail: { base: 2, changements: ["ton"] } },
    ]);
    expect(simule.ajouterVersion.mock.calls.map((c) => (c[1] as { base: number }).base)).toEqual([3, 2]);
  });

  it("un refus de l'atelier rend sa phrase et ses messages champ par champ", async () => {
    const champs = [{ champ: "nom_agent", message: "Le prénom doit faire 40 caractères au plus." }];
    simule.ajouterVersion.mockRejectedValue(new RefusChamps(422, "configuration invalide", champs));
    const r = await appeler(preparer, { id: "garage-essai" }, "exploitant", { changements: { nom_agent: "x".repeat(41) } });
    expect([r.status, await r.json()]).toEqual([422, { erreur: "configuration invalide", champs }]);
    expect(journal().map((l) => l.resultat)).toEqual(["refuse 422"]);
  });
});

describe("valider des changements", () => {
  it("rend le résultat de l'atelier sans rien noter ; un externe y est filtré comme pour préparer, d'après la version en service", async () => {
    const r = await appeler(valider, { id: "garage-essai" }, "invite", { changements: { ton: "chaleureux" } });
    expect([r.status, await r.json()]).toEqual([200, { base: 3, config: CONFIG, manques: [] }]);
    expect(simule.valider.mock.calls).toEqual([["garage-essai", { base: 2, changements: { ton: "chaleureux" } }]]);
    expect((await appeler(valider, { id: "garage-essai" }, "invite", { changements: { consignes: "x" } })).status).toBe(403);
    expect((await appeler(valider, { id: "garage-essai" }, "invite", { gabarit: "immobilier" })).status).toBe(403);
    await appeler(valider, { id: "garage-essai" }, "exploitant", { changements: { consignes: CONSIGNES } });
    expect(simule.valider.mock.calls[1]).toEqual(["garage-essai", { base: 3, changements: { consignes: CONSIGNES } }]);
    expect(simule.valider).toHaveBeenCalledTimes(2);
    expect(journal()).toEqual([]);
  });
});

describe("essayer une version", () => {
  it("le message part à l'atelier ; le journal ne garde que la version et le rôle, jamais le texte", async () => {
    const r = await appeler(essayer, { id: "garage-essai", numero: "2" }, "invite", { message: MESSAGE, role: "visiteur", conversation: "abc", forcer: true });
    expect([r.status, await r.json()]).toEqual([200, { version: 2, conversation: "1", reponse: REPONSE }]);
    expect(simule.essai.mock.calls).toEqual([["garage-essai", 2, { message: MESSAGE, conversation: "abc", role: "visiteur" }]]);
    expect(journal().map((l) => [l.qui, l.action, l.cible, l.resultat, l.detail])).toEqual([
      ["invite", "versions.essayer", "client:garage-essai", "ok", { version: 2, role: "visiteur" }],
    ]);
    expect(tableJournal()).not.toContain("message d'essai");
    expect(tableJournal()).not.toContain("réponse d'essai");
  });

  it("un numéro qui n'est pas un entier positif : 400, avant tout appel", async () => {
    for (const numero of ["abc", "0", "-1", "1.5", "02"]) {
      const r = await appeler(essayer, { id: "garage-essai", numero }, "exploitant", { message: "x" });
      expect([r.status, await r.json()], numero).toEqual([400, { erreur: TA.numeroInvalide }]);
    }
    expect(simule.essai).not.toHaveBeenCalled();
  });
});

describe("mettre en service", () => {
  it("un superadmin : la version part à l'atelier, la ligne clients.activer est notée", async () => {
    const r = await appeler(activer, { id: "boulangerie-essai", numero: "2" }, "chef", {});
    expect(r.status).toBe(200);
    expect(simule.activer.mock.calls).toEqual([["boulangerie-essai", 2, {}]]);
    expect(journal().map((l) => [l.qui, l.action, l.cible, l.resultat, l.detail])).toEqual([
      ["chef", "clients.activer", "client:boulangerie-essai", "ok", { version: 2, forcer: false }],
    ]);
  });

  it("forcer passe tel quel, et se note ; un corps absent vaut {}", async () => {
    await appeler(activer, { id: "boulangerie-essai", numero: "4" }, "exploitant", { forcer: true, autre: 1 });
    await appeler(activer, { id: "boulangerie-essai", numero: "3" }, "exploitant");
    expect(simule.activer.mock.calls).toEqual([["boulangerie-essai", 4, { forcer: true }], ["boulangerie-essai", 3, {}]]);
    expect(journal().map((l) => l.detail)).toEqual([{ version: 3, forcer: false }, { version: 4, forcer: true }]);
  });

  it("un externe ne met rien en service, même d'un corps écrit à la main : 403, l'atelier jamais appelé", async () => {
    for (const corps of [{}, { forcer: true }]) {
      expect((await appeler(activer, { id: "garage-essai", numero: "2" }, "invite", corps)).status).toBe(403);
    }
    expect(simule.activer).not.toHaveBeenCalled();
    expect(journal().map((l) => [l.qui, l.action, l.resultat])).toEqual([["invite", "clients.activer", "refuse 403"], ["invite", "clients.activer", "refuse 403"]]);
  });

  it("un numéro qui n'est pas un entier positif : 400, avant tout appel", async () => {
    expect((await appeler(activer, { id: "boulangerie-essai", numero: "abc" }, "chef", {})).status).toBe(400);
    expect(simule.activer).not.toHaveBeenCalled();
  });
});
