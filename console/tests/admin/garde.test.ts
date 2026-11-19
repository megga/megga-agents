import type { DatabaseSync } from "node:sqlite";
import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { RefusChamps } from "@/lib/admin/atelier";
import { GARDE, garde, gardePage, gardeSession, origineAdmise } from "@/lib/admin/garde";
import { lireJournal } from "@/lib/admin/journal";
import { Refus } from "@/lib/agents";
import { TA } from "@/lib/admin/textes";
import { config, proxy } from "@/proxy";
import { acces, dbEssai, compte, membre, roleVide } from "./aides";

// La session vient de l'en-tête x-essai-qui (routes) ou de etat.qui (pages) ; la base est celle de l'essai.
// connection() note seulement son appel : hors de Next.js, la vraie refuse de répondre.
const etat = vi.hoisted(() => ({ db: undefined as unknown as DatabaseSync, qui: null as string | null, connexions: 0 }));
vi.mock("next/server", async (original) => ({
  ...(await original<typeof import("next/server")>()),
  connection: async () => {
    etat.connexions++;
  },
}));
const sessionPour = (qui: string | null) => (qui ? { user: { id: qui, email: `${qui}@megga.test`, name: qui.toUpperCase() } } : null);

vi.mock("@/lib/base", async (original) => {
  const { baseDe } = await import("./aides");
  return { ...(await original<typeof import("@/lib/base")>()), base: () => etat.db, pret: async () => baseDe(etat.db), donnees: () => baseDe(etat.db) };
});
vi.mock("@/lib/auth", async (original) => ({
  ...(await original<typeof import("@/lib/auth")>()),
  sessionDe: async (r: Request) => sessionPour(r.headers.get("x-essai-qui")),
  session: async () => sessionPour(etat.qui),
}));
vi.mock("next/navigation", () => ({
  redirect: (url: string) => {
    throw new Error(`redirect:${url}`);
  },
  notFound: () => {
    throw new Error("404");
  },
}));

beforeEach(async () => {
  etat.db = await dbEssai();
  etat.qui = null;
});
afterEach(() => vi.restoreAllMocks());

const route = garde({ droit: "clients.piloter", client: (p: { id: string }) => p.id, action: "essai.geste" }, async ({ params }) => ({ id: params.id }));

function appel(id: string, p: { qui?: string; methode?: string; origine?: string | null; corps?: unknown } = {}) {
  const headers: Record<string, string> = {};
  if (p.qui) headers["x-essai-qui"] = p.qui;
  if (p.origine !== null) headers.origin = p.origine ?? "http://localhost";
  const methode = p.methode ?? "POST";
  const requete = new Request(`http://localhost/api/admin/essai/${id}`, {
    method: methode,
    headers,
    body: methode === "GET" ? undefined : JSON.stringify(p.corps ?? {}),
  });
  return route(requete, { params: Promise.resolve({ id }) });
}

const lignes = () => lireJournal(etat.db, acces({ superadmin: true }), { page: 1 }).lignes;

