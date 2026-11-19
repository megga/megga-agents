import { betterAuth } from "better-auth";
import { getMigrations } from "better-auth/db/migration";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  COMPTES_PAR_PAGE,
  deconnecter,
  ficheCompte,
  filtresComptesDe,
  listerComptes,
  peutAgirSur,
  reactiver,
  suspendre,
  totauxConsole,
  type AdaptateurComptes,
} from "@/lib/admin/comptes";
import { modifierMembre, retirerMembre } from "@/lib/admin/membres";
import { TA } from "@/lib/admin/textes";
import { compterTour, noterConnexion } from "@/lib/admin/usage";
import { creer } from "@/lib/agents";
import { CHEMINS_ADMIN_FERMES, optionsAuth } from "@/lib/auth";
import { preparer } from "@/lib/base";
import type { Base } from "@/lib/donnees/base";
import { T } from "@/lib/textes";
import { baseVide, moteurParDefaut } from "../moteurs";
import { baseEssai, colonnes, compte, membre, refusAsync, T0 } from "./aides";

// Les comptes de la console et leur suspension : la liste, la fiche, les totaux de la vue d'ensemble ; suspendre, réactiver,
// déconnecter partout, par l'adaptateur interne de Better Auth (ses routes HTTP de l'extension admin restent fermées).

const JOUR = 24 * 3600 * 1000;
const avant = (jours: number) => new Date(T0.getTime() - jours * JOUR);

let db: Base;
let appels: unknown[][];
let ad: AdaptateurComptes;

beforeEach(async () => {
  db = await baseEssai();
  appels = [];
  ad = {
    updateUser: vi.fn(async (...a: unknown[]) => appels.push(["updateUser", ...a])),
    deleteUserSessions: vi.fn(async (...a: unknown[]) => appels.push(["deleteUserSessions", ...a])),
  };
  await compte(db, { id: "c", courriel: "garage@exemple.test", nom: "Garage du Lac" });
});

const SECRET = "secret-des-essais-de-la-console-assez-long";

/** La première page des comptes, sans recherche. */
const tous = async (d: Base, maintenant: Date) => (await listerComptes(d, { page: 1 }, maintenant)).comptes;

describe("les routes HTTP de l'extension admin de Better Auth", () => {
  it("sont toutes les quinze fermées", async () => {
    expect(CHEMINS_ADMIN_FERMES).toHaveLength(15);
    for (const c of ["/admin/ban-user", "/admin/impersonate-user", "/admin/set-role", "/admin/create-user", "/admin/unban-user", "/admin/list-users"]) {
      expect(CHEMINS_ADMIN_FERMES).toContain(c);
    }
    expect(optionsAuth(db).disabledPaths).toEqual(CHEMINS_ADMIN_FERMES);
  });

  it("ne répondent à personne, même à un superadmin qui serait aussi « admin » pour Better Auth", async () => {
    const appeler = async (auth: { handler: (r: Request) => Promise<Response> }, chemin: string, corps: unknown, cookie = "") =>
      auth.handler(new Request(`http://localhost:3000/api/auth${chemin}`, {
        method: "POST",
        headers: { "content-type": "application/json", origin: "http://localhost:3000", cookie },
        body: JSON.stringify(corps),
      }));
    const libre = { CONSOLE_INSCRIPTION: "ouverte" }; // le compte s'inscrit sans invitation (tests/inscription.test.ts)
    const ouverte = betterAuth({ ...optionsAuth(db, libre), disabledPaths: [], secret: SECRET, baseURL: "http://localhost:3000" });
    const fermee = betterAuth({ ...optionsAuth(db, libre), secret: SECRET, baseURL: "http://localhost:3000" });
    const inscrit = await appeler(fermee, "/sign-up/email", { name: "Chef", email: "chef@megga.test", password: "motdepasse" });
    const chef = ((await inscrit.json()) as { user: { id: string } }).user.id;
    await db.ecrire("UPDATE \"user\" SET role = 'admin' WHERE id = ?", chef);
    await membre(db, { utilisateur: chef, role: "superadmin" });
    const cookie = (inscrit.headers.get("set-cookie") ?? "").split(";")[0];

    const r = await appeler(fermee, "/admin/ban-user", { userId: "c", banReason: "essai" }, cookie);
    expect(r.status).toBe(404);
    expect((await appeler(fermee, "/admin/set-role", { userId: "c", role: "admin" }, cookie)).status).toBe(404);
    expect(await db.un('SELECT banned, role FROM "user" WHERE id = ?', "c")).toEqual({ banned: null, role: null });
    // Témoin : la même requête passe sans disabledPaths. C'est bien la fermeture qui refuse.
    expect((await appeler(ouverte, "/admin/ban-user", { userId: "c", banReason: "essai" }, cookie)).status).toBe(200);
  });
});

