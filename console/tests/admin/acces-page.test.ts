import type { DatabaseSync } from "node:sqlite";
import { isValidElement, type ReactElement, type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Cles, Jetons, Main } from "@/app/admin/(espace)/clients/[id]/acces/acces";
import PageAcces from "@/app/admin/(espace)/clients/[id]/acces/page";
import { RefusChamps } from "@/lib/admin/atelier";
import { creerRole } from "@/lib/admin/roles";
import { TA } from "@/lib/admin/textes";
import { acces, dbEssai, membre } from "./aides";

// L'onglet Accès, appelé comme Next.js le rend (session, base et atelier simulés) : chaque bloc suit son droit, un externe
// n'y entre pas, et la liste des clés ne porte que ce que l'écran montre.

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
  useRouter: () => ({ refresh: () => {} }),
}));

const simule = vi.hoisted(() => ({ appels: [] as string[], cles: {} as unknown }));
vi.mock("@/lib/admin/atelier", async (original) => {
  const vrai = await original<typeof import("@/lib/admin/atelier")>();
  return {
    ...vrai,
    atelier: {
      ...vrai.atelier,
      client: async (id: string) => (simule.appels.push(`client ${id}`), { id, nom_agent: "Max", entreprise: "Garage", version_en_service: 1,
        derniere_version: 1, gere_par_megga: true, config: {} }),
      cles: async (id: string) => {
        simule.appels.push(`cles ${id}`);
        if (simule.cles instanceof Error) throw simule.cles;
        return simule.cles;
      },
    },
  };
});

const page = (id = "garage-essai") => PageAcces({ params: Promise.resolve({ id }) } as never);
const enHtml = (t: string) => t.replaceAll("'", "&#x27;");

function elements(n: unknown, type: unknown): ReactElement<Record<string, unknown>>[] {
  if (Array.isArray(n)) return n.flatMap((x) => elements(x, type));
  if (!isValidElement(n)) return [];
  const el = n as ReactElement<Record<string, unknown>>;
  return [...(el.type === type ? [el] : []), ...Object.values(el.props).flatMap((v) => elements(v, type))];
}

beforeEach(async () => {
  etat.db = await dbEssai();
  simule.appels = [];
  simule.cles = { client: "garage-essai", cles: [{ id: "d15a76f57ee4", logiciel: "caisse", par_minute: 30, cree: 1_800_000_000, retiree: null,
    empreinte: "ne-doit-pas-sortir" }] };
  const pilote = creerRole(etat.db, acces({ superadmin: true }), { nom: "Pilote", droits: ["clients.voir", "clients.piloter"] });
  membre(etat.db, { utilisateur: "exploitant", role: "exploitation" });
  membre(etat.db, { utilisateur: "pilote", role: pilote.id });
  membre(etat.db, { utilisateur: "invite", role: "administration", externe: true, perimetre: ["garage-essai"] });
  membre(etat.db, { utilisateur: "lecteur", role: "lecture" });
  etat.qui = "exploitant";
});

describe("l'onglet Accès", () => {
  it("avec acces.gerer et clients.piloter : la main, les jetons, les clés (rien de plus que ce que l'écran montre)", async () => {
    const arbre = await page();
    expect(elements(arbre, Main)[0].props).toEqual({ id: "garage-essai", gere: true });
    expect(elements(arbre, Jetons)[0].props).toEqual({ id: "garage-essai" });
    expect(elements(arbre, Cles)[0].props).toEqual({ id: "garage-essai",
      cles: [{ id: "d15a76f57ee4", logiciel: "caisse", parMinute: 30, creeLe: TA.moment(1_800_000_000), retireeLe: null }] });
    expect(JSON.stringify(elements(arbre, Cles)[0].props)).not.toContain("ne-doit-pas-sortir");
  });

  it("avec clients.piloter seul : la main, sans jetons ni clés, et l'atelier ne lit pas les clés", async () => {
    etat.qui = "pilote";
    const arbre = await page();
    expect([elements(arbre, Main).length, elements(arbre, Jetons).length, elements(arbre, Cles).length]).toEqual([1, 0, 0]);
    expect(simule.appels).toEqual(["client garage-essai"]);
  });

  it("hors Cloudflare ou jamais mis en service : la phrase 409 de l'atelier tient lieu de liste, sans formulaire", async () => {
    const phrase = "hors Cloudflare, les clés se créent chez le client : python -m noyau.cles creer <logiciel> (docs/api.md)";
    simule.cles = new RefusChamps(409, phrase);
    const arbre = await page();
    expect(elements(arbre, Cles)).toEqual([]);
    expect(renderToStaticMarkup(arbre as ReactNode)).toContain(enHtml(phrase).replace("<logiciel>", "&lt;logiciel&gt;"));
  });

  it("un externe, ou un membre sans ces droits, ou hors du périmètre : 404, sans appel à l'atelier", async () => {
    for (const qui of ["invite", "lecteur"]) {
      etat.qui = qui;
      await expect(page(), qui).rejects.toThrow("404");
    }
    etat.qui = "invite";
    await expect(page("boulangerie-essai")).rejects.toThrow("404");
    expect(simule.appels).toEqual([]);
  });
});
