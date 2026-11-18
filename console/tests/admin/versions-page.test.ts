import type { DatabaseSync } from "node:sqlite";
import { isValidElement, type ReactElement, type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import PageVersions from "@/app/admin/(espace)/clients/[id]/versions/page";
import { gesteDe, Preparer } from "@/app/admin/(espace)/clients/[id]/versions/versions";
import { TA } from "@/lib/admin/textes";
import { baseEssai, membre } from "./aides";

// L'onglet Versions, appelé comme Next.js le rend, sans réseau (session, base et atelier simulés, un lien est un simple <a>),
// puis dessiné en HTML. Un externe n'y voit ni modèle par métier ni geste de pilotage ; chaque geste dit son effet.

const etat = vi.hoisted(() => ({ db: undefined as unknown as DatabaseSync, qui: null as string | null }));
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
  useRouter: () => ({ refresh: () => {}, push: () => {} }),
}));
vi.mock("next/link", async () => {
  const { createElement } = await import("react");
  return { default: (p: { href: string; className?: string; children?: ReactNode }) => createElement("a", { href: p.href, className: p.className }, p.children) };
});

const CONFIG = { id: "garage-essai", zone: "europe", ton: "posé", metier: "general", outils: [], consignes: "Sur mesure" };
const VERSIONS = [
  { version: 4, etat: "brouillon", auteur: "client", base: 3, essais: 0, cree_le: 1_800_000_300 },
  { version: 3, etat: "brouillon", auteur: "megga", base: 2, essais: 2, cree_le: 1_800_000_200 },
  { version: 2, etat: "publiee", auteur: "megga", base: 1, essais: 1, cree_le: 1_800_000_100 },
  { version: 1, etat: "publiee", auteur: "megga", base: null, essais: 0, cree_le: 1_800_000_000 },
];
const CATALOGUE = { metiers: { general: [] }, champs_client: ["metier", "nom_agent", "voix", "ton", "outils"], zones: ["europe", "client"],
  zones_porte: ["europe"], modeles: [] };
const GABARITS = { gabarits: [{ id: "immobilier", titre: "Immobilier", description: "Une agence.", metier: "immobilier", reglages: {} }] };

const simule = vi.hoisted(() => ({ appels: [] as string[], config: {} as Record<string, unknown>, surClient: {} as Record<string, unknown> }));
vi.mock("@/lib/admin/atelier", async (original) => {
  const vrai = await original<typeof import("@/lib/admin/atelier")>();
  const noter = (quoi: string) => simule.appels.push(quoi);
  return {
    ...vrai,
    atelier: {
      ...vrai.atelier,
      client: async (id: string) => (noter(`client ${id}`), { id, nom_agent: "Max", entreprise: "Garage", version_en_service: 2, derniere_version: 4,
        gere_par_megga: false, ecart: false, config: simule.config, ...simule.surClient }),
      versions: async (id: string) => (noter(`versions ${id}`), { versions: VERSIONS }),
      version: async (id: string, n: number) => (noter(`version ${id} ${n}`), { ...VERSIONS.find((v) => v.version === n),
        config: { ...simule.config, ton: `ton ${n}` } }),
      catalogue: async () => (noter("catalogue"), CATALOGUE),
      gabarits: async () => (noter("gabarits"), GABARITS),
    },
  };
});

const page = (v?: string, id = "garage-essai") => PageVersions({ params: Promise.resolve({ id }), searchParams: Promise.resolve(v ? { v } : {}) } as never);
const html = (n: unknown) => renderToStaticMarkup(n as ReactNode);
const enHtml = (t: string) => t.replaceAll("'", "&#x27;");

/** Les éléments d'un type dans l'arbre rendu par une page, sans rien dessiner. */
function elements(n: unknown, type: unknown): ReactElement<Record<string, unknown>>[] {
  if (Array.isArray(n)) return n.flatMap((x) => elements(x, type));
  if (!isValidElement(n)) return [];
  const el = n as ReactElement<Record<string, unknown>>;
  return [...(el.type === type ? [el] : []), ...Object.values(el.props).flatMap((v) => elements(v, type))];
}

beforeEach(async () => {
  etat.db = await baseEssai();
  simule.appels = [];
  simule.config = CONFIG;
  simule.surClient = {};
  membre(etat.db, { utilisateur: "chef", role: "superadmin" });
  membre(etat.db, { utilisateur: "invite", role: "exploitation", externe: true, perimetre: ["garage-essai"] });
  membre(etat.db, { utilisateur: "lecteur", role: "lecture" });
  etat.qui = "chef";
});