/** Une session ouverte d'un compte. */
async function ouvrirSession(id: string, utilisateur: string) {
  await db.ecrire('INSERT INTO session (id, "expiresAt", token, "createdAt", "updatedAt", "userId") VALUES (?, ?, ?, ?, ?, ?)',
    id, "2026-12-01T10:00:00.000Z", `jeton-${id}`, T0.toISOString(), T0.toISOString(), utilisateur);
}

/** Ce que la base dit d'un compte : banni (1 ou 0, sous les deux moteurs), son motif, ses sessions. */
async function etatCompte(id: string) {
  const u = (await db.un<{ banni: number; motif: string | null }>(
    'SELECT CASE WHEN banned THEN 1 ELSE 0 END AS banni, "banReason" AS motif FROM "user" WHERE id = ?', id))!;
  const { n } = (await db.un<{ n: number }>('SELECT COUNT(*) AS n FROM session WHERE "userId" = ?', id))!;
  return { ...u, sessions: n };
}

describe("suspendre un compte", () => {
  beforeEach(async () => {
    await ouvrirSession("s1", "c");
    await ouvrirSession("s2", "c");
  });

  it("un membre avec comptes.gerer suspend un compte ordinaire : le bannissement, puis ses sessions effacées", async () => {
    const a = await membre(db, { utilisateur: "exploitant", role: "exploitation" });
    await ouvrirSession("s3", "exploitant");
    await suspendre(db, a, "c", { motif: "  Abus  " });
    expect(await etatCompte("c")).toEqual({ banni: 1, motif: "Abus", sessions: 0 });
    expect(await etatCompte("exploitant")).toEqual({ banni: 0, motif: null, sessions: 1 }); // seulement les siennes
    expect(appels).toEqual([]); // ni l'adaptateur de Better Auth, ni une autre connexion
  });

  it("sans motif, ou un motif de plus de 200 caractères : 400, rien n'est écrit", async () => {
    const a = await membre(db, { utilisateur: "exploitant", role: "exploitation" });
    for (const corps of [{ motif: "" }, { motif: "   " }, { motif: "x".repeat(201) }, {}, { motif: 3 }, null]) {
      const e = await refusAsync(() => suspendre(db, a, "c", corps));
      expect([e.statut, e.message], JSON.stringify(corps)).toEqual([400, TA.motifManquant]);
    }
    expect(await etatCompte("c")).toEqual({ banni: 0, motif: null, sessions: 2 });
    await suspendre(db, a, "c", { motif: "é".repeat(200) });
    expect(await etatCompte("c")).toEqual({ banni: 1, motif: "é".repeat(200), sessions: 0 });
  });

  it("un compte inconnu : 404", async () => {
    const a = await membre(db, { utilisateur: "exploitant", role: "exploitation" });
    const e = await refusAsync(() => suspendre(db, a, "personne", { motif: "Abus" }));
    expect([e.statut, e.message]).toEqual([404, TA.compteInconnu]);
    expect(await db.tous('SELECT id FROM "user" WHERE banned IS TRUE')).toEqual([]);
    expect(await etatCompte("c")).toEqual({ banni: 0, motif: null, sessions: 2 });
  });

  it("le compte d'un membre sans être superadmin, celui d'un superadmin, le sien : 403, rien n'est écrit", async () => {
    const exploitant = await membre(db, { utilisateur: "exploitant", role: "exploitation" });
    const chef = await membre(db, { utilisateur: "chef", role: "superadmin" });
    await membre(db, { utilisateur: "autre-chef", role: "superadmin" });
    await membre(db, { utilisateur: "lecteur", role: "lecture" });
    await membre(db, { utilisateur: "invite", role: "lecture", externe: true, perimetre: ["garage-essai"] });
    for (const qui of ["exploitant", "chef", "autre-chef", "lecteur", "invite"]) await ouvrirSession(`s-${qui}`, qui);
    const essais: [typeof chef, string][] = [[exploitant, "lecteur"], [exploitant, "invite"], [exploitant, "chef"], [exploitant, "exploitant"],
      [chef, "autre-chef"], [chef, "chef"]];
    for (const [a, cible] of essais) {
      for (const geste of [() => suspendre(db, a, cible, { motif: "Abus" }), () => reactiver(db, a, cible, ad), () => deconnecter(db, a, cible, ad)]) {
        const e = await refusAsync(geste);
        expect([e.statut, e.message], `${a.utilisateur} sur ${cible}`).toEqual([403, TA.suspensionInterdite]);
      }
      expect(await etatCompte(cible), cible).toEqual({ banni: 0, motif: null, sessions: 1 });
    }
    expect(appels).toEqual([]);
  });

  it("le compte d'un membre, par un superadmin : permis", async () => {
    const chef = await membre(db, { utilisateur: "chef", role: "superadmin" });
    await membre(db, { utilisateur: "lecteur", role: "lecture" });
    await suspendre(db, chef, "lecteur", { motif: "Départ" });
    expect(await etatCompte("lecteur")).toEqual({ banni: 1, motif: "Départ", sessions: 0 });
  });

  it("sans comptes.gerer : 403", async () => {
    const lecteur = await membre(db, { utilisateur: "lecteur", role: "lecture" });
    expect((await refusAsync(() => suspendre(db, lecteur, "c", { motif: "Abus" }))).statut).toBe(403);
    expect(await peutAgirSur(db, lecteur, "c")).toBe(false);
    expect(await etatCompte("c")).toEqual({ banni: 0, motif: null, sessions: 2 });
  });

  it("peutAgirSur suit la même règle que les gestes (l'écran ne montre pas un geste refusé)", async () => {
    const exploitant = await membre(db, { utilisateur: "exploitant", role: "exploitation" });
    await membre(db, { utilisateur: "lecteur", role: "lecture" });
    await membre(db, { utilisateur: "parti", role: "lecture", finAcces: "2026-11-18" });
    expect(await peutAgirSur(db, exploitant, "c")).toBe(true);
    expect(await peutAgirSur(db, exploitant, "lecteur")).toBe(false);
    expect(await peutAgirSur(db, exploitant, "exploitant")).toBe(false);
    // Une fin d'accès passée : ce n'est plus un membre, son compte est un compte ordinaire.
    expect(await peutAgirSur(db, exploitant, "parti", new Date("2026-11-19T10:00:00Z"))).toBe(true);
  });

  it("le bannissement et l'effacement des sessions vont ensemble : un échec n'en laisse aucun", async () => {
    const a = await membre(db, { utilisateur: "exploitant", role: "exploitation" });
    await db.executer("ALTER TABLE session RENAME TO session_cachee"); // l'effacement des sessions échouera, après le bannissement
    await expect(suspendre(db, a, "c", { motif: "Abus" })).rejects.toThrow();
    await db.executer("ALTER TABLE session_cachee RENAME TO session");
    expect(await etatCompte("c")).toEqual({ banni: 0, motif: null, sessions: 2 });
  });

  it("réactiver : le bannissement levé ; déconnecter : seulement ses sessions", async () => {
    const a = await membre(db, { utilisateur: "exploitant", role: "exploitation" });
    await reactiver(db, a, "c", ad);
    await deconnecter(db, a, "c", ad);
    expect(appels).toEqual([
      ["updateUser", "c", { banned: false, banReason: null, banExpires: null }],
      ["deleteUserSessions", "c"],
    ]);
  });
});

