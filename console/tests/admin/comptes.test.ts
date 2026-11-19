import type { DatabaseSync } from "node:sqlite";
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
import { baseSqlite } from "@/lib/donnees/sqlite";
import { T } from "@/lib/textes";
import { baseDe, dbEssai, compte, membre, refusAsync, T0 } from "./aides";

// Les comptes de la console et leur suspension : la liste, la fiche, les totaux de la vue d'ensemble ; suspendre, réactiver,
// déconnecter partout, par l'adaptateur interne de Better Auth (ses routes HTTP de l'extension admin restent fermées).

const JOUR = 24 * 3600 * 1000;
const avant = (jours: number) => new Date(T0.getTime() - jours * JOUR);

let db: DatabaseSync;
let b: Base;
let appels: unknown[][];
let ad: AdaptateurComptes;

beforeEach(async () => {
  db = await dbEssai();
  b = baseDe(db);
  appels = [];
  ad = {
    updateUser: vi.fn(async (...a: unknown[]) => appels.push(["updateUser", ...a])),
    deleteUserSessions: vi.fn(async (...a: unknown[]) => appels.push(["deleteUserSessions", ...a])),
  };
  compte(db, { id: "c", courriel: "garage@exemple.test", nom: "Garage du Lac" });
});

const SECRET = "secret-des-essais-de-la-console-assez-long";

/** La première page des comptes, sans recherche. */
const tous = (d: DatabaseSync, maintenant: Date) => listerComptes(d, { page: 1 }, maintenant).comptes;

describe("les routes HTTP de l'extension admin de Better Auth", () => {
  it("sont toutes les quinze fermées", () => {
    expect(CHEMINS_ADMIN_FERMES).toHaveLength(15);
    for (const c of ["/admin/ban-user", "/admin/impersonate-user", "/admin/set-role", "/admin/create-user", "/admin/unban-user", "/admin/list-users"]) {
      expect(CHEMINS_ADMIN_FERMES).toContain(c);
    }
    expect(optionsAuth(b).disabledPaths).toEqual(CHEMINS_ADMIN_FERMES);
  });

  it("ne répondent à personne, même à un superadmin qui serait aussi « admin » pour Better Auth", async () => {
    const appeler = async (auth: { handler: (r: Request) => Promise<Response> }, chemin: string, corps: unknown, cookie = "") =>
      auth.handler(new Request(`http://localhost:3000/api/auth${chemin}`, {
        method: "POST",
        headers: { "content-type": "application/json", origin: "http://localhost:3000", cookie },
        body: JSON.stringify(corps),
      }));
    const ouverte = betterAuth({ ...optionsAuth(b), disabledPaths: [], secret: SECRET, baseURL: "http://localhost:3000" });
    const fermee = betterAuth({ ...optionsAuth(b), secret: SECRET, baseURL: "http://localhost:3000" });
    const inscrit = await appeler(fermee, "/sign-up/email", { name: "Chef", email: "chef@megga.test", password: "motdepasse" });
    const chef = ((await inscrit.json()) as { user: { id: string } }).user.id;
    db.prepare("UPDATE \"user\" SET role = 'admin' WHERE id = ?").run(chef);
    membre(db, { utilisateur: chef, role: "superadmin" });
    const cookie = (inscrit.headers.get("set-cookie") ?? "").split(";")[0];

    const r = await appeler(fermee, "/admin/ban-user", { userId: "c", banReason: "essai" }, cookie);
    expect(r.status).toBe(404);
    expect((await appeler(fermee, "/admin/set-role", { userId: "c", role: "admin" }, cookie)).status).toBe(404);
    expect(db.prepare('SELECT banned, role FROM "user" WHERE id = ?').get("c")).toEqual({ banned: null, role: null });
    // Témoin : la même requête passe sans disabledPaths. C'est bien la fermeture qui refuse.
    expect((await appeler(ouverte, "/admin/ban-user", { userId: "c", banReason: "essai" }, cookie)).status).toBe(200);
  });
});

