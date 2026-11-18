import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { atelier, atelierBranche, ATTENTE_MS, GARDE_MS, lireErreur, oublier, RefusChamps } from "@/lib/admin/atelier";
import { TA } from "@/lib/admin/textes";
import { refusAsync } from "./aides";

// Le client de l'atelier : sans réseau, fetch simulé. Le jeton de MEGGA ne quitte jamais le serveur.

const CONSOLE = join(__dirname, "../..");

function fichiers(dossier: string): string[] {
  return readdirSync(dossier).flatMap((n) => {
    const c = join(dossier, n);
    return statSync(c).isDirectory() ? fichiers(c) : /\.(tsx?|mjs|js)$/.test(n) ? [c] : [];
  });
}

const reponse = (corps: unknown, statut = 200) => new Response(JSON.stringify(corps), { status: statut, headers: { "content-type": "application/json" } });

let fetchSimule: ReturnType<typeof vi.fn>;

beforeEach(() => {
  oublier();
  process.env.ATELIER_URL = "http://atelier.test";
  process.env.ATELIER_JETON = "jeton-essai";
  fetchSimule = vi.fn(async () => reponse({ clients: [], porte: true }));
  vi.stubGlobal("fetch", fetchSimule);
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  delete process.env.ATELIER_URL;
  delete process.env.ATELIER_JETON;
});

describe("les refus de l'atelier", () => {
  it("montrent sa phrase, et ses messages champ par champ quand details en est une liste", () => {
    expect(lireErreur(400, { erreur: "jours : un nombre de 1 à 365" })).toMatchObject({ statut: 400, message: "jours : un nombre de 1 à 365", champs: [] });
    const champs = [{ champ: "nom_agent", message: "Le prénom doit faire 40 caractères au plus." }];
    const e = lireErreur(422, { erreur: "configuration invalide", details: champs });
    expect(e).toBeInstanceOf(RefusChamps);
    expect([e.statut, e.message, e.champs]).toEqual([422, "configuration invalide", champs]);
    expect(lireErreur(500, { erreur: "mise en service interrompue", details: { annuaire_retabli: false } }).champs).toEqual([]);
    expect(lireErreur(409, { erreur: "version incomplète", details: ["le pack immobilier attend son catalogue"] }).champs).toEqual([]);
  });

  it("d'une autre forme donnent une phrase générale", () => {
    expect(lireErreur(422, { detail: [{ loc: ["body"], msg: "Field required" }] })).toMatchObject({ statut: 422, message: TA.atelierRefus, champs: [] });
    expect(lireErreur(502, "texte")).toMatchObject({ statut: 502, message: TA.atelierRefus });
    expect(lireErreur(500, null).message).toBe(TA.atelierRefus);
  });

  it("pour le jeton de la console sont une panne du branchement, pas un refus fait au membre", () => {
    expect(lireErreur(401, { erreur: "jeton refusé" })).toMatchObject({ statut: 502, message: "jeton refusé" });
    expect(lireErreur(403, { erreur: "réservé à MEGGA" }).statut).toBe(502);
  });
});