describe("avec le vrai Better Auth", () => {
  it("un compte suspendu perd ses sessions, ne se reconnecte plus et lit T.compteSuspendu ; réactivé, il revient", async () => {
    const auth = betterAuth({ ...optionsAuth(db, { CONSOLE_INSCRIPTION: "ouverte" }), secret: SECRET });
    const inscrit = await auth.api.signUpEmail({ body: { name: "Fleuriste", email: "fleurs@exemple.test", password: "motdepasse" }, returnHeaders: true });
    const user = inscrit.response.user;
    const cookie = new Headers({ cookie: (inscrit.headers.get("set-cookie") ?? "").split(";")[0] });
    const reel = (await auth.$context).internalAdapter;
    const chef = await membre(db, { utilisateur: "chef", role: "superadmin" });
    expect((await auth.api.getSession({ headers: cookie }))?.user.id).toBe(user.id);

    await suspendre(db, chef, user.id, { motif: "Abus" });
    expect(await db.un('SELECT CASE WHEN banned THEN 1 ELSE 0 END AS banned, "banReason" FROM "user" WHERE id = ?', user.id)).toEqual({ banned: 1, banReason: "Abus" });
    expect(await db.un("SELECT COUNT(*) AS n FROM session WHERE \"userId\" = ?", user.id)).toEqual({ n: 0 });
    expect(await auth.api.getSession({ headers: cookie })).toBeNull(); // son cookie ne vaut plus rien, dès la requête suivante
    const refus = await auth.api.signInEmail({ body: { email: "fleurs@exemple.test", password: "motdepasse" } }).catch((e: unknown) => e);
    expect(refus).toMatchObject({ body: { code: "BANNED_USER", message: T.compteSuspendu } });
    expect((await tous(db, T0)).find((c) => c.id === user.id)).toMatchObject({ suspendu: true, motif: "Abus" });

    await reactiver(db, chef, user.id, reel);
    const r = await auth.api.signInEmail({ body: { email: "fleurs@exemple.test", password: "motdepasse" } });
    expect(r.token).toBeTruthy();
    expect((await tous(db, T0)).find((c) => c.id === user.id)).toMatchObject({ suspendu: false, motif: null });
  });

  it("les migrations ajoutent les colonnes de l'extension à une base qui existait avant elle, sans rien perdre", async () => {
    const ancienne = await baseVide(moteurParDefaut());
    const sansExtension = { ...optionsAuth(ancienne), plugins: [], disabledPaths: [] };
    await (await getMigrations(sansExtension)).runMigrations();
    await preparer(ancienne);
    await compte(ancienne, { id: "ancien", courriel: "ancien@exemple.test", nom: "Ancien" });
    expect(await colonnes(ancienne, "user")).not.toContain("banned");
    await (await getMigrations(optionsAuth(ancienne))).runMigrations();
    expect(await colonnes(ancienne, "user")).toEqual(expect.arrayContaining(["banned", "banReason", "banExpires", "role"]));
    expect(await tous(ancienne, T0)).toMatchObject([{ id: "ancien", entreprise: "Ancien", suspendu: false, motif: null }]);
  });
});