describe("suspendre un compte", () => {
  it("un membre avec comptes.gerer suspend un compte ordinaire : le bannissement, puis ses sessions effacées", async () => {
    const a = membre(db, { utilisateur: "exploitant", role: "exploitation" });
    await suspendre(db, a, "c", { motif: "  Abus  " }, ad);
    expect(appels).toEqual([
      ["updateUser", "c", { banned: true, banReason: "Abus", banExpires: null }],
      ["deleteUserSessions", "c"],
    ]);
  });

  it("sans motif, ou un motif de plus de 200 caractères : 400, rien n'est écrit", async () => {
    const a = membre(db, { utilisateur: "exploitant", role: "exploitation" });
    for (const corps of [{ motif: "" }, { motif: "   " }, { motif: "x".repeat(201) }, {}, { motif: 3 }, null]) {
      const e = await refusAsync(() => suspendre(db, a, "c", corps, ad));
      expect([e.statut, e.message], JSON.stringify(corps)).toEqual([400, TA.motifManquant]);
    }
    await suspendre(db, a, "c", { motif: "é".repeat(200) }, ad);
    expect(appels).toHaveLength(2);
  });

  it("un compte inconnu : 404", async () => {
    const a = membre(db, { utilisateur: "exploitant", role: "exploitation" });
    const e = await refusAsync(() => suspendre(db, a, "personne", { motif: "Abus" }, ad));
    expect([e.statut, e.message]).toEqual([404, TA.compteInconnu]);
    expect(appels).toEqual([]);
  });

  it("le compte d'un membre sans être superadmin, celui d'un superadmin, le sien : 403, rien n'est écrit", async () => {
    const exploitant = membre(db, { utilisateur: "exploitant", role: "exploitation" });
    const chef = membre(db, { utilisateur: "chef", role: "superadmin" });
    membre(db, { utilisateur: "autre-chef", role: "superadmin" });
    membre(db, { utilisateur: "lecteur", role: "lecture" });
    membre(db, { utilisateur: "invite", role: "lecture", externe: true, perimetre: ["garage-essai"] });
    const essais: [typeof chef, string][] = [[exploitant, "lecteur"], [exploitant, "invite"], [exploitant, "chef"], [exploitant, "exploitant"],
      [chef, "autre-chef"], [chef, "chef"]];
    for (const [a, cible] of essais) {
      for (const geste of [() => suspendre(db, a, cible, { motif: "Abus" }, ad), () => reactiver(db, a, cible, ad), () => deconnecter(db, a, cible, ad)]) {
        const e = await refusAsync(geste);
        expect([e.statut, e.message], `${a.utilisateur} sur ${cible}`).toEqual([403, TA.suspensionInterdite]);
      }
    }
    expect(appels).toEqual([]);
  });

  it("le compte d'un membre, par un superadmin : permis", async () => {
    const chef = membre(db, { utilisateur: "chef", role: "superadmin" });
    membre(db, { utilisateur: "lecteur", role: "lecture" });
    await suspendre(db, chef, "lecteur", { motif: "Départ" }, ad);
    expect(appels[0]).toEqual(["updateUser", "lecteur", { banned: true, banReason: "Départ", banExpires: null }]);
  });

  it("sans comptes.gerer : 403", async () => {
    const lecteur = membre(db, { utilisateur: "lecteur", role: "lecture" });
    expect((await refusAsync(() => suspendre(db, lecteur, "c", { motif: "Abus" }, ad))).statut).toBe(403);
    expect(peutAgirSur(db, lecteur, "c")).toBe(false);
  });

  it("peutAgirSur suit la même règle que les gestes (l'écran ne montre pas un geste refusé)", () => {
    const exploitant = membre(db, { utilisateur: "exploitant", role: "exploitation" });
    membre(db, { utilisateur: "lecteur", role: "lecture" });
    membre(db, { utilisateur: "parti", role: "lecture", finAcces: "2026-11-18" });
    expect(peutAgirSur(db, exploitant, "c")).toBe(true);
    expect(peutAgirSur(db, exploitant, "lecteur")).toBe(false);
    expect(peutAgirSur(db, exploitant, "exploitant")).toBe(false);
    // Une fin d'accès passée : ce n'est plus un membre, son compte est un compte ordinaire.
    expect(peutAgirSur(db, exploitant, "parti", new Date("2026-11-19T10:00:00Z"))).toBe(true);
  });

  it("des sessions qui ne s'effacent pas : un second essai ; s'il échoue aussi, le compte reste suspendu et le geste le dit, sans refus", async () => {
    const a = membre(db, { utilisateur: "exploitant", role: "exploitation" });
    let echecs = 1;
    const fragile: AdaptateurComptes = {
      updateUser: async (...x: unknown[]) => appels.push(["updateUser", ...x]),
      deleteUserSessions: async (...x: unknown[]) => {
        appels.push(["deleteUserSessions", ...x]);
        if (echecs-- > 0) throw new Error("base occupée");
      },
    };
    const erreur = vi.spyOn(console, "error").mockImplementation(() => {});
    // Un échec, puis réussi au second essai.
    expect(await suspendre(db, a, "c", { motif: "Abus" }, fragile)).toEqual({ sessionsRestent: false });
    expect(appels.map((x) => x[0])).toEqual(["updateUser", "deleteUserSessions", "deleteUserSessions"]);
    appels = [];
    echecs = 2;
    // Deux échecs : le bannissement est écrit, le geste le dit (ce n'est pas un refus).
    expect(await suspendre(db, a, "c", { motif: "Abus" }, fragile)).toEqual({ sessionsRestent: true });
    expect(appels).toEqual([
      ["updateUser", "c", { banned: true, banReason: "Abus", banExpires: null }],
      ["deleteUserSessions", "c"],
      ["deleteUserSessions", "c"],
    ]);
    expect(erreur).toHaveBeenCalled();
    erreur.mockRestore();
  });

  it("une écriture du bannissement en échec reste une erreur, et rien n'est effacé", async () => {
    const a = membre(db, { utilisateur: "exploitant", role: "exploitation" });
    const panne: AdaptateurComptes = {
      updateUser: async () => {
        throw new Error("base fermée");
      },
      deleteUserSessions: async (...x: unknown[]) => appels.push(["deleteUserSessions", ...x]),
    };
    await expect(suspendre(db, a, "c", { motif: "Abus" }, panne)).rejects.toThrow("base fermée");
    expect(appels).toEqual([]);
  });

  it("réactiver : le bannissement levé ; déconnecter : seulement ses sessions", async () => {
    const a = membre(db, { utilisateur: "exploitant", role: "exploitation" });
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
    const auth = betterAuth({ ...optionsAuth(b), secret: SECRET });
    const inscrit = await auth.api.signUpEmail({ body: { name: "Fleuriste", email: "fleurs@exemple.test", password: "motdepasse" }, returnHeaders: true });
    const user = inscrit.response.user;
    const cookie = new Headers({ cookie: (inscrit.headers.get("set-cookie") ?? "").split(";")[0] });
    const reel = (await auth.$context).internalAdapter;
    const chef = membre(db, { utilisateur: "chef", role: "superadmin" });
    expect((await auth.api.getSession({ headers: cookie }))?.user.id).toBe(user.id);

    await suspendre(db, chef, user.id, { motif: "Abus" }, reel);
    expect(db.prepare('SELECT banned, banReason FROM "user" WHERE id = ?').get(user.id)).toEqual({ banned: 1, banReason: "Abus" });
    expect(db.prepare("SELECT COUNT(*) AS n FROM session WHERE userId = ?").get(user.id)).toEqual({ n: 0 });
    expect(await auth.api.getSession({ headers: cookie })).toBeNull(); // son cookie ne vaut plus rien, dès la requête suivante
    const refus = await auth.api.signInEmail({ body: { email: "fleurs@exemple.test", password: "motdepasse" } }).catch((e: unknown) => e);
    expect(refus).toMatchObject({ body: { code: "BANNED_USER", message: T.compteSuspendu } });
    expect(tous(db, T0).find((c) => c.id === user.id)).toMatchObject({ suspendu: true, motif: "Abus" });

    await reactiver(db, chef, user.id, reel);
    const r = await auth.api.signInEmail({ body: { email: "fleurs@exemple.test", password: "motdepasse" } });
    expect(r.token).toBeTruthy();
    expect(tous(db, T0).find((c) => c.id === user.id)).toMatchObject({ suspendu: false, motif: null });
  });

  it("les migrations ajoutent les colonnes de l'extension à une base qui existait avant elle, sans rien perdre", async () => {
    const ancienneBase = baseSqlite(":memory:");
    const ancienne = ancienneBase.pourAuth() as DatabaseSync;
    const sansExtension = { ...optionsAuth(ancienneBase), plugins: [], disabledPaths: [] };
    await (await getMigrations(sansExtension)).runMigrations();
    await preparer(ancienneBase);
    compte(ancienne, { id: "ancien", courriel: "ancien@exemple.test", nom: "Ancien" });
    const colonnes = () => (ancienne.prepare('PRAGMA table_info("user")').all() as { name: string }[]).map((c) => c.name);
    expect(colonnes()).not.toContain("banned");
    await (await getMigrations(optionsAuth(ancienneBase))).runMigrations();
    expect(colonnes()).toEqual(expect.arrayContaining(["banned", "banReason", "banExpires", "role"]));
    expect(tous(ancienne, T0)).toMatchObject([{ id: "ancien", entreprise: "Ancien", suspendu: false, motif: null }]);
  });
});

