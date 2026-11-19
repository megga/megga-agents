import { betterAuth } from "better-auth";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PATCH as changerNom } from "@/app/api/admin/compte/route";
import { POST as changerMotDePasse } from "@/app/api/admin/compte/mot-de-passe/route";
import { DELETE as retirerPhoto, PUT as poserPhoto } from "@/app/api/admin/compte/photo/route";
import { DELETE as deconnecterAutres } from "@/app/api/admin/compte/sessions/route";
import { lireJournal } from "@/lib/admin/journal";
import { lirePhoto } from "@/lib/admin/photo";
import { TA } from "@/lib/admin/textes";
import { optionsAuth } from "@/lib/auth";
import type { Base } from "@/lib/donnees/base";
import { acces, baseEssai, membre } from "./aides";

// Les gestes de Mon compte, par leurs routes, avec un vrai Better Auth sur la base de l'essai : de vrais comptes, de vraies
// sessions (leurs cookies), de vrais mots de passe. La garde est celle de l'admin (gardeMembre) : membre en cours, sans droit.

const SECRET = "secret-des-essais-de-la-console-assez-long";
type Auth = ReturnType<typeof betterAuth>;

const etat = vi.hoisted(() => ({ db: undefined as unknown as Base, auth: undefined as unknown as ReturnType<typeof betterAuth> }));
vi.mock("@/lib/base", async (original) => ({
  ...(await original<typeof import("@/lib/base")>()),
  pret: async () => etat.db,
  donnees: () => etat.db,
}));
vi.mock("@/lib/auth", async (original) => ({
  ...(await original<typeof import("@/lib/auth")>()),
  auth: () => etat.auth,
  sessionDe: async (r: Request) => etat.auth.api.getSession({ headers: r.headers }),
}));

beforeEach(async () => {
  etat.db = await baseEssai();
  etat.auth = betterAuth({ ...optionsAuth(etat.db, { CONSOLE_INSCRIPTION: "ouverte" }), secret: SECRET }) as Auth;
});

/** Le cookie que le navigateur renverrait, d'après les Set-Cookie d'une réponse de Better Auth. */
const cookieDe = (h: Headers) => h.getSetCookie().map((c) => c.split(";")[0]).join("; ");

/** Un compte inscrit (et connecté) ; rend son identifiant et le cookie de sa session. */
async function inscrire(courriel: string, motDePasse = "ancien-mot-de-passe") {
  const { headers, response } = await etat.auth.api.signUpEmail({ body: { name: "Chef", email: courriel, password: motDePasse }, returnHeaders: true });
  return { id: response.user.id, cookie: cookieDe(headers) };
}

/** Une session de plus pour ce compte (un autre appareil) : son cookie. */
async function connecter(courriel: string, motDePasse = "ancien-mot-de-passe"): Promise<string> {
  const { headers } = await etat.auth.api.signInEmail({ body: { email: courriel, password: motDePasse }, returnHeaders: true });
  return cookieDe(headers);
}

const reussit = async (courriel: string, motDePasse: string) => connecter(courriel, motDePasse).then(() => true, () => false);

/** Un membre de l'admin, inscrit par Better Auth. */
async function membreInscrit(courriel = "chef@megga.test") {
  const c = await inscrire(courriel);
  await membre(etat.db, { utilisateur: c.id, role: "superadmin" });
  return c;
}

type Route = (r: Request, ctx: { params: Promise<Record<string, string>> }) => Promise<Response>;

function appel(f: Route, methode: string, cookie: string, corps?: unknown) {
  const headers: Record<string, string> = { origin: "http://localhost", cookie };
  return f(new Request("http://localhost/api/admin/compte", { method: methode, headers, body: corps === undefined ? undefined : JSON.stringify(corps) }),
    { params: Promise.resolve({}) });
}

const journal = async () => (await lireJournal(etat.db, acces({ superadmin: true }), { page: 1 })).lignes;
const image = async (id: string) => (await etat.db.un<{ image: string | null }>('SELECT image FROM "user" WHERE id = ?', id))?.image;
const nom = async (id: string) => (await etat.db.un<{ name: string }>('SELECT name FROM "user" WHERE id = ?', id))?.name;

const PNG = Uint8Array.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0, 0, 0, 13, 0x49, 0x48, 0x44, 0x52]);
const photo = { donnees: Buffer.from(PNG).toString("base64"), type: "image/png" };

