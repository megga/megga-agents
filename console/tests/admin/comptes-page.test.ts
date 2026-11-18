import type { DatabaseSync } from "node:sqlite";
import { cloneElement, createElement, isValidElement, type ReactElement, type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { GestesCompte } from "@/app/admin/(espace)/comptes/[id]/compte";
import PageCompte from "@/app/admin/(espace)/comptes/[id]/page";
import PageComptes from "@/app/admin/(espace)/comptes/page";
import VueEnsemble from "@/app/admin/(espace)/page";
import { Barres } from "@/components/admin/barres";
import { creerRole } from "@/lib/admin/roles";
import { TA } from "@/lib/admin/textes";
import { compterTour } from "@/lib/admin/usage";
import { creer } from "@/lib/agents";
import { acces, baseEssai, compte, membre } from "./aides";

// L'écran Comptes, la fiche d'un compte et le bloc Console de la vue d'ensemble, appelés comme Next.js les rend (session, base
// et atelier simulés, un lien est un simple <a>), puis dessinés en HTML. Sans comptes.voir, ni courriel de client ni total ;
// les gestes seulement là où la bibliothèque les laissera passer.

const etat = vi.hoisted(() => ({ db: undefined as unknown as DatabaseSync, qui: null as string | null, appels: [] as string[] }));
vi.mock("next/server", async (original) => ({ ...(await original<typeof import("next/server")>()), connection: async () => {} }));
vi.mock("@/lib/base", async (original) => ({ ...(await original<typeof import("@/lib/base")>()), base: () => etat.db }));
vi.mock("@/lib/auth", async (original) => ({
  ...(await original<typeof import("@/lib/auth")>()),
  session: async () => (etat.qui ? { user: { id: etat.qui, email: `${etat.qui}@megga.test`, name: etat.qui } } : null),
}));
vi.mock("next/navigation", () => ({
  redirect: (url: string) => {
    throw new Error(`redirect:${url}`);
  },
  notFound: () => {
    throw new Error("404");
  },
  useRouter: () => ({ refresh: () => {} }),
}));
vi.mock("next/link", async () => {
  const { createElement } = await import("react");
  return { default: (p: { href: string; className?: string; children?: ReactNode }) => createElement("a", { href: p.href, className: p.className }, p.children) };
});
vi.mock("@/lib/admin/atelier", async (original) => {
  const vrai = await original<typeof import("@/lib/admin/atelier")>();
  return { ...vrai, atelier: { ...vrai.atelier, clients: async () => (etat.appels.push("clients"), { clients: [], porte: true }) } };
});

/** Les composants async du serveur se rendent d'abord ; le reste se dessine en HTML. */
async function resoudre(n: unknown): Promise<unknown> {
  if (Array.isArray(n)) return Promise.all(n.map(resoudre));
  if (!isValidElement(n)) return n;
  const el = n as ReactElement<{ children?: unknown }>;
  if (typeof el.type === "function" && el.type.constructor.name === "AsyncFunction") {
    return resoudre(await (el.type as (p: unknown) => Promise<unknown>)(el.props));
  }
  return el.props.children === undefined ? el : cloneElement(el, { children: await resoudre(el.props.children) } as never);
}
const html = async (n: unknown) => renderToStaticMarkup((await resoudre(n)) as ReactNode);
const enHtml = (t: string) => t.replaceAll("'", "&#x27;");

function elements(n: unknown, type: unknown): ReactElement<Record<string, unknown>>[] {
  if (Array.isArray(n)) return n.flatMap((x) => elements(x, type));
  if (!isValidElement(n)) return [];
  const el = n as ReactElement<Record<string, unknown>>;
  return [...(el.type === type ? [el] : []), ...Object.values(el.props).flatMap((v) => elements(v, type))];
}

/** La valeur d'une tuile, d'après son titre. */
const tuile = (h: string, titre: string) => new RegExp(`>${titre}</span><b[^>]*>([^<]*)</b>`).exec(h)?.[1];

const liste = () => PageComptes();
const fiche = (id: string) => PageCompte({ params: Promise.resolve({ id }) } as never);
const vue = () => VueEnsemble({ searchParams: Promise.resolve({ jours: "7" }) } as never);

beforeEach(async () => {
  etat.db = await baseEssai();
  etat.appels = [];
  const s = acces({ superadmin: true });
  const clientsSeuls = creerRole(etat.db, s, { nom: "Clients seuls", droits: ["clients.voir"] });
  const comptesSeuls = creerRole(etat.db, s, { nom: "Comptes seuls", droits: ["comptes.voir"] });
  membre(etat.db, { utilisateur: "exploitant", role: "exploitation" });
  membre(etat.db, { utilisateur: "lecteur", role: "lecture" });
  membre(etat.db, { utilisateur: "chef", role: "superadmin" });
  membre(etat.db, { utilisateur: "suiveur", role: clientsSeuls.id });
  membre(etat.db, { utilisateur: "compteur", role: comptesSeuls.id });
  membre(etat.db, { utilisateur: "invite", role: "administration", externe: true, perimetre: ["garage-essai"] });
  compte(etat.db, { id: "c", courriel: "garage@exemple.test", nom: "Garage du Lac" });
  const a = creer(etat.db, "c", { prenom: "Lou", metier: "garage" });
  compterTour(etat.db, a.id);
  compterTour(etat.db, a.id);
  etat.db.prepare("INSERT INTO session (id, expiresAt, token, createdAt, updatedAt, ipAddress, userAgent, userId) VALUES (?, ?, ?, ?, ?, ?, ?, ?)")
    .run("s1", new Date(Date.now() + 86_400_000).toISOString(), "jeton-de-session", new Date().toISOString(), new Date().toISOString(),
      "203.0.113.42", "Mozilla/5.0 Essai", "c");
});

describe("l'écran Comptes", () => {
  it("avec comptes.voir : chaque compte, son courriel, ses agents, ses messages sur 30 jours, son état, membre ou non", async () => {
    etat.qui = "lecteur";
    const h = await html(await liste());
    expect(h).toContain("Garage du Lac");
    expect(h).toContain("garage@exemple.test");
    expect(h).toContain('href="/admin/comptes/c"');
    expect(h).toContain(TA.actif);
    expect(h).toContain(enHtml(TA.membreAdmin));
    expect(h).not.toContain("203.0.113.42");
  });

  it("un externe, ou un membre sans comptes.voir : 404", async () => {
    for (const qui of ["invite", "suiveur"]) {
      etat.qui = qui;
      await expect(liste(), qui).rejects.toThrow("404");
      await expect(fiche("c"), qui).rejects.toThrow("404");
    }
  });
});

describe("la fiche d'un compte", () => {
  it("ses agents, ses sessions, sans adresse IP ni jeton ; un compte inconnu : 404", async () => {
    etat.qui = "lecteur";
    const h = await html(await fiche("c"));
    expect(h).toContain("Lou");
    expect(h).toContain("Mozilla/5.0 Essai");
    expect(h).not.toMatch(/203\.0\.113|jeton-de-session/);
    await expect(fiche("personne")).rejects.toThrow("404");
  });

  it("les gestes seulement avec comptes.gerer et la main sur ce compte (peutAgirSur)", async () => {
    etat.qui = "lecteur";
    expect(elements(await fiche("c"), GestesCompte)).toEqual([]);
    etat.qui = "exploitant";
    expect(elements(await fiche("c"), GestesCompte)[0].props).toEqual({ id: "c", nom: "Garage du Lac", suspendu: false, sessions: 1 });
    expect(elements(await fiche("lecteur"), GestesCompte)).toEqual([]); // un membre, sans être superadmin
    expect(elements(await fiche("exploitant"), GestesCompte)).toEqual([]); // le sien
    etat.qui = "chef";
    expect(elements(await fiche("lecteur"), GestesCompte)).toHaveLength(1);
    expect(elements(await fiche("chef"), GestesCompte)).toEqual([]);
  });

  it("un compte suspendu : son état et son motif ; réactiver plutôt que suspendre", async () => {
    etat.db.prepare("UPDATE \"user\" SET banned = 1, banReason = 'Abus' WHERE id = 'c'").run();
    etat.qui = "exploitant";
    const arbre = await fiche("c");
    expect(elements(arbre, GestesCompte)[0].props).toMatchObject({ suspendu: true });
    const h = await html(arbre);
    expect(h).toContain(TA.suspendu);
    expect(h).toContain(TA.motifSuspension("Abus"));
  });
});

describe("le bloc Console de la vue d'ensemble", () => {
  it("avec comptes.voir : comptes, agents, messages de la période, inscriptions et messages par jour", async () => {
    etat.qui = "lecteur";
    const arbre = await vue();
    const h = await html(arbre);
    expect(tuile(h, TA.comptes)).toBe("7");
    expect(tuile(h, TA.agents)).toBe("1");
    expect(tuile(h, TA.messages)).toBe("2");
    // Deux cadres de barres (inscriptions, messages), sept jours chacun ; aujourd'hui, deux messages.
    expect(h).toContain(`>${TA.inscriptions}</span>`);
    expect(h.match(/<li title=/g)).toHaveLength(14);
    expect(h).toContain(enHtml(TA.barre(TA.jour(new Date().toISOString().slice(0, 10)), 2)));
  });

  it("comptes.voir sans clients.voir : la période et le bloc Console, sans lire l'atelier", async () => {
    etat.qui = "compteur";
    const h = await html(await vue());
    expect(tuile(h, TA.comptes)).toBe("7");
    expect(h).toContain(`aria-label="${TA.periode}"`);
    expect(etat.appels).toEqual([]);
  });

  it("sans comptes.voir (un externe, un membre limité aux clients) : ni tuile, ni total, ni barres", async () => {
    for (const qui of ["suiveur", "invite"]) {
      etat.qui = qui;
      const arbre = await vue();
      const h = await html(arbre);
      expect(tuile(h, TA.comptes), qui).toBeUndefined();
      expect(tuile(h, TA.agents), qui).toBeUndefined();
      expect(h, qui).not.toContain(`>${TA.console}<`);
      expect(h, qui).not.toContain(TA.inscriptions);
      expect(h, qui).not.toMatch(/<li title=/);
    }
  });
});

describe("les barres", () => {
  it("une barre par jour et par légende, à l'échelle de sa légende, le nombre exact lisible", () => {
    const h = renderToStaticMarkup(createElement(Barres, {
      jours: [{ jour: "2026-11-17", valeurs: [0, 4] }, { jour: "2026-11-18", valeurs: [2, 8] }],
      legendes: ["Inscriptions", "Messages"],
    }));
    expect(h).toContain("Inscriptions");
    expect(h).toContain(enHtml(TA.barre(TA.jour("2026-11-18"), 8)));
    expect(h).toContain("height:100%");
    expect(h).toContain("height:50%");
    expect(h).not.toMatch(/#[0-9a-f]{3,8}\b|rgb/i);
  });
});
