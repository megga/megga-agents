import type { DatabaseSync } from "node:sqlite";
import { isValidElement, type ReactElement, type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { GestesInstallation } from "@/app/admin/(espace)/clients/[id]/installation/installation";
import PageInstallation from "@/app/admin/(espace)/clients/[id]/installation/page";
import { Clients } from "@/app/admin/(espace)/clients/clients";
import PageClients from "@/app/admin/(espace)/clients/page";
import PageInstallations from "@/app/admin/(espace)/installations/page";
import { RefusChamps } from "@/lib/admin/atelier";
import { TA } from "@/lib/admin/textes";
import { dbEssai, membre } from "./aides";

// Les écrans des installations et le nouveau client, appelés comme Next.js les rend (session, base et atelier simulés, un lien
// est un simple <a>) : le périmètre borne la liste, les gestes suivent installations.gerer, « Nouveau client » suit
// peutCreerClient.

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

const BREF = { cle: "263dfa8b264b31a1", enregistree: 1_800_000_000, revoquee: null, releve: 1_800_000_100, silencieuse: false, pilotage: "complet",
  accord: true, mises_a_jour: false, agent: { ok: true, version: "0.2.0", licence: { etat: "valide", jusqu_au: "2027-12-31" } },
  configuration: { source: "pilotage", version: 2 }, ecart: false };
const simule = vi.hoisted(() => ({ appels: [] as string[], installations: {} as unknown, installation: {} as unknown, gabarits: null as unknown }));
vi.mock("@/lib/admin/atelier", async (original) => {
  const vrai = await original<typeof import("@/lib/admin/atelier")>();
  const noter = (quoi: string) => simule.appels.push(quoi);
  const repondre = (r: unknown) => {
    if (r instanceof Error) throw r;
    return r;
  };
  return {
    ...vrai,
    atelier: {
      ...vrai.atelier,
      clients: async () => (noter("clients"), { clients: [{ id: "chalet-essai", nom_agent: "Noé", entreprise: "Chalet des Essais", version_en_service: 2,
        derniere_version: 2, gere_par_megga: false, installation: BREF }], porte: true }),
      installations: async () => (noter("installations"), repondre(simule.installations)),
      installation: async (id: string) => (noter(`installation ${id}`), repondre(simule.installation)),
      gabarits: async () => (noter("gabarits"), repondre(simule.gabarits ?? { gabarits: [{ id: "generaliste", titre: "Généraliste", description: "",
        metier: "general", reglages: {} }] })),
      catalogue: async () => (noter("catalogue"), { metiers: {}, champs_client: [], zones: ["suisse", "europe", "client"], zones_porte: ["europe"], modeles: [] }),
    },
  };
});

const html = (n: unknown) => renderToStaticMarkup(n as ReactNode);
const enHtml = (t: string) => t.replaceAll("'", "&#x27;");
const onglet = (id = "chalet-essai") => PageInstallation({ params: Promise.resolve({ id }) } as never);

function elements(n: unknown, type: unknown): ReactElement<Record<string, unknown>>[] {
  if (Array.isArray(n)) return n.flatMap((x) => elements(x, type));
  if (!isValidElement(n)) return [];
  const el = n as ReactElement<Record<string, unknown>>;
  return [...(el.type === type ? [el] : []), ...Object.values(el.props).flatMap((v) => elements(v, type))];
}

beforeEach(async () => {
  etat.db = await dbEssai();
  simule.appels = [];
  simule.gabarits = null;
  simule.installations = { installations: [{ client: "chalet-essai", ...BREF }], cle_pilotage: true };
  simule.installation = { client: "chalet-essai", version_en_service: 2, installation: BREF,
    ordres: [{ numero: 2, genre: "config", version: 2, etat: "applique", detail: "", cree: 1_800_000_000, expire: 1_800_600_000, maj: 1_800_000_100 }],
    journal: [{ quand: 1_800_000_100, numero: 2, evenement: "applique", detail: "selon l'installation" }] };
  membre(etat.db, { utilisateur: "chef", role: "superadmin" });
  membre(etat.db, { utilisateur: "limite", role: "administration", perimetre: ["garage-essai"] });
  membre(etat.db, { utilisateur: "lecteur", role: "lecture" });
  etat.qui = "chef";
});

describe("l'écran Installations", () => {
  it("les installations du périmètre, chacune liée à son onglet ; hors périmètre, aucune", async () => {
    const h = html(await PageInstallations());
    expect(h).toContain('href="/admin/clients/chalet-essai/installation"');
    expect(h).toContain("Chalet des Essais");
    expect(h).toContain(TA.modesPilotage.complet);
    expect(h).not.toContain(enHtml(TA.sansClePilotage));
    etat.qui = "limite";
    const limite = html(await PageInstallations());
    expect(limite).not.toContain("chalet-essai");
    expect(limite).toContain(TA.videInstallations);
  });

  it("sans clé de pilotage, un bandeau le dit", async () => {
    simule.installations = { installations: [], cle_pilotage: false };
    expect(html(await PageInstallations())).toContain(enHtml(TA.sansClePilotage));
  });
});

describe("l'onglet Installation", () => {
  it("le dernier relevé, les ordres et le journal du pilotage ; les gestes avec installations.gerer", async () => {
    const arbre = await onglet();
    const h = html(arbre);
    for (const t of [TA.agentRepond("0.2.0"), TA.versionNumero(2), TA.etatsPilotage.applique, "263dfa8b264b31a1", TA.licenceJusqua("Valide", "31.12.2027")]) {
      expect(h, t).toContain(enHtml(t));
    }
    expect(elements(arbre, GestesInstallation).map((e) => e.props)).toEqual([{ id: "chalet-essai", revocable: true }]);
  });

  it("une clé révoquée ne se révoque plus ; en lecture (clients.voir seul), aucun geste", async () => {
    simule.installation = { ...(simule.installation as object), installation: { ...BREF, revoquee: 1_800_000_200 } };
    expect(elements(await onglet(), GestesInstallation)[0].props.revocable).toBe(false);
    etat.qui = "lecteur";
    expect(elements(await onglet(), GestesInstallation)).toEqual([]);
  });

  it("un client servi par la porte : la phrase de l'atelier ; hors du périmètre : 404 sans appel", async () => {
    const phrase = "ce client est servi par la porte de Cloudflare : il n'a pas d'installation à piloter";
    simule.installation = new RefusChamps(409, phrase);
    expect(html(await onglet("boulangerie-essai"))).toContain(enHtml(phrase));
    simule.appels = [];
    etat.qui = "limite";
    await expect(onglet()).rejects.toThrow("404");
    expect(simule.appels).toEqual([]);
  });
});

describe("le nouveau client", () => {
  it("proposé à qui peut créer (clients.creer et tous les clients), avec les modèles et les zones", async () => {
    expect(elements(await PageClients(), Clients)[0].props.creation).toEqual({ gabarits: [{ id: "generaliste", titre: "Généraliste" }],
      zones: ["suisse", "europe", "client"], avertissement: null });
  });

  it("les modèles illisibles : toujours proposé, la configuration collée seule, avec l'avertissement qui dit pourquoi", async () => {
    simule.gabarits = new RefusChamps(502, TA.atelierInjoignable);
    expect(elements(await PageClients(), Clients)[0].props.creation).toEqual({ gabarits: [], zones: [], avertissement: TA.modelesIllisibles });
  });

  it("un membre limité à une liste, ou sans clients.creer : ni le formulaire, ni les modèles lus", async () => {
    for (const qui of ["limite", "lecteur"]) {
      etat.qui = qui;
      simule.appels = [];
      const arbre = await PageClients();
      expect(elements(arbre, Clients)[0].props.creation, qui).toBeNull();
      expect(html(arbre)).not.toContain(TA.nouveauClient);
      expect(simule.appels).toEqual(["clients"]);
    }
  });
});