describe("la liste des comptes", () => {
  it("entreprise, courriel, inscription, dernière connexion, agents, messages des 30 derniers jours, état, membre", async () => {
    await compte(db, { id: "d", courriel: "fleurs@exemple.test", nom: "Fleurs", creeLe: avant(1).toISOString() });
    await membre(db, { utilisateur: "chef", role: "superadmin" });
    await db.ecrire("UPDATE \"user\" SET \"createdAt\" = ? WHERE id = 'chef'", avant(5).toISOString());
    await db.ecrire("UPDATE \"user\" SET banned = ?, \"banReason\" = 'Abus' WHERE id = 'd'", true);
    const a1 = await creer(db, "c", { prenom: "Lou", metier: "garage" }, T0);
    const a2 = await creer(db, "c", { prenom: "Max", metier: "garage" }, T0);
    await compterTour(db, a1.id, avant(31)); // hors des 30 jours
    await compterTour(db, a1.id, avant(29));
    await compterTour(db, a1.id, T0);
    await compterTour(db, a2.id, T0);
    await noterConnexion(db, "c", T0);
    expect(await tous(db, T0)).toEqual([
      { id: "c", entreprise: "Garage du Lac", courriel: "garage@exemple.test", inscritLe: T0.toISOString(), derniereConnexion: T0.toISOString(),
        agents: 2, messages30j: 3, suspendu: false, motif: null, membre: false },
      { id: "d", entreprise: "Fleurs", courriel: "fleurs@exemple.test", inscritLe: avant(1).toISOString(), derniereConnexion: null,
        agents: 0, messages30j: 0, suspendu: true, motif: "Abus", membre: false },
      { id: "chef", entreprise: "CHEF", courriel: "chef@megga.test", inscritLe: avant(5).toISOString(), derniereConnexion: null,
        agents: 0, messages30j: 0, suspendu: false, motif: null, membre: true },
    ]);
  });

  it("un membre dont l'accès a pris fin n'est plus marqué membre", async () => {
    await membre(db, { utilisateur: "parti", role: "lecture", finAcces: "2026-11-18" });
    expect((await tous(db, T0)).find((c) => c.id === "parti")?.membre).toBe(true);
    expect((await tous(db, new Date("2026-11-19T10:00:00Z"))).find((c) => c.id === "parti")?.membre).toBe(false);
  });
});

