import type { DatabaseSync } from "node:sqlite";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { POST as accepter } from "@/app/api/admin/invitation/route";
import { DELETE as retirerInvitation } from "@/app/api/admin/equipe/invitations/[id]/route";
import { POST as inviter } from "@/app/api/admin/equipe/invitations/route";
import { DELETE as retirerMembre, PATCH as modifierMembre } from "@/app/api/admin/equipe/membres/[id]/route";
import { DELETE as retirerRole, PATCH as modifierRole } from "@/app/api/admin/equipe/roles/[id]/route";
import { POST as creerRole } from "@/app/api/admin/equipe/roles/route";
import { invitationsEnAttente } from "@/lib/admin/invitations";
import { lireJournal } from "@/lib/admin/journal";
import { membreEnCours } from "@/lib/admin/membres";
import { lireRole, creerRole as creerRoleEnBase } from "@/lib/admin/roles";
import { TA } from "@/lib/admin/textes";
import { acces, baseEssai, compte, membre } from "./aides";

// Les routes de l'équipe et de l'invitation, appelées comme Next.js les appelle : la session vient de l'en-tête x-essai-qui,
// la base est celle de l'essai. La garde elle-même a ses essais (garde.test.ts) ; ici, ce que chaque route fait et note.

const etat = vi.hoisted(() => ({ db: undefined as unknown as DatabaseSync }));
vi.mock("@/lib/base", async (original) => ({ ...(await original<typeof import("@/lib/base")>()), base: () => etat.db }));
vi.mock("@/lib/auth", async (original) => ({
  ...(await original<typeof import("@/lib/auth")>()),
  sessionDe: async (r: Request) => {
    const qui = r.headers.get("x-essai-qui");
    return qui ? { user: { id: qui, email: r.headers.get("x-essai-courriel") ?? `${qui}@megga.test`, name: qui } } : null;
  },
}));

type Route<P> = (r: Request, ctx: { params: Promise<P> }) => Promise<Response>;

function appel<P>(f: Route<P>, methode: string, p: { qui: string; courriel?: string; corps?: unknown; params?: P }) {
  const headers: Record<string, string> = { origin: "http://localhost", "x-essai-qui": p.qui };
  if (p.courriel) headers["x-essai-courriel"] = p.courriel;
  const body = methode === "DELETE" ? undefined : JSON.stringify(p.corps ?? {});
  return f(new Request("http://localhost/api/admin/x", { method: methode, headers, body }), { params: Promise.resolve((p.params ?? {}) as P) });
}

const journal = () => lireJournal(etat.db, acces({ superadmin: true }), { page: 1 }).lignes;

beforeEach(async () => {
  etat.db = await baseEssai();
  membre(etat.db, { utilisateur: "s", role: "superadmin" });
});

/** m gère l'équipe avec deux droits ; petit n'en a qu'un, que m peut donner. */
function gestionnaire() {
  const s = acces({ utilisateur: "s", superadmin: true });
  const gestion = creerRoleEnBase(etat.db, s, { nom: "Gestion", droits: ["clients.voir", "equipe.gerer"] });
  const petit = creerRoleEnBase(etat.db, s, { nom: "Petit", droits: ["clients.voir"] });
  membre(etat.db, { utilisateur: "m", role: gestion.id });
  return { gestion, petit };
}

const chef = { courriel: "Chef@Megga.test ", role: "lecture", externe: false, perimetre: "tous", finAcces: null };

