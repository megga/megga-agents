import { cloneElement, createElement, isValidElement, type ReactElement, type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import PageSuivi from "@/app/admin/(espace)/clients/[id]/page";
import VueEnsemble from "@/app/admin/(espace)/page";
import PageTarifs from "@/app/admin/(espace)/tarifs/page";
import { FormTarifs } from "@/app/admin/(espace)/tarifs/tarifs";
import type { Suivi, Tarifs } from "@/lib/admin/atelier";
import { creerRole } from "@/lib/admin/roles";
import { TA } from "@/lib/admin/textes";
import type { Base } from "@/lib/donnees/base";
import { acces, baseEssai, membre } from "./aides";

// Les coûts et les tarifs à l'écran, sans réseau : l'écran Tarifs, l'onglet Suivi et la vue d'ensemble, appelés comme Next.js
// les rend (session, base et atelier simulés, un lien est un simple <a>), puis dessinés en HTML. Ce qu'un membre sans
// couts.voir reçoit ne contient aucun coût, ni à l'écran ni dans les props d'un composant du navigateur.

const etat = vi.hoisted(() => ({ db: undefined as unknown as Base, qui: null as string | null }));
vi.mock("next/server", async (original) => ({ ...(await original<typeof import("next/server")>()), connection: async () => {} }));
vi.mock("@/lib/base", async (original) => ({
  ...(await original<typeof import("@/lib/base")>()),
  pret: async () => etat.db,
  donnees: () => etat.db,
}));
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

const simule = vi.hoisted(() => ({ appels: [] as string[], suivis: {} as Record<string, unknown>, tarifs: {} as unknown }));
vi.mock("@/lib/admin/atelier", async (original) => {
  const vrai = await original<typeof import("@/lib/admin/atelier")>();
  const noter = (quoi: string) => simule.appels.push(quoi);
  const client = (id: string, entreprise: string, enService: number | null) =>
    ({ id, nom_agent: "Lou", entreprise, version_en_service: enService, derniere_version: 1, gere_par_megga: false });
  const clients = [client("boulangerie-essai", "Boulangerie des Essais", 1), client("chalet-essai", "Chalet des Essais", 1),
    client("librairie-essai", "Librairie des Essais", null)];
  return {
    ...vrai,
    atelier: {
      ...vrai.atelier,
      clients: async () => (noter("clients"), { clients, porte: true }),
      client: async (id: string) => (noter(`client ${id}`), { ...clients.find((c) => c.id === id), config: {} }),
      suivi: async (id: string) => (noter(`suivi ${id}`), simule.suivis[id]),
      alertes: async (id: string) => (noter(`alertes ${id}`), { periode_jours: 7, alertes: [] }),
      tarifs: async () => (noter("tarifs"), simule.tarifs),
      releves: async (jours: number) => (noter(`releves ${jours}`), RELEVES),
    },
  };
});

const TARIFS: Tarifs = { devise: "USD", modeles: { "claude-sonnet-5-5": { entree: 3, sortie: 15, cache_lecture: 0.3, cache_ecriture: 3.75 } },
  voix_par_1000_caracteres: null, par_vocal_entendu: null };

const suivi = (id: string, couts: Suivi["couts"]): Suivi => ({
  id, nom_agent: "Lou", entreprise: id, version_en_service: 1, derniere_version: 1, gere_par_megga: false, periode_jours: 7,
  activite: { tours: 10, tours_api: 0, tours_en_echec: 0, secours: 1, personnes: 2, rappels_en_attente: 0, modeles: {}, journal: {} },
  couts,
});
const LISIBLES = { devise: "USD", postes: { "claude-sonnet-5-5": 1.8507 }, total: 1.8507, sans_tarif: ["deepseek-v4-pro", "voix"] };
// Le relevé chiffré que lit la vue d'ensemble (GET /atelier/releves) : hissé, la simulation de l'atelier le rend.
const RELEVES = vi.hoisted(() => {
  const jour = (cout: number) => ({ tours: 5, tours_api: 0, tours_en_echec: 0, secours: 0, personnes: 1, cout,
    delais: { lecture: { nombre: 0, moyenne: null }, reponse: { nombre: 1, moyenne: 4 }, lentes: 0 } });
  const client = (id: string, entreprise: string, cout: number, sansTarif: string[], autres = {}) => ({
    id, entreprise, zone: "europe", actif: true, version_en_service: 1, ecart: false, releve_le: 1, silencieux: false,
    etat: { demarre: true, pannes_en_cours: [] }, totaux: { tours: 10, tours_api: 0, tours_en_echec: 0, secours: 1, cout, sans_tarif: sansTarif },
    jours: { "2026-11-19": jour(cout / 2), "2026-11-20": jour(cout / 2) }, ...autres });
  return { depuis: "2026-11-14", periode_jours: 7, devise: "USD", clients: [
    client("boulangerie-essai", "Boulangerie des Essais", 1.8507, ["deepseek-v4-pro", "voix"]),
    client("chalet-essai", "Chalet des Essais", 0, [], { silencieux: true }),
  ] };
});
const ILLISIBLES = { erreur: "activité illisible" };

/** Les composants async du serveur (BlocMoteur) se rendent d'abord ; le reste se dessine en HTML. */
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

/** Les éléments d'un type dans l'arbre rendu par une page, sans rien dessiner. */
function elements(n: unknown, type: unknown): ReactElement<Record<string, unknown>>[] {
  if (Array.isArray(n)) return n.flatMap((x) => elements(x, type));
  if (!isValidElement(n)) return [];
  const el = n as ReactElement<Record<string, unknown>>;
  return [...(el.type === type ? [el] : []), ...Object.values(el.props).flatMap((v) => elements(v, type))];
}

/** La valeur d'une tuile, d'après son titre. */
const tuile = (h: string, titre: string) => new RegExp(`>${titre}</span><b[^>]*>([^<]*)</b>`).exec(h)?.[1];

const tarifs = () => PageTarifs();
const suiviDe = (id: string) => PageSuivi({ params: Promise.resolve({ id }), searchParams: Promise.resolve({}) } as never);
const vue = () => VueEnsemble({ searchParams: Promise.resolve({}) } as never);

beforeEach(async () => {
  etat.db = await baseEssai();
  simule.appels = [];
  simule.tarifs = TARIFS;
  simule.suivis = { "boulangerie-essai": suivi("boulangerie-essai", LISIBLES), "chalet-essai": suivi("chalet-essai", ILLISIBLES) };
  const s = acces({ superadmin: true });
  const lectureCouts = await creerRole(etat.db, s, { nom: "Coûts en lecture", droits: ["clients.voir", "couts.voir"] });
  await membre(etat.db, { utilisateur: "finance", role: "finance" });
  await membre(etat.db, { utilisateur: "lecteur", role: "lecture" });
  await membre(etat.db, { utilisateur: "comptable", role: lectureCouts.id });
  await membre(etat.db, { utilisateur: "invite", role: "administration", externe: true, perimetre: ["boulangerie-essai"] });
});

describe("l'écran Tarifs", () => {
  it("sans couts.voir (Lecture, un externe quel que soit son rôle) : 404, l'atelier jamais lu", async () => {
    for (const qui of ["lecteur", "invite"]) {
      etat.qui = qui;
      await expect(tarifs(), qui).rejects.toThrow("404");
    }
    expect(simule.appels).toEqual([]);
  });

  it("couts.voir sans tarifs.regler : en lecture seule, sans le composant du formulaire ni aucune props envoyée au navigateur", async () => {
    etat.qui = "comptable";
    const arbre = await tarifs();
    expect(elements(arbre, FormTarifs)).toEqual([]);
    const h = await html(arbre);
    expect(h).toContain("claude-sonnet-5-5");
    expect(h).toContain(enHtml(TA.sansTarif("deepseek-v4-pro")));
    expect(h).not.toMatch(/<(input|form|button)\b/);
  });

  it("avec tarifs.regler : le formulaire reçoit les tarifs et les modèles vus sans tarif ; seuls les suivis sont lus, aucune alerte", async () => {
    etat.qui = "finance";
    const [form] = elements(await tarifs(), FormTarifs);
    expect(form.props).toEqual({ tarifs: TARIFS, proposes: ["deepseek-v4-pro"] });
    expect(simule.appels.sort()).toEqual(["clients", "suivi boulangerie-essai", "suivi chalet-essai", "tarifs"]);
  });

  it("chaque modèle du formulaire se retire", async () => {
    const deux = { ...TARIFS, modeles: { ...TARIFS.modeles, "deepseek-v4-pro": { entree: 0.5, sortie: 2, cache_lecture: 0, cache_ecriture: 0 } } };
    const h = renderToStaticMarkup(createElement(FormTarifs, { tarifs: deux, proposes: [] }));
    for (const m of ["claude-sonnet-5-5", "deepseek-v4-pro"]) expect(h).toContain(`aria-label="${TA.retirerModele(m)}"`);
  });
});

describe("l'onglet Suivi", () => {
  it("avec couts.voir : le coût par poste et le total ; des coûts illisibles se disent tels quels", async () => {
    etat.qui = "comptable";
    const lisible = await html(await suiviDe("boulangerie-essai"));
    expect(lisible).toContain(`>${TA.couts}</h2>`);
    expect(lisible).toContain(TA.montant(1.8507));
    expect(lisible).toContain(enHtml(TA.sansTarif("deepseek-v4-pro, voix")));
    const illisible = await html(await suiviDe("chalet-essai"));
    expect(illisible).toContain(`>${TA.couts}</h2>`);
    expect(illisible).toContain("activité illisible");
  });

  it("sans couts.voir : ni bloc des coûts, ni montant, ni devise", async () => {
    etat.qui = "lecteur";
    for (const id of ["boulangerie-essai", "chalet-essai"]) {
      const h = await html(await suiviDe(id));
      for (const m of [`>${TA.couts}</h2>`, TA.montant(1.8507), "USD", "activité illisible", "deepseek"]) expect(h, `${id} ${m}`).not.toContain(m);
    }
  });
});

describe("la vue d'ensemble", () => {
  it("un membre Lecture : ni tuile ni colonne de coût, ni montant, ni bandeau des coûts", async () => {
    etat.qui = "lecteur";
    const h = await html(await vue());
    expect(tuile(h, TA.cout)).toBeUndefined();
    for (const m of [TA.cout, "USD", TA.montant(1.8507), "deepseek", enHtml(TA.coutsIllisibles("Chalet des Essais"))]) expect(h, m).not.toContain(m);
  });

  it("avec couts.voir : la tuile « Coût » et sa devise, la colonne, le coût par jour et les modèles sans tarif", async () => {
    etat.qui = "comptable";
    const h = await html(await vue());
    expect(tuile(h, TA.cout)).toBe(TA.montantEn(1.8507, "USD"));
    expect(h).toContain(`>${TA.coutEn("USD")}</th>`);
    expect(h).toContain(TA.coutParJour("USD"));
    expect(h).toContain(enHtml(TA.sansTarif("deepseek-v4-pro, voix")));
  });

  it("une seule lecture, le relevé chiffré : aucun suivi ni aucune alerte de client, la santé la pire d'abord", async () => {
    etat.qui = "comptable";
    const h = await html(await vue());
    expect(simule.appels).toEqual(["releves 7"]);
    expect(tuile(h, TA.aSurveiller)).toBe("1");
    expect(h.indexOf("Chalet des Essais")).toBeLessThan(h.indexOf("Boulangerie des Essais"));
    expect(h).toContain(TA.santes.silencieux);
    expect(h).toContain(TA.secondes(4));
  });
});