describe("les pages et la recherche", () => {
  async function inscrire(n: number) {
    for (let i = 0; i < n; i++) {
      const quand = new Date(T0.getTime() - (i + 1) * 60_000).toISOString();
      await compte(db, { id: `n${i}`, courriel: `client${i}@exemple.test`, nom: `Entreprise ${i}`, creeLe: quand });
    }
  }

  it("par pages de 50, l'inscription la plus récente d'abord ; une page trop loin ramène à la dernière", async () => {
    await inscrire(120); // et « c », inscrit à T0
    const p1 = await listerComptes(db, { page: 1 }, T0);
    expect([p1.pages, p1.page, p1.comptes.length, p1.comptes[0].id, p1.comptes[1].id]).toEqual([3, 1, 50, "c", "n0"]);
    const p3 = await listerComptes(db, { page: 3 }, T0);
    expect([p3.page, p3.comptes.length, p3.comptes.at(-1)?.id]).toEqual([3, 21, "n119"]);
    expect(await listerComptes(db, { page: 99 }, T0)).toMatchObject({ page: 3, pages: 3 });
    expect(COMPTES_PAR_PAGE).toBe(50);
  });

  it("cherche dans l'entreprise ou le courriel, sans tenir compte de la casse ; les pages comptent ce qui correspond", async () => {
    await inscrire(60);
    expect((await listerComptes(db, { q: "LAC", page: 1 }, T0)).comptes.map((c) => c.id)).toEqual(["c"]);
    expect((await listerComptes(db, { q: "garage@exemple", page: 1 }, T0)).comptes.map((c) => c.id)).toEqual(["c"]);
    const cinq = await listerComptes(db, { q: "Entreprise 5", page: 1 }, T0);
    expect([cinq.pages, cinq.comptes.map((c) => c.id)]).toEqual([1, ["n5", "n50", "n51", "n52", "n53", "n54", "n55", "n56", "n57", "n58", "n59"]]);
    expect(await listerComptes(db, { q: "rien de tel", page: 4 }, T0)).toEqual({ comptes: [], pages: 1, page: 1 });
  });

  it("la recherche ignore la casse", async () => {
    await compte(db, { id: "alice", courriel: "alice@megga.test", nom: "Atelier" });
    expect((await listerComptes(db, { q: "ALICE", page: 1 }, T0)).comptes.map((c) => c.id)).toEqual(["alice"]);
    expect((await listerComptes(db, { q: "aTeLiEr", page: 1 }, T0)).comptes.map((c) => c.id)).toEqual(["alice"]);
  });

  it("prend % et _ à la lettre", async () => {
    await compte(db, { id: "pourcent", courriel: "p@exemple.test", nom: "Remise 100% garage" });
    await compte(db, { id: "souligne", courriel: "s_x@exemple.test", nom: "Souligné" });
    expect((await listerComptes(db, { q: "%", page: 1 }, T0)).comptes.map((c) => c.id)).toEqual(["pourcent"]);
    expect((await listerComptes(db, { q: "_", page: 1 }, T0)).comptes.map((c) => c.id)).toEqual(["souligne"]);
    expect((await listerComptes(db, { q: "\\", page: 1 }, T0)).comptes).toEqual([]);
  });

  it("les filtres tels que l'adresse les donne : une page mal formée retombe sur 1, une recherche vide n'en est pas une", async () => {
    expect(filtresComptesDe({})).toEqual({ page: 1 });
    expect(filtresComptesDe({ page: "2", q: "  lac  " })).toEqual({ page: 2, q: "lac" });
    for (const page of ["0", "-1", "abc", "1.5", "99999999999999999999"]) expect(filtresComptesDe({ page }), page).toEqual({ page: 1 });
    expect(filtresComptesDe({ q: "   " })).toEqual({ page: 1 });
    expect(filtresComptesDe({ q: ["lac", "autre"], page: ["2"] })).toEqual({ page: 2, q: "lac" });
    expect(filtresComptesDe({ q: "x".repeat(300) }).q).toHaveLength(100);
  });
});