describe("les invitations, par la route", () => {
  it("un superadmin invite : 201, le lien rendu une fois, et le journal ne garde pas le jeton", async () => {
    const r = await appel(inviter, "POST", { qui: "s", corps: chef });
    expect(r.status).toBe(201);
    const { invitation, lien } = await r.json();
    expect(lien).toMatch(/^\/admin\/invitation\/[A-Za-z0-9_-]{43}$/);
    expect(invitation).toMatchObject({ courriel: "chef@megga.test", role: "lecture", creeePar: "s" });
    const jeton = lien.split("/").at(-1);
    const [ligne] = journal();
    expect(ligne).toMatchObject({ qui: "s", action: "invitations.creer", resultat: "ok", detail: { courriel: "Chef@Megga.test ", role: "lecture" } });
    expect(JSON.stringify(etat.db.prepare("SELECT * FROM admin_journal").all())).not.toContain(jeton);
  });

  it("m ne donne pas le rôle superadmin : 403, noté refusé", async () => {
    gestionnaire();
    const r = await appel(inviter, "POST", { qui: "m", corps: { ...chef, role: "superadmin" } });
    expect([r.status, await r.json()]).toEqual([403, { erreur: TA.escalade }]);
    expect(journal().map((l) => `${l.qui} ${l.action} ${l.resultat}`)).toEqual(["m invitations.creer refuse 403"]);
    expect(invitationsEnAttente(etat.db)).toEqual([]);
  });

  it("se retire : 204, notée sur sa cible", async () => {
    const { lien } = await (await appel(inviter, "POST", { qui: "s", corps: chef })).json();
    const [i] = invitationsEnAttente(etat.db);
    const r = await appel(retirerInvitation, "DELETE", { qui: "s", params: { id: i.id } });
    expect([r.status, await r.text()]).toEqual([204, ""]);
    expect(invitationsEnAttente(etat.db)).toEqual([]);
    expect(journal()[0]).toMatchObject({ action: "invitations.retirer", cible: `invitation:${i.id}`, resultat: "ok" });
    const encore = await appel(accepter, "POST", { qui: "c", courriel: "chef@megga.test", corps: { jeton: lien.split("/").at(-1) } });
    expect(encore.status).toBe(404);
  });

  it("s'accepte avec la session du courriel invité : 200, le membre créé, le jeton masqué au journal", async () => {
    const { lien } = await (await appel(inviter, "POST", { qui: "s", corps: chef })).json();
    const jeton = lien.split("/").at(-1);
    compte(etat.db, { id: "c", courriel: "chef@megga.test" });
    const autre = await appel(accepter, "POST", { qui: "x", courriel: "autre@megga.test", corps: { jeton } });
    expect([autre.status, await autre.json()]).toEqual([403, { erreur: TA.autreCourriel }]);
    const r = await appel(accepter, "POST", { qui: "c", courriel: "CHEF@megga.test", corps: { jeton } });
    expect(r.status).toBe(200);
    expect((await r.json()).membre).toMatchObject({ utilisateur: "c", courriel: "chef@megga.test", role: "lecture", ajoutePar: "s" });
    expect(membreEnCours(etat.db, "c")).toBeDefined();
    const ligne = journal().find((l) => l.action === "invitations.accepter" && l.resultat === "ok");
    expect(ligne).toMatchObject({ qui: "c", detail: { jeton: "[masqué]" } });
    expect(JSON.stringify(etat.db.prepare("SELECT * FROM admin_journal").all())).not.toContain(jeton);
    expect((await appel(accepter, "POST", { qui: "c", courriel: "chef@megga.test", corps: { jeton } })).status).toBe(404);
    expect((await appel(accepter, "POST", { qui: "c", courriel: "chef@megga.test", corps: {} })).status).toBe(404);
  });
});

describe("rejoindre, une route ouverte à tout compte", () => {
  it("ne note au journal que le jeton, masqué, jamais le reste du corps", async () => {
    const { lien } = await (await appel(inviter, "POST", { qui: "s", corps: chef })).json();
    const jeton = lien.split("/").at(-1);
    const r = await appel(accepter, "POST", { qui: "x", courriel: "x@megga.test", corps: { jeton, autre: "x".repeat(3000) } });
    expect(r.status).toBe(403);
    const ligne = journal().find((l) => l.action === "invitations.accepter")!;
    expect([ligne.qui, ligne.resultat, ligne.detail]).toEqual(["x", "refuse 403", { jeton: "[masqué]" }]);
    expect(JSON.stringify(etat.db.prepare("SELECT detail FROM admin_journal").all())).not.toMatch(/xxxx|autre/);
  });
});

