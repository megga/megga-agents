import { beforeEach, describe, expect, it, vi } from "vitest";
import { DELETE } from "@/app/api/admin/alertes/destinations/[id]/route";
import { POST as ESSAI } from "@/app/api/admin/alertes/destinations/[id]/essai/route";
import { POST } from "@/app/api/admin/alertes/destinations/route";
import { PUT } from "@/app/api/admin/alertes/regles/route";
import { peutReglerAlertes, voitReglesAlertes } from "@/lib/admin/acces";
import { lireJournal } from "@/lib/admin/journal";
import type { Base } from "@/lib/donnees/base";
import { acces, baseEssai, membre } from "./aides";

// Les alertes envoyées (20.11.2026) : les règles et les destinations valent pour tous les clients ; elles se règlent avec
// alertes.regler sur un périmètre complet, et le journal ne garde jamais l'adresse d'une destination (un secret).

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

const faux = vi.hoisted(() => ({ reglerAlertes: vi.fn(), ajouterDestination: vi.fn(), retirerDestination: vi.fn(), essayerDestination: vi.fn() }));
vi.mock("@/lib/admin/atelier", async (original) => {
  const vrai = await original<typeof import("@/lib/admin/atelier")>();
  return { ...vrai, atelier: { ...vrai.atelier, ...faux } };
});

const SLACK = "https://hooks.slack.com/services/T000/B000/secretsecret";
const REGLES = [{ id: "echecs", nom: "Tours en échec", mesure: "taux_echec", comparaison: ">", alerte: 10, destinations: ["slack"] }];

const requete = (qui: string, methode: string, chemin: string, corps?: unknown) =>
  new Request(`http://localhost/api/admin/alertes${chemin}`, {
    method: methode,
    headers: { origin: "http://localhost", "x-essai-qui": qui },
    body: corps === undefined ? undefined : JSON.stringify(corps),
  });
const sans = { params: Promise.resolve({}) };
const avec = (id: string) => ({ params: Promise.resolve({ id }) });
const journal = async () => (await lireJournal(etat.db, acces({ superadmin: true }), { page: 1 })).lignes;

beforeEach(async () => {
  for (const f of Object.values(faux)) f.mockReset();
  etat.db = await baseEssai();
  await membre(etat.db, { utilisateur: "exploitation", role: "exploitation" });
  await membre(etat.db, { utilisateur: "limite", role: "exploitation", perimetre: ["garage-essai"] });
  await membre(etat.db, { utilisateur: "lecture", role: "lecture" });
});

describe("régler les alertes envoyées", () => {
  it("les règles partent telles quelles ; le journal garde l'identifiant et la mesure", async () => {
    faux.reglerAlertes.mockResolvedValue({ regles: REGLES });
    const r = await PUT(requete("exploitation", "PUT", "/regles", REGLES), sans);
    expect([r.status, await r.json()]).toEqual([200, { regles: REGLES }]);
    expect(faux.reglerAlertes.mock.calls).toEqual([[REGLES]]);
    expect((await journal())[0]).toMatchObject({ action: "alertes.regles", resultat: "ok", detail: [{ id: "echecs", mesure: "taux_echec" }] });
  });

  it("refusé à un périmètre limité ou sans le droit, rien ne part à l'atelier", async () => {
    expect((await PUT(requete("limite", "PUT", "/regles", REGLES), sans)).status).toBe(403);
    expect((await PUT(requete("lecture", "PUT", "/regles", REGLES), sans)).status).toBe(403);
    expect((await POST(requete("limite", "POST", "/destinations", { id: "slack", genre: "slack", adresse: SLACK }), sans)).status).toBe(403);
    expect((await DELETE(requete("limite", "DELETE", "/destinations/slack"), avec("slack"))).status).toBe(403);
    expect((await ESSAI(requete("limite", "POST", "/destinations/slack/essai"), avec("slack"))).status).toBe(403);
    expect(Object.values(faux).every((f) => f.mock.calls.length === 0)).toBe(true);
    expect((await PUT(requete("exploitation", "PUT", "/regles", { pas: "une liste" }), sans)).status).toBe(400);
  });

  it("une destination : l'adresse part à l'atelier, jamais au journal ; la clé d'une adresse web revient une fois", async () => {
    faux.ajouterDestination.mockResolvedValue({ id: "web", genre: "web", adresse: "https://alertes.example.com/…cret", secret: "cle-de-signature" });
    const r = await POST(requete("exploitation", "POST", "/destinations", { id: "web", genre: "web", adresse: "https://alertes.example.com/secret", autre: 1 }), sans);
    expect([r.status, (await r.json()).secret]).toEqual([200, "cle-de-signature"]);
    expect(faux.ajouterDestination.mock.calls).toEqual([[{ id: "web", genre: "web", adresse: "https://alertes.example.com/secret" }]]);
    faux.ajouterDestination.mockResolvedValue({ id: "slack", genre: "slack", adresse: "https://hooks.slack.com/…cret" });
    await POST(requete("exploitation", "POST", "/destinations", { id: "slack", genre: "slack", adresse: SLACK }), sans);
    const lignes = JSON.stringify(await journal());
    expect(lignes).not.toContain("secret");
    expect((await journal()).map((l) => l.detail)).toContainEqual({ id: "slack", genre: "slack" });
  });

  it("retirer et essayer une destination : son identifiant seulement", async () => {
    faux.retirerDestination.mockResolvedValue({ retiree: "slack" });
    faux.essayerDestination.mockResolvedValue({ envoye: true });
    expect((await DELETE(requete("exploitation", "DELETE", "/destinations/slack"), avec("slack"))).status).toBe(200);
    expect((await ESSAI(requete("exploitation", "POST", "/destinations/slack/essai"), avec("slack"))).status).toBe(200);
    expect((await DELETE(requete("exploitation", "DELETE", "/destinations/A%20B"), avec("A B"))).status).toBe(404);
    expect([faux.retirerDestination.mock.calls, faux.essayerDestination.mock.calls]).toEqual([[["slack"]], [["slack"]]]);
  });

  it("lire et régler les règles demandent un périmètre complet", () => {
    expect(voitReglesAlertes(acces({ droits: ["clients.voir"] }))).toBe(true);
    expect(voitReglesAlertes(acces({ droits: ["clients.voir"], perimetre: ["garage-essai"] }))).toBe(false);
    expect(peutReglerAlertes(acces({ droits: ["alertes.regler"] }))).toBe(true);
    expect(peutReglerAlertes(acces({ droits: ["alertes.regler"], perimetre: ["garage-essai"] }))).toBe(false);
    expect(peutReglerAlertes(acces({ droits: ["clients.voir"] }))).toBe(false);
  });
});