describe("la fiche d'un compte", () => {
  it("ses agents et leurs messages, ses sessions ouvertes ; jamais une adresse IP", async () => {
    const a1 = await creer(db, "c", { prenom: "Lou", metier: "garage", couleur: 2 }, T0);
    await compterTour(db, a1.id, T0);
    await compterTour(db, a1.id, avant(40));
    const session = (...v: (string | null)[]) => db.ecrire(
      'INSERT INTO session (id, "expiresAt", token, "createdAt", "updatedAt", "ipAddress", "userAgent", "userId") VALUES (?, ?, ?, ?, ?, ?, ?, ?)', ...v);
    await session("s1", "2026-11-25T10:00:00.000Z", "t1", T0.toISOString(), T0.toISOString(), "203.0.113.42", "Mozilla/5.0 Essai", "c");
    await session("s2", "2026-11-17T10:00:00.000Z", "t2", avant(8).toISOString(), avant(8).toISOString(), "203.0.113.43", null, "c"); // expirée
    const f = (await ficheCompte(db, "c", T0))!;
    expect(f.compte).toMatchObject({ id: "c", entreprise: "Garage du Lac", agents: 1, messages30j: 1 });
    expect(f.agents).toEqual([{ ...a1, messages30j: 1 }]);
    expect(f.sessions).toEqual([{ creeLe: T0.toISOString(), expireLe: "2026-11-25T10:00:00.000Z", appareil: "Mozilla/5.0 Essai" }]);
    expect(JSON.stringify(f)).not.toMatch(/203\.0\.113|ipAddress|token/);
  });

  it("un compte inconnu : rien", async () => {
    expect(await ficheCompte(db, "personne", T0)).toBeUndefined();
  });
});