describe("les appels", () => {
  it("vont à l'atelier avec le jeton de MEGGA", async () => {
    expect(await atelier.clients()).toEqual({ clients: [], porte: true });
    const [url, init] = fetchSimule.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://atelier.test/atelier/clients");
    expect(new Headers(init.headers).get("authorization")).toBe("Bearer jeton-essai");
    expect(init.method).toBe("GET");
  });

  it("passent les segments par encodeURIComponent, la période et le corps", async () => {
    fetchSimule.mockImplementation(async () => reponse({}));
    await atelier.echanges("garage-essai", "api:dossier:client/42");
    await atelier.suivi("garage-essai", 30);
    await atelier.activer("garage-essai", 2, { forcer: true });
    const appels = fetchSimule.mock.calls as [string, RequestInit][];
    expect(appels.map(([u]) => u)).toEqual([
      "http://atelier.test/atelier/clients/garage-essai/conversations/api%3Adossier%3Aclient%2F42",
      "http://atelier.test/atelier/clients/garage-essai/suivi?jours=30",
      "http://atelier.test/atelier/clients/garage-essai/versions/2/activer",
    ]);
    expect([appels[2][1].method, appels[2][1].body]).toEqual(["POST", JSON.stringify({ forcer: true })]);
    expect(new Headers(appels[2][1].headers).get("content-type")).toBe("application/json");
  });

  it("sans ATELIER_URL, le moteur n'est pas branché, et rien ne part", async () => {
    delete process.env.ATELIER_URL;
    expect(atelierBranche()).toBe(false);
    expect(await refusAsync(() => atelier.clients())).toMatchObject({ statut: 503, message: TA.moteurNonBranche });
    expect(fetchSimule).not.toHaveBeenCalled();
    process.env.ATELIER_URL = "http://atelier.test";
    expect(atelierBranche()).toBe(true);
  });

  it("un atelier injoignable : 502, sans rien dire du jeton", async () => {
    fetchSimule.mockRejectedValue(new Error("jeton-essai injoignable"));
    const e = await refusAsync(() => atelier.clients());
    expect([e.statut, e.message]).toEqual([502, TA.atelierInjoignable]);
    expect(e.message).not.toContain("jeton-essai");
  });

  it("un atelier qui ne répond jamais : 504 au bout de ATTENTE_MS", async () => {
    vi.useFakeTimers();
    fetchSimule.mockImplementation(
      (_: string, init: RequestInit) => new Promise((_ok, non) => init.signal?.addEventListener("abort", () => non(init.signal?.reason))),
    );
    const attente = refusAsync(() => atelier.clients());
    await vi.advanceTimersByTimeAsync(ATTENTE_MS - 1);
    let fini = false;
    void attente.then(() => (fini = true));
    await Promise.resolve();
    expect(fini).toBe(false);
    await vi.advanceTimersByTimeAsync(1);
    expect(await attente).toMatchObject({ statut: 504, message: TA.atelierLent });
  });

  it("un refus de l'atelier devient un RefusChamps", async () => {
    fetchSimule.mockResolvedValue(reponse({ erreur: "client inconnu" }, 404));
    expect(await refusAsync(() => atelier.client("garage-essai"))).toMatchObject({ statut: 404, message: "client inconnu", champs: [] });
  });
});

describe("la garde en mémoire", () => {
  it("garde une lecture GARDE_MS ; une écriture ou le temps l'oublient", async () => {
    vi.useFakeTimers();
    await atelier.clients();
    await atelier.clients();
    expect(fetchSimule).toHaveBeenCalledTimes(1);
    fetchSimule.mockResolvedValueOnce(reponse({ client: "garage-essai", jeton: "j" }, 201));
    await atelier.creerJeton("garage-essai");
    await atelier.clients();
    expect(fetchSimule).toHaveBeenCalledTimes(3);
    await vi.advanceTimersByTimeAsync(GARDE_MS);
    await atelier.clients();
    expect(fetchSimule).toHaveBeenCalledTimes(4);
  });

  it("ne garde pas un refus", async () => {
    fetchSimule.mockResolvedValueOnce(reponse({ erreur: "x" }, 500));
    await refusAsync(() => atelier.clients());
    await atelier.clients();
    expect(fetchSimule).toHaveBeenCalledTimes(2);
  });
});

describe("le jeton de MEGGA reste sur le serveur", () => {
  const src = fichiers(join(CONSOLE, "src"));

  it("atelier.ts commence par server-only", () => {
    expect(readFileSync(join(CONSOLE, "src/lib/admin/atelier.ts"), "utf8").startsWith('import "server-only";')).toBe(true);
  });

  it("ATELIER_JETON n'est lu que dans atelier.ts", () => {
    const avec = src.filter((f) => readFileSync(f, "utf8").includes("ATELIER_JETON")).map((f) => relative(CONSOLE, f));
    expect(avec).toEqual(["src/lib/admin/atelier.ts"]);
  });

  it("aucun composant client n'importe le client de l'atelier, sauf ses types", () => {
    for (const f of src) {
      const texte = readFileSync(f, "utf8");
      if (!/^\s*["']use client["']/m.test(texte)) continue;
      const imports = texte.match(/^import\s+(?!type\b).*from\s+["']@\/lib\/admin\/atelier["']/gm) ?? [];
      expect(imports, f).toEqual([]);
    }
  });
});