describe("les membres, par la route", () => {
  it("se modifient et se retirent : { membre }, puis 204", async () => {
    membre(etat.db, { utilisateur: "n", role: "lecture" });
    const r = await appel(modifierMembre, "PATCH", { qui: "s", params: { id: "n" }, corps: { perimetre: ["garage-essai"], finAcces: "2026-12-31" } });
    expect(r.status).toBe(200);
    expect((await r.json()).membre).toMatchObject({ utilisateur: "n", perimetre: ["garage-essai"], finAcces: "2026-12-31" });
    const retrait = await appel(retirerMembre, "DELETE", { qui: "s", params: { id: "n" } });
    expect(retrait.status).toBe(204);
    expect(membreEnCours(etat.db, "n")).toBeUndefined();
    expect(journal().map((l) => `${l.action} ${l.cible} ${l.resultat}`)).toEqual(["membres.retirer membre:n ok", "membres.modifier membre:n ok"]);
  });

  it("m ne modifie pas sa propre ligne : 403", async () => {
    gestionnaire();
    const r = await appel(modifierMembre, "PATCH", { qui: "m", params: { id: "m" }, corps: { finAcces: "2026-12-31" } });
    expect([r.status, await r.json()]).toEqual([403, { erreur: TA.escalade }]);
    expect(journal()[0]).toMatchObject({ qui: "m", action: "membres.modifier", cible: "membre:m", resultat: "refuse 403" });
  });

  it("le seul superadmin ne se retire pas : 409", async () => {
    const r = await appel(retirerMembre, "DELETE", { qui: "s", params: { id: "s" } });
    expect([r.status, await r.json()]).toEqual([409, { erreur: TA.dernierSuperadmin }]);
    expect(membreEnCours(etat.db, "s")).toBeDefined();
  });
});

describe("les rôles, par la route", () => {
  it("un droit inconnu : 400", async () => {
    const r = await appel(creerRole, "POST", { qui: "s", corps: { nom: "Support", droits: ["clients.voir", "inconnu"] } });
    expect([r.status, await r.json()]).toEqual([400, { erreur: TA.droitInconnu }]);
    expect(journal()[0]).toMatchObject({ action: "roles.creer", resultat: "refuse 400" });
  });

  it("se créent (201), se modifient, se retirent (204)", async () => {
    const r = await appel(creerRole, "POST", { qui: "s", corps: { nom: "Support", description: "Aide.", droits: ["clients.voir"] } });
    expect(r.status).toBe(201);
    const { role } = await r.json();
    expect(role).toMatchObject({ nom: "Support", description: "Aide.", droits: ["clients.voir"], membres: 0 });
    const m = await appel(modifierRole, "PATCH", { qui: "s", params: { id: role.id }, corps: { droits: ["clients.voir", "journal.voir"] } });
    expect([m.status, (await m.json()).role.droits]).toEqual([200, ["clients.voir", "journal.voir"]]);
    const d = await appel(retirerRole, "DELETE", { qui: "s", params: { id: role.id } });
    expect(d.status).toBe(204);
    expect(lireRole(etat.db, role.id)).toBeUndefined();
    expect(journal().map((l) => `${l.action} ${l.cible ?? "-"} ${l.resultat}`))
      .toEqual([`roles.retirer role:${role.id} ok`, `roles.modifier role:${role.id} ok`, "roles.creer - ok"]);
  });

  it("le rôle superadmin ne se modifie pas ; un rôle porté ne se retire pas", async () => {
    const fixe = await appel(modifierRole, "PATCH", { qui: "s", params: { id: "superadmin" }, corps: { nom: "Chef" } });
    expect([fixe.status, await fixe.json()]).toEqual([403, { erreur: TA.roleFixe }]);
    membre(etat.db, { utilisateur: "l", role: "lecture" });
    const porte = await appel(retirerRole, "DELETE", { qui: "s", params: { id: "lecture" } });
    expect([porte.status, await porte.json()]).toEqual([409, { erreur: TA.rolePorte }]);
  });
});