describe("la photo de son compte", () => {
  it("pose la photo et met à jour l'image du compte", async () => {
    const c = await membreInscrit();
    const r = await appel(poserPhoto, "PUT", c.cookie, photo);
    expect(r.status).toBe(200);
    const { image: adresse } = await r.json();
    expect(adresse).toMatch(new RegExp(`^/api/compte/photo/${c.id}\\?v=[0-9a-f]{12}$`));
    expect(await image(c.id)).toBe(adresse);
    expect([...(await lirePhoto(etat.db, c.id))!.octets]).toEqual([...PNG]);
  });

  it("retire la photo", async () => {
    const c = await membreInscrit();
    await appel(poserPhoto, "PUT", c.cookie, photo);
    const r = await appel(retirerPhoto, "DELETE", c.cookie);
    expect(r.status).toBe(204);
    expect(await image(c.id)).toBeNull();
    expect(await lirePhoto(etat.db, c.id)).toBeUndefined();
  });

  it("note la photo au journal sans ses données", async () => {
    const c = await membreInscrit();
    await appel(poserPhoto, "PUT", c.cookie, photo);
    await appel(retirerPhoto, "DELETE", c.cookie);
    const [retrait, pose] = await journal();
    expect(pose).toMatchObject({ qui: c.id, action: "compte.photo", resultat: "ok", detail: { type: "image/png", octets: PNG.length } });
    expect(retrait).toMatchObject({ qui: c.id, action: "compte.photoRetiree", resultat: "ok", detail: null });
    expect(JSON.stringify(await etat.db.tous("SELECT * FROM admin_journal"))).not.toContain(photo.donnees);
  });

  it("refuse une image déguisée, sans rien ranger ni changer l'image du compte", async () => {
    const c = await membreInscrit();
    const svg = Buffer.from("<svg xmlns='http://www.w3.org/2000/svg'/>").toString("base64");
    const r = await appel(poserPhoto, "PUT", c.cookie, { donnees: svg, type: "image/png" });
    expect(r.status).toBe(400);
    expect(await r.json()).toEqual({ erreur: TA.photoInvalide });
    expect(await image(c.id)).toBeNull();
    expect(await lirePhoto(etat.db, c.id)).toBeUndefined();
    const [ligne] = await journal();
    expect(ligne).toMatchObject({ action: "compte.photo", resultat: "refuse 400" });
    expect(JSON.stringify(ligne)).not.toContain(svg);
  });
});

describe("le nom de son compte", () => {
  it("change le nom", async () => {
    const c = await membreInscrit();
    const r = await appel(changerNom, "PATCH", c.cookie, { nom: "  Alix Martin " });
    expect(r.status).toBe(200);
    expect(await r.json()).toEqual({ nom: "Alix Martin" });
    expect(await nom(c.id)).toBe("Alix Martin");
    const [ligne] = await journal();
    expect(ligne).toMatchObject({ qui: c.id, action: "compte.nom", resultat: "ok", detail: { nom: "Alix Martin" } });
  });

  it("refuse un nom vide", async () => {
    const c = await membreInscrit();
    for (const corps of [{ nom: "   " }, { nom: "" }, {}, { nom: "x".repeat(81) }]) {
      const r = await appel(changerNom, "PATCH", c.cookie, corps);
      expect(r.status, JSON.stringify(corps)).toBe(400);
      expect(await r.json()).toEqual({ erreur: TA.nomCompteManquant });
    }
    expect(await nom(c.id)).toBe("Chef");
  });
});