describe("les totaux de la console", () => {
  it("comptes et agents en tout ; messages et inscriptions jour par jour sur la période", async () => {
    await compte(db, { id: "d", courriel: "d@exemple.test", creeLe: avant(2).toISOString() });
    await compte(db, { id: "e", courriel: "e@exemple.test", creeLe: avant(10).toISOString() });
    const a = await creer(db, "c", { prenom: "Lou", metier: "garage" }, T0);
    await creer(db, "d", { prenom: "Max", metier: "sante" }, T0);
    await compterTour(db, a.id, T0);
    await compterTour(db, a.id, T0);
    await compterTour(db, a.id, avant(2));
    await compterTour(db, a.id, avant(9));
    const t = await totauxConsole(db, 7, T0);
    expect([t.comptes, t.agents, t.messages]).toEqual([3, 2, 3]);
    expect(t.parJour).toHaveLength(7);
    expect(t.parJour[0]).toEqual({ jour: "2026-11-12", inscriptions: 0, messages: 0 });
    expect(t.parJour[4]).toEqual({ jour: "2026-11-16", inscriptions: 1, messages: 1 });
    expect(t.parJour[6]).toEqual({ jour: "2026-11-18", inscriptions: 1, messages: 2 });
    expect((await totauxConsole(db, 30, T0)).messages).toBe(4);
  });

  it("les inscriptions par jour de Zurich : 0 h 30 compte dans le jour affiché, 23 h 59 la veille non", async () => {
    await compte(db, { id: "minuit", courriel: "m@exemple.test", creeLe: "2026-11-11T23:30:00.000Z" }); // le 12 à 0 h 30, à Zurich
    await compte(db, { id: "veille", courriel: "v@exemple.test", creeLe: "2026-11-11T22:59:00.000Z" }); // le 11 à 23 h 59
    await compte(db, { id: "soir", courriel: "s@exemple.test", creeLe: "2026-11-18T23:30:00.000Z" }); // déjà le 19 à Zurich
    const t = await totauxConsole(db, 7, T0);
    expect(t.parJour[0]).toEqual({ jour: "2026-11-12", inscriptions: 1, messages: 0 });
    expect(t.parJour.reduce((n, j) => n + j.inscriptions, 0)).toBe(2); // « minuit » et « c » (T0) ; ni la veille, ni demain
    expect(t.comptes).toBe(4); // en tout
    expect((await totauxConsole(db, 1, new Date("2026-11-18T23:45:00Z"))).parJour).toEqual([{ jour: "2026-11-19", inscriptions: 1, messages: 0 }]);
  });
});

describe("le dernier superadmin", () => {
  it("un superadmin suspendu ne compte pas : le dernier qui peut se connecter ne part pas", async () => {
    const chef = await membre(db, { utilisateur: "chef", role: "superadmin" });
    await membre(db, { utilisateur: "lecteur", role: "lecture" });
    await db.ecrire("UPDATE \"user\" SET banned = ? WHERE id = 'lecteur'", true);
    // modifierMembre refuse de nommer superadmin un compte suspendu (equipe.test.ts) : une ligne d'avant, écrite à la main.
    await db.ecrire("UPDATE admin_membre SET role = 'superadmin' WHERE utilisateur = 'lecteur'");
    const e = await refusAsync(() => retirerMembre(db, chef, "chef", T0));
    expect([e.statut, e.message]).toEqual([409, TA.dernierSuperadmin]);
    // Le superadmin suspendu, lui, peut perdre ce rôle : il en reste un qui se connecte.
    await modifierMembre(db, chef, "lecteur", { role: "lecture" }, T0);
  });
});