describe("la garde des routes", () => {
  it("vérifie la session, le membre, l'origine, le droit et le client, dans cet ordre", async () => {
    compte(etat.db, { id: "c", courriel: "c@megga.test" });
    membre(etat.db, { utilisateur: "l", role: "lecture" });
    membre(etat.db, { utilisateur: "p", role: "exploitation", perimetre: ["garage-essai"] });
    const statut = async (r: Promise<Response>) => (await r).status;
    expect(await statut(appel("garage-essai"))).toBe(401);
    expect(await (await appel("garage-essai")).json()).toEqual({ erreur: TA.connectezVous });
    expect(await statut(appel("garage-essai", { qui: "c" }))).toBe(404);
    expect(await statut(appel("garage-essai", { qui: "l" }))).toBe(403);
    expect(await statut(appel("garage-essai", { qui: "p", origine: null }))).toBe(403);
    const ailleurs = await appel("garage-essai", { qui: "p", origine: "https://ailleurs.example" });
    expect([ailleurs.status, await ailleurs.json()]).toEqual([403, { erreur: TA.origineRefusee }]);
    expect(await statut(appel("boulangerie-essai", { qui: "p" }))).toBe(404);
    expect(await statut(appel("Garage-essai", { qui: "p" }))).toBe(404);
    const ok = await appel("garage-essai", { qui: "p" });
    expect([ok.status, await ok.json()]).toEqual([200, { id: "garage-essai" }]);
    expect(await statut(appel("garage-essai", { qui: "p", methode: "GET", origine: null }))).toBe(200);
  });

  it("note au journal chaque issue après la session, sans secret", async () => {
    membre(etat.db, { utilisateur: "l", role: "lecture" });
    membre(etat.db, { utilisateur: "p", role: "exploitation", perimetre: ["garage-essai"] });
    await appel("garage-essai");
    await appel("garage-essai", { qui: "p", corps: { jeton: "x", ton: "chaleureux" } });
    await appel("garage-essai", { qui: "l" });
    expect(lignes().map((l) => [l.qui, l.courriel, l.action, l.cible, l.resultat, l.detail])).toEqual([
      ["l", "l@megga.test", "essai.geste", "client:garage-essai", "refuse 403", {}],
      ["p", "p@megga.test", "essai.geste", "client:garage-essai", "ok", { jeton: "[masqué]", ton: "chaleureux" }],
    ]);
  });

  it("une règle avec detail ne note que ce qu'il rend, jamais le corps entier, réussi ou refusé", async () => {
    membre(etat.db, { utilisateur: "s", role: "superadmin" });
    membre(etat.db, { utilisateur: "l", role: "lecture" });
    const resume = garde({ droit: "clients.piloter", client: (p: { id: string }) => p.id, action: "essai.resume",
      detail: (corps, p) => ({ id: p.id, ton: (corps as { ton?: unknown }).ton }) }, async () => ({}));
    const envoi = (qui: string) => resume(new Request("http://localhost/api/admin/essai/garage-essai", { method: "POST",
      headers: { "x-essai-qui": qui, origin: "http://localhost" }, body: JSON.stringify({ ton: "chaleureux", prix: 31.4159 }) }),
    { params: Promise.resolve({ id: "garage-essai" }) });
    expect([(await envoi("s")).status, (await envoi("l")).status]).toEqual([200, 403]);
    expect(lignes().map((l) => [l.qui, l.resultat, l.detail])).toEqual([
      ["l", "refuse 403", { id: "garage-essai", ton: "chaleureux" }],
      ["s", "ok", { id: "garage-essai", ton: "chaleureux" }],
    ]);
    expect(JSON.stringify(etat.db.prepare("SELECT * FROM admin_journal").all())).not.toContain("31.4159");
  });

  it("preciser : le détail décidé pendant le traitement remplace celui de la règle, même si le geste échoue ensuite", async () => {
    membre(etat.db, { utilisateur: "s", role: "superadmin" });
    const geste = garde({ droit: "clients.piloter", client: (p: { id: string }) => p.id, action: "essai.precis",
      detail: (corps) => ({ demande: (corps as { base?: unknown }).base ?? null }) }, async ({ corps, preciser }) => {
      const c = corps as { base?: number; echec?: boolean; preciser?: boolean };
      if (c.preciser) preciser({ envoyee: 3 });
      if (c.echec) throw new Refus(422, "refusé après l'envoi");
      return {};
    });
    const envoi = (corps: unknown) => geste(new Request("http://localhost/api/admin/essai/garage-essai", { method: "POST",
      headers: { "x-essai-qui": "s", origin: "http://localhost" }, body: JSON.stringify(corps) }), { params: Promise.resolve({ id: "garage-essai" }) });
    await envoi({ preciser: true });
    await envoi({ preciser: true, echec: true });
    await envoi({ base: 1 });
    await envoi({ base: 1, echec: true });
    expect(lignes().map((l) => [l.resultat, l.detail]).reverse()).toEqual([
      ["ok", { envoyee: 3 }],
      ["refuse 422", { envoyee: 3 }],
      ["ok", { demande: 1 }],
      ["refuse 422", { demande: 1 }],
    ]);
  });

  it("rend une réponse telle quelle, un refus à son statut, une autre erreur en 500 sans détail", async () => {
    membre(etat.db, { utilisateur: "s", role: "superadmin" });
    const erreur = vi.spyOn(console, "error").mockImplementation(() => {});
    const faire = (traiter: () => Promise<unknown>) =>
      garde({ droit: "equipe.gerer", action: "essai.autre", cible: () => "role:r" }, traiter)(
        new Request("http://localhost/api/admin/x", { method: "POST", headers: { "x-essai-qui": "s", origin: "http://localhost" }, body: "{}" }),
        { params: Promise.resolve({}) },
      );
    const brute = await faire(async () => new Response("brut", { status: 201 }));
    expect([brute.status, await brute.text()]).toEqual([201, "brut"]);
    const refusee = await faire(async () => {
      throw new Refus(409, TA.nomPris);
    });
    expect([refusee.status, await refusee.json()]).toEqual([409, { erreur: TA.nomPris }]);
    const champs = [{ champ: "nom_agent", message: "Le prénom doit faire 40 caractères au plus." }];
    const parChamp = await faire(async () => {
      throw new RefusChamps(422, "configuration invalide", champs);
    });
    expect([parChamp.status, await parChamp.json()]).toEqual([422, { erreur: "configuration invalide", champs }]);
    const sansChamp = await faire(async () => {
      throw new RefusChamps(504, TA.atelierLent);
    });
    expect(await sansChamp.json()).toEqual({ erreur: TA.atelierLent });
    const cassee = await faire(async () => {
      throw new Error("le secret interne");
    });
    expect([cassee.status, await cassee.json()]).toEqual([500, { erreur: TA.erreurInterne }]);
    expect(erreur).toHaveBeenCalledOnce();
    expect(lignes().map((l) => `${l.cible} ${l.resultat}`)).toEqual(["role:r erreur", "role:r refuse 504", "role:r refuse 422", "role:r refuse 409", "role:r ok"]);
  });

  it("un geste qui ne rend rien répond 204 et note ok", async () => {
    membre(etat.db, { utilisateur: "s", role: "superadmin" });
    const erreur = vi.spyOn(console, "error").mockImplementation(() => {});
    let fait = 0;
    const retirer = garde({ droit: "equipe.gerer", action: "roles.retirer", cible: () => "role:r" }, async () => {
      fait++;
    });
    const r = await retirer(
      new Request("http://localhost/api/admin/x", { method: "DELETE", headers: { "x-essai-qui": "s", origin: "http://localhost" } }),
      { params: Promise.resolve({}) },
    );
    expect([r.status, await r.text(), fait]).toEqual([204, "", 1]);
    expect(erreur).not.toHaveBeenCalled();
    expect(lignes().map((l) => `${l.action} ${l.cible} ${l.resultat}`)).toEqual(["roles.retirer role:r ok"]);
  });

  it("un détail est borné à 2048 caractères", async () => {
    membre(etat.db, { utilisateur: "p", role: "exploitation", perimetre: ["garage-essai"] });
    const gros = { texte: "x".repeat(5000) };
    expect((await appel("garage-essai", { qui: "p", corps: gros })).status).toBe(200);
    const [deP] = lignes();
    expect([deP.qui, deP.resultat]).toEqual(["p", "ok"]);
    const longueurs = etat.db.prepare("SELECT qui, length(detail) AS n FROM admin_journal ORDER BY id").all();
    expect(longueurs).toEqual([{ qui: "p", n: 2048 }]);
    expect(deP.detail).toBe(JSON.stringify(gros).slice(0, 2048));
  });

  it("un compte qui n'est pas membre reçoit 404 et ne laisse aucune ligne au journal", async () => {
    compte(etat.db, { id: "c", courriel: "c@megga.test" });
    for (let i = 0; i < 10; i++) expect((await appel("garage-essai", { qui: "c", corps: { n: i } })).status).toBe(404);
    expect(etat.db.prepare("SELECT COUNT(*) AS n FROM admin_journal").get()).toEqual({ n: 0 });
  });

  it("une panne du journal ne casse pas un geste, réussi ou refusé", async () => {
    membre(etat.db, { utilisateur: "p", role: "exploitation", perimetre: ["garage-essai"] });
    membre(etat.db, { utilisateur: "l", role: "lecture" });
    const erreur = vi.spyOn(console, "error").mockImplementation(() => {});
    etat.db.exec("DROP TABLE admin_journal");
    const ok = await appel("garage-essai", { qui: "p" });
    expect([ok.status, await ok.json()]).toEqual([200, { id: "garage-essai" }]);
    expect(erreur).toHaveBeenCalledOnce();
    expect((await appel("garage-essai", { qui: "l" })).status).toBe(403);
    expect(erreur).toHaveBeenCalledTimes(2);
  });

  it("marque chaque route qu'elle garde ; gardeSession ne demande qu'une session", async () => {
    expect(route[GARDE]).toBe(true);
    const rejoindre = gardeSession({ action: "essai.session", detail: (c) => ({ jeton: (c as { jeton: string }).jeton }) },
      async ({ compte, corps }) => ({ qui: compte.id, corps }));
    expect(rejoindre[GARDE]).toBe(true);
    const appelSession = (qui?: string, origine = "http://localhost") =>
      rejoindre(new Request("http://localhost/api/admin/invitation", { method: "POST",
        headers: { ...(qui ? { "x-essai-qui": qui } : {}), origin: origine }, body: JSON.stringify({ jeton: "j", autre: "a" }) }), { params: Promise.resolve({}) });
    expect((await appelSession()).status).toBe(401);
    const ok = await appelSession("c");
    expect([ok.status, await ok.json()]).toEqual([200, { qui: "c", corps: { jeton: "j", autre: "a" } }]);
    expect((await appelSession("c", "https://ailleurs.example")).status).toBe(403);
    expect(lignes().map((l) => `${l.qui} ${l.action} ${l.resultat} ${JSON.stringify(l.detail)}`))
      .toEqual(['c essai.session refuse 403 {"jeton":"[masqué]"}', 'c essai.session ok {"jeton":"[masqué]"}']);
  });

  it("n'admet que l'origine de la requête ou celle de BETTER_AUTH_URL", () => {
    const avec = (origine?: string) => new Request("http://localhost:3000/api/admin/x", { method: "POST", headers: origine ? { origin: origine } : {} });
    expect(origineAdmise(avec("http://localhost:3000"), {})).toBe(true);
    expect(origineAdmise(avec(), {})).toBe(false);
    expect(origineAdmise(avec("http://localhost:3001"), {})).toBe(false);
    expect(origineAdmise(avec("https://console.megga.test"), { BETTER_AUTH_URL: "https://console.megga.test/" })).toBe(true);
    expect(origineAdmise(avec("https://console.megga.test"), { BETTER_AUTH_URL: "pas une adresse" })).toBe(false);
  });
});