describe("la liste des comptes", () => {
  it("entreprise, courriel, inscription, dernière connexion, agents, messages des 30 derniers jours, état, membre", async () => {
    compte(db, { id: "d", courriel: "fleurs@exemple.test", nom: "Fleurs", creeLe: avant(1).toISOString() });
    membre(db, { utilisateur: "chef", role: "superadmin" });
    db.prepare("UPDATE \"user\" SET createdAt = ? WHERE id = 'chef'").run(avant(5).toISOString());
    db.prepare("UPDATE \"user\" SET banned = 1, banReason = 'Abus' WHERE id = 'd'").run();
    const a1 = await creer(b, "c", { prenom: "Lou", metier: "garage" }, T0);
    const a2 = await creer(b, "c", { prenom: "Max", metier: "garage" }, T0);
    await compterTour(b, a1.id, avant(31)); // hors des 30 jours
    await compterTour(b, a1.id, avant(29));
    await compterTour(b, a1.id, T0);
    await compterTour(b, a2.id, T0);
    await noterConnexion(b, "c", T0);
    expect(tous(db, T0)).toEqual([
      { id: "c", entreprise: "Garage du Lac", courriel: "garage@exemple.test", inscritLe: T0.toISOString(), derniereConnexion: T0.toISOString(),
        agents: 2, messages30j: 3, suspendu: false, motif: null, membre: false },
      { id: "d", entreprise: "Fleurs", courriel: "fleurs@exemple.test", inscritLe: avant(1).toISOString(), derniereConnexion: null,
        agents: 0, messages30j: 0, suspendu: true, motif: "Abus", membre: false },
      { id: "chef", entreprise: "CHEF", courriel: "chef@megga.test", inscritLe: avant(5).toISOString(), derniereConnexion: null,
        agents: 0, messages30j: 0, suspendu: false, motif: null, membre: true },
    ]);
  });

  it("un membre dont l'accès a pris fin n'est plus marqué membre", () => {
    membre(db, { utilisateur: "parti", role: "lecture", finAcces: "2026-11-18" });
    expect(tous(db, T0).find((c) => c.id === "parti")?.membre).toBe(true);
    expect(tous(db, new Date("2026-11-19T10:00:00Z")).find((c) => c.id === "parti")?.membre).toBe(false);
  });
});