describe("le mot de passe de son compte", () => {
  it("change le mot de passe", async () => {
    const c = await membreInscrit();
    const r = await appel(changerMotDePasse, "POST", c.cookie, { actuel: "ancien-mot-de-passe", nouveau: "nouveau-mot-de-passe" });
    expect(r.status).toBe(200);
    expect(await reussit("chef@megga.test", "nouveau-mot-de-passe")).toBe(true);
    expect(await reussit("chef@megga.test", "ancien-mot-de-passe")).toBe(false);
    expect(await etat.auth.api.getSession({ headers: new Headers({ cookie: c.cookie }) })).not.toBeNull(); // la session reste
    const [ligne] = await journal();
    expect(ligne).toMatchObject({ qui: c.id, action: "compte.motDePasse", resultat: "ok", detail: null });
  });

  it("refuse un ancien mot de passe faux", async () => {
    const c = await membreInscrit();
    const r = await appel(changerMotDePasse, "POST", c.cookie, { actuel: "pas-le-bon-mot", nouveau: "nouveau-mot-de-passe" });
    expect(r.status).toBe(400);
    expect(await r.json()).toEqual({ erreur: TA.ancienMotDePasseFaux });
    expect(await reussit("chef@megga.test", "ancien-mot-de-passe")).toBe(true);
    expect(await reussit("chef@megga.test", "nouveau-mot-de-passe")).toBe(false);
    const [ligne] = await journal();
    expect(ligne).toMatchObject({ qui: c.id, action: "compte.motDePasse", resultat: "refuse 400", detail: null });
    const tout = JSON.stringify(await etat.db.tous("SELECT * FROM admin_journal"));
    expect(tout).not.toContain("pas-le-bon-mot");
    expect(tout).not.toContain("nouveau-mot-de-passe");
  });

  it("refuse un nouveau mot de passe de moins de 8 caractères", async () => {
    const c = await membreInscrit();
    const r = await appel(changerMotDePasse, "POST", c.cookie, { actuel: "ancien-mot-de-passe", nouveau: "court" });
    expect(r.status).toBe(400);
    expect(await r.json()).toEqual({ erreur: TA.motDePasseCourt });
    expect(await reussit("chef@megga.test", "ancien-mot-de-passe")).toBe(true);
    const sans = await appel(changerMotDePasse, "POST", c.cookie, { nouveau: "nouveau-mot-de-passe" });
    expect(await sans.json()).toEqual({ erreur: TA.ancienMotDePasseManquant });
  });
});

describe("les autres appareils", () => {
  it("déconnecte seulement les autres sessions de ce compte", async () => {
    const c = await membreInscrit();
    const deux = await connecter("chef@megga.test");
    const trois = await connecter("chef@megga.test");
    const autre = await inscrire("autre@megga.test");
    const valide = async (cookie: string) => (await etat.auth.api.getSession({ headers: new Headers({ cookie }) })) !== null;
    expect(await Promise.all([c.cookie, deux, trois, autre.cookie].map(valide))).toEqual([true, true, true, true]);

    const r = await appel(deconnecterAutres, "DELETE", deux);
    expect(r.status).toBe(200);
    expect(await valide(deux)).toBe(true); // celle-ci
    expect(await valide(c.cookie)).toBe(false);
    expect(await valide(trois)).toBe(false);
    expect(await valide(autre.cookie)).toBe(true); // un autre compte
    const restantes = await etat.db.tous<{ userId: string }>('SELECT "userId" FROM session ORDER BY "userId"');
    expect(restantes.map((s) => s.userId).sort()).toEqual([c.id, autre.id].sort());
    const [ligne] = await journal();
    expect(ligne).toMatchObject({ qui: c.id, action: "compte.autresAppareils", resultat: "ok", detail: null });
  });
});

describe("la garde de Mon compte", () => {
  it("refuse un compte qui n'est pas membre", async () => {
    const c = await inscrire("passant@megga.test");
    const gestes: [Route, string, unknown][] = [
      [poserPhoto, "PUT", photo],
      [retirerPhoto, "DELETE", undefined],
      [changerNom, "PATCH", { nom: "Intrus" }],
      [changerMotDePasse, "POST", { actuel: "ancien-mot-de-passe", nouveau: "nouveau-mot-de-passe" }],
      [deconnecterAutres, "DELETE", undefined],
    ];
    for (const [f, methode, corps] of gestes) {
      const r = await appel(f, methode, c.cookie, corps);
      expect(r.status, methode).toBe(404);
    }
    expect(await etat.db.tous("SELECT * FROM admin_journal")).toEqual([]);
    expect(await nom(c.id)).toBe("Chef");
    expect(await image(c.id)).toBeNull();
    expect(await reussit("passant@megga.test", "ancien-mot-de-passe")).toBe(true);
  });

  it("refuse sans session (401) et d'une autre origine (403)", async () => {
    const c = await membreInscrit();
    expect((await appel(changerNom, "PATCH", "", { nom: "X" })).status).toBe(401);
    const ailleurs = await changerNom(new Request("http://localhost/api/admin/compte", {
      method: "PATCH", headers: { origin: "https://ailleurs.example", cookie: c.cookie }, body: JSON.stringify({ nom: "X" }),
    }), { params: Promise.resolve({}) });
    expect(ailleurs.status).toBe(403);
    expect(await nom(c.id)).toBe("Chef");
  });
});