describe("la garde des pages", () => {
  it("renvoie à la connexion sans session, répond 404 sans être membre, sans le droit ou hors périmètre", async () => {
    compte(etat.db, { id: "c", courriel: "c@megga.test" });
    membre(etat.db, { utilisateur: "p", role: "lecture", perimetre: ["garage-essai"] });
    roleVide(etat.db);
    membre(etat.db, { utilisateur: "v", role: "vide" });
    await expect(gardePage()).rejects.toThrow("redirect:/connexion?retour=/admin");
    etat.qui = "c";
    await expect(gardePage()).rejects.toThrow("404");
    etat.qui = "v";
    await expect(gardePage()).resolves.toMatchObject({ utilisateur: "v", role: { id: "vide" } });
    await expect(gardePage("clients.voir")).rejects.toThrow("404");
    etat.qui = "p";
    await expect(gardePage("couts.voir")).rejects.toThrow("404");
    await expect(gardePage("clients.voir", "boulangerie-essai")).rejects.toThrow("404");
    await expect(gardePage("clients.voir", "Garage-essai")).rejects.toThrow("404");
    const a = await gardePage("clients.voir", "garage-essai");
    expect(a).toMatchObject({ utilisateur: "p", courriel: "p@megga.test", perimetre: ["garage-essai"] });
  });

  it("ne se rend qu'à la requête, jamais dans un préchargement", async () => {
    membre(etat.db, { utilisateur: "p", role: "lecture" });
    etat.qui = "p";
    etat.connexions = 0;
    await gardePage("clients.voir");
    expect(etat.connexions).toBe(1);
  });
});

describe("le tri de /admin, avant toute page", () => {
  it("envoie à la connexion sans cookie, sauf la page d'une invitation", () => {
    const vers = (url: string) => proxy(new NextRequest(url)).headers.get("location");
    expect(vers("http://localhost/admin/clients")).toBe("http://localhost/connexion?retour=/admin");
    expect(vers("http://localhost/admin")).toBe("http://localhost/connexion?retour=/admin");
    expect(vers("http://localhost/")).toBe("http://localhost/connexion");
    expect(vers("http://localhost/admin/invitation/abc")).toBeNull();
    expect(vers("http://localhost/admin/invitation")).toBeNull();
    expect(vers("http://localhost/admin/invitations")).toBe("http://localhost/connexion?retour=/admin");
    const avecCookie = new NextRequest("http://localhost/admin/clients", { headers: { cookie: "better-auth.session_token=x" } });
    expect(proxy(avecCookie).headers.get("location")).toBeNull();
    expect(config.matcher).toEqual(["/", "/admin/:path*"]);
  });
});