describe("les pages et la recherche", () => {
  function inscrire(n: number) {
    for (let i = 0; i < n; i++) {
      const quand = new Date(T0.getTime() - (i + 1) * 60_000).toISOString();
      compte(db, { id: `n${i}`, courriel: `client${i}@exemple.test`, nom: `Entreprise ${i}`, creeLe: quand });
    }
  }

  it("par pages de 50, l'inscription la plus récente d'abord ; une page trop loin ramène à la dernière", () => {
    inscrire(120); // et « c », inscrit à T0
    const p1 = listerComptes(db, { page: 1 }, T0);
    expect([p1.pages, p1.page, p1.comptes.length, p1.comptes[0].id, p1.comptes[1].id]).toEqual([3, 1, 50, "c", "n0"]);
    const p3 = listerComptes(db, { page: 3 }, T0);
    expect([p3.page, p3.comptes.length, p3.comptes.at(-1)?.id]).toEqual([3, 21, "n119"]);
    expect(listerComptes(db, { page: 99 }, T0)).toMatchObject({ page: 3, pages: 3 });
    expect(COMPTES_PAR_PAGE).toBe(50);
  });

  it("cherche dans l'entreprise ou le courriel, sans tenir compte de la casse ; les pages comptent ce qui correspond", () => {
    inscrire(60);
    expect(listerComptes(db, { q: "LAC", page: 1 }, T0).comptes.map((c) => c.id)).toEqual(["c"]);
    expect(listerComptes(db, { q: "garage@exemple", page: 1 }, T0).comptes.map((c) => c.id)).toEqual(["c"]);
    const cinq = listerComptes(db, { q: "Entreprise 5", page: 1 }, T0);
    expect([cinq.pages, cinq.comptes.map((c) => c.id)]).toEqual([1, ["n5", "n50", "n51", "n52", "n53", "n54", "n55", "n56", "n57", "n58", "n59"]]);
    expect(listerComptes(db, { q: "rien de tel", page: 4 }, T0)).toEqual({ comptes: [], pages: 1, page: 1 });
  });

  it("prend % et _ à la lettre", () => {
    compte(db, { id: "pourcent", courriel: "p@exemple.test", nom: "Remise 100% garage" });
    compte(db, { id: "souligne", courriel: "s_x@exemple.test", nom: "Souligné" });
    expect(listerComptes(db, { q: "%", page: 1 }, T0).comptes.map((c) => c.id)).toEqual(["pourcent"]);
    expect(listerComptes(db, { q: "_", page: 1 }, T0).comptes.map((c) => c.id)).toEqual(["souligne"]);
    expect(listerComptes(db, { q: "\\", page: 1 }, T0).comptes).toEqual([]);
  });

  it("les filtres tels que l'adresse les donne : une page mal formée retombe sur 1, une recherche vide n'en est pas une", () => {
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
    const a1 = await creer(b, "c", { prenom: "Lou", metier: "garage", couleur: 2 }, T0);
    await compterTour(b, a1.id, T0);
    await compterTour(b, a1.id, avant(40));
    const session = (...v: (string | null)[]) => b.ecrire(
      'INSERT INTO session (id, "expiresAt", token, "createdAt", "updatedAt", "ipAddress", "userAgent", "userId") VALUES (?, ?, ?, ?, ?, ?, ?, ?)', ...v);
    await session("s1", "2026-11-25T10:00:00.000Z", "t1", T0.toISOString(), T0.toISOString(), "203.0.113.42", "Mozilla/5.0 Essai", "c");
    await session("s2", "2026-11-17T10:00:00.000Z", "t2", avant(8).toISOString(), avant(8).toISOString(), "203.0.113.43", null, "c"); // expirée
    const f = (await ficheCompte(b, "c", T0))!;
    expect(f.compte).toMatchObject({ id: "c", entreprise: "Garage du Lac", agents: 1, messages30j: 1 });
    expect(f.agents).toEqual([{ ...a1, messages30j: 1 }]);
    expect(f.sessions).toEqual([{ creeLe: T0.toISOString(), expireLe: "2026-11-25T10:00:00.000Z", appareil: "Mozilla/5.0 Essai" }]);
    expect(JSON.stringify(f)).not.toMatch(/203\.0\.113|ipAddress|token/);
  });

  it("un compte inconnu : rien", async () => {
    expect(await ficheCompte(b, "personne", T0)).toBeUndefined();
  });
});