describe("l'onglet Versions", () => {
  it("l'historique : chaque version ouvre ?v=, brouillon ou publiée, en service, préparée par MEGGA ou par le client", async () => {
    const h = html(await page());
    expect([...h.matchAll(/href="([^"]*\?v=\d+)"/g)].map((m) => m[1])).toEqual([4, 3, 2, 1].map((n) => `/admin/clients/garage-essai/versions?v=${n}`));
    expect(h).toContain(TA.parLeClient);
    expect(h).toContain(TA.brouillon);
    expect(h).toContain(TA.enService);
    expect(simule.appels).not.toContain("version garage-essai 3");
  });

  it("un superadmin : la version ouverte, son geste (forcer un brouillon jamais essayé), l'essai, ce qui change ; le modèle par métier", async () => {
    const arbre = await page("4");
    const h = html(arbre);
    expect(h).toContain(TA.forcer);
    expect(h).toContain(TA.essaiTitre(4));
    expect(h).toContain(enHtml(TA.essaiConsomme));
    expect(h).toContain(enHtml(TA.changeParRapport(2)));
    expect(h).toContain("ton 4");
    const [p] = elements(arbre, Preparer);
    expect(p.props).toMatchObject({ id: "garage-essai", externe: false, gabarits: [{ id: "immobilier", titre: "Immobilier", description: "Une agence." }],
      derniere: { numero: 4, config: { ...CONFIG, ton: "ton 4" } } });
  });

  it("un externe : il prépare et essaie, limité aux réglages simples ; ni modèle par métier, ni geste de pilotage", async () => {
    etat.qui = "invite";
    for (const v of ["4", "3", "1"]) {
      const arbre = await page(v);
      const h = html(arbre);
      for (const t of [TA.forcer, TA.mettreEnService, TA.revenirVersion, TA.dApresModele]) expect(h, `${v} ${t}`).not.toContain(enHtml(t));
      expect(h).toContain(TA.preparerBrouillon);
      expect(h).toContain(enHtml(TA.reglagesSimples("metier, nom_agent, voix, ton, outils")));
      expect(elements(arbre, Preparer)[0].props).toMatchObject({ externe: true, gabarits: [] });
    }
    expect(simule.appels).not.toContain("gabarits");
    expect(html(await page("4"))).toContain(TA.essaiTitre(4));
  });

  it("en lecture (clients.voir seul) : l'historique et la configuration, rien à préparer, essayer ni mettre en service", async () => {
    etat.qui = "lecteur";
    const h = html(await page("4"));
    expect(h).toContain(TA.laConfiguration);
    for (const t of [TA.preparerBrouillon, TA.essaiTitre(4), TA.forcer, TA.mettreEnService]) expect(h, t).not.toContain(enHtml(t));
  });

  it("un numéro de version mal formé n'ouvre rien ; un client hors du périmètre : 404, sans appel à l'atelier", async () => {
    for (const v of ["abc", "0", "1.5"]) expect(html(await page(v))).not.toContain(enHtml(TA.changeParRapport(2)));
    expect(simule.appels.filter((x) => x.startsWith("version ") && !x.endsWith(" 4"))).toEqual([]);
    simule.appels = [];
    etat.qui = "invite";
    await expect(page(undefined, "boulangerie-essai")).rejects.toThrow("404");
    expect(simule.appels).toEqual([]);
  });

  it("un client jamais mis en service : ses brouillons, rien à comparer", async () => {
    simule.surClient = { version_en_service: null, config: null };
    const h = html(await page("4"));
    expect(h).toContain(enHtml(TA.aucuneEnService));
    expect(h).toContain(TA.forcer);
    expect(h).not.toContain(TA.enService);
  });
});

describe("le geste de pilotage d'une version", () => {
  const v = (numero: number, etat: "brouillon" | "publiee", essais: number) => ({ numero, etat, essais });

  it("forcer un brouillon jamais essayé ; mettre en service un brouillon essayé ; revenir à une publiée plus ancienne", () => {
    expect(gesteDe(v(4, "brouillon", 0), 2, false, false)).toEqual({ titre: TA.forcerTitre(4), bouton: TA.forcer,
      effet: `${TA.jamaisEssayee} ${TA.effetActiver(4)}`, forcer: true });
    expect(gesteDe(v(3, "brouillon", 2), 2, false, false)).toEqual({ titre: TA.mettreEnServiceTitre(3), bouton: TA.mettreEnService,
      effet: TA.effetActiver(3), forcer: false });
    expect(gesteDe(v(1, "publiee", 0), 2, false, false)).toEqual({ titre: TA.revenirTitre(1), bouton: TA.revenirVersion, effet: TA.effetActiver(1), forcer: false });
    expect(gesteDe(v(2, "brouillon", 3), null, false, false)?.titre).toBe(TA.mettreEnServiceTitre(2));
  });

  it("la version en service : rien, sauf un écart à relancer ; hors Cloudflare, l'effet dit l'ordre signé", () => {
    expect(gesteDe(v(2, "publiee", 1), 2, false, false)).toBeNull();
    expect(gesteDe(v(2, "publiee", 1), 2, true, false)).toEqual({ titre: TA.relancerTitre(2), bouton: TA.mettreEnService,
      effet: `${TA.ecartARelancer} ${TA.effetActiver(2)}`, forcer: false });
    expect(gesteDe(v(3, "brouillon", 1), 2, false, true)?.effet).toBe(TA.effetOrdre(3));
    expect(gesteDe(v(4, "brouillon", 0), 2, false, true)?.effet).toBe(`${TA.jamaisEssayee} ${TA.effetOrdre(4)}`);
  });
});