describe("les totaux de la console", () => {
  it("comptes et agents en tout ; messages et inscriptions jour par jour sur la période", async () => {
    compte(db, { id: "d", courriel: "d@exemple.test", creeLe: avant(2).toISOString() });
    compte(db, { id: "e", courriel: "e@exemple.test", creeLe: avant(10).toISOString() });
    const a = await creer(b, "c", { prenom: "Lou", metier: "garage" }, T0);
    await creer(b, "d", { prenom: "Max", metier: "sante" }, T0);
    await compterTour(b, a.id, T0);
    await compterTour(b, a.id, T0);
    await compterTour(b, a.id, avant(2));
    await compterTour(b, a.id, avant(9));
    const t = await totauxConsole(b, 7, T0);
    expect([t.comptes, t.agents, t.messages]).toEqual([3, 2, 3]);
    expect(t.parJour).toHaveLength(7);
    expect(t.parJour[0]).toEqual({ jour: "2026-11-12", inscriptions: 0, messages: 0 });
    expect(t.parJour[4]).toEqual({ jour: "2026-11-16", inscriptions: 1, messages: 1 });
    expect(t.parJour[6]).toEqual({ jour: "2026-11-18", inscriptions: 1, messages: 2 });
    expect((await totauxConsole(b, 30, T0)).messages).toBe(4);
  });

  it("les inscriptions par jour de Zurich : 0 h 30 compte dans le jour affiché, 23 h 59 la veille non", async () => {
    compte(db, { id: "minuit", courriel: "m@exemple.test", creeLe: "2026-11-11T23:30:00.000Z" }); // le 12 à 0 h 30, à Zurich
    compte(db, { id: "veille", courriel: "v@exemple.test", creeLe: "2026-11-11T22:59:00.000Z" }); // le 11 à 23 h 59
    compte(db, { id: "soir", courriel: "s@exemple.test", creeLe: "2026-11-18T23:30:00.000Z" }); // déjà le 19 à Zurich
    const t = await totauxConsole(b, 7, T0);
    expect(t.parJour[0]).toEqual({ jour: "2026-11-12", inscriptions: 1, messages: 0 });
    expect(t.parJour.reduce((n, j) => n + j.inscriptions, 0)).toBe(2); // « minuit » et « c » (T0) ; ni la veille, ni demain
    expect(t.comptes).toBe(4); // en tout
    expect((await totauxConsole(b, 1, new Date("2026-11-18T23:45:00Z"))).parJour).toEqual([{ jour: "2026-11-19", inscriptions: 1, messages: 0 }]);
  });
});

describe("le dernier superadmin", () => {
  it("un superadmin suspendu ne compte pas : le dernier qui peut se connecter ne part pas", async () => {
    const chef = membre(db, { utilisateur: "chef", role: "superadmin" });
    membre(db, { utilisateur: "lecteur", role: "lecture" });
    db.prepare("UPDATE \"user\" SET banned = 1 WHERE id = 'lecteur'").run();
    // modifierMembre refuse de nommer superadmin un compte suspendu (equipe.test.ts) : une ligne d'avant, écrite à la main.
    db.prepare("UPDATE admin_membre SET role = 'superadmin' WHERE utilisateur = 'lecteur'").run();
    const e = await refusAsync(async () => retirerMembre(db, chef, "chef", T0));
    expect([e.statut, e.message]).toEqual([409, TA.dernierSuperadmin]);
    // Le superadmin suspendu, lui, peut perdre ce rôle : il en reste un qui se connecte.
    modifierMembre(db, chef, "lecteur", { role: "lecture" }, T0);
  });
});
