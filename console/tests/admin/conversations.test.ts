import type { DatabaseSync } from "node:sqlite";
import type { ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import PageFil from "@/app/admin/(espace)/clients/[id]/conversations/[cle]/page";
import PageConversations from "@/app/admin/(espace)/clients/[id]/conversations/page";
import { RefusChamps } from "@/lib/admin/atelier";
import { lireJournal } from "@/lib/admin/journal";
import { clePersonne } from "@/lib/admin/personnes";
import { TA } from "@/lib/admin/textes";
import { acces, baseEssai, membre } from "./aides";

// Les deux pages des conversations, appelées comme Next.js les rend, sans réseau : la session vient de etat.qui, la base
// est celle de l'essai, l'atelier est simulé, un lien est un simple <a>. Ce que la page montre se lit dans son HTML.

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
}));
vi.mock("next/link", async () => {
  const { createElement } = await import("react");
  return { default: (p: { href: string; className?: string; children?: ReactNode }) => createElement("a", { href: p.href, className: p.className }, p.children) };
});

const simule = vi.hoisted(() => ({ appels: [] as string[], client: {} as unknown, conversations: {} as unknown, echanges: {} as unknown }));
vi.mock("@/lib/admin/atelier", async (original) => {
  const vrai = await original<typeof import("@/lib/admin/atelier")>();
  const repondre = (nom: "client" | "conversations" | "echanges") => async (...args: unknown[]) => {
    simule.appels.push(`${nom} ${args.join(" ")}`);
    const r = simule[nom];
    if (r instanceof Error) throw r;
    return r;
  };
  return { ...vrai, atelier: { ...vrai.atelier, client: repondre("client"), conversations: repondre("conversations"), echanges: repondre("echanges") } };
});

const SECRET = "secret-des-essais-des-conversations";
const html = (n: unknown) => renderToStaticMarkup(n as ReactNode);
/** Un texte tel que le HTML l'écrit (l'apostrophe échappée). */
const enHtml = (t: string) => t.replaceAll("'", "&#x27;");
const journal = () => lireJournal(etat.db, acces({ superadmin: true }), { page: 1 }).lignes;
const fil = (id: string, cle: string) => PageFil({ params: Promise.resolve({ id, cle }) } as never);
const liste = (id: string) => PageConversations({ params: Promise.resolve({ id }) } as never);
const cle = (personne: string, client = "boulangerie-essai") => clePersonne(client, personne, SECRET);

const BOULANGERIE = { id: "boulangerie-essai", nom_agent: "Lou", entreprise: "Boulangerie", version_en_service: 1, derniere_version: 1, gere_par_megga: false, config: {} };
const PERSONNES = [
  { personne: "+41790000002", messages: 2, derniere: 1_800_000_100 },
  { personne: "+41790000001", messages: 4, derniere: 1_800_000_000 },
  { personne: "api:caisse:client-42", messages: 2, derniere: 1_700_000_000 },
];
const MESSAGES = [
  { quand: 1_800_000_000, sens: "recu", genre: "texte", texte: "Vous avez encore des tresses ?" },
  { quand: 1_800_000_060, sens: "envoye", genre: "texte", texte: "Oui, je vous en mets une de côté." },
];
const HORS_CLOUDFLARE = "les conversations d'une installation hors Cloudflare ne la quittent jamais : elles se lisent chez le client";

beforeEach(async () => {
  process.env.BETTER_AUTH_SECRET = SECRET;
  etat.db = await baseEssai();
  simule.appels = [];
  simule.client = BOULANGERIE;
  simule.conversations = { conversations: PERSONNES };
  simule.echanges = { personne: "+41790000001", messages: MESSAGES };
  membre(etat.db, { utilisateur: "exploitant", role: "exploitation" });
  membre(etat.db, { utilisateur: "lecteur", role: "lecture" });
  membre(etat.db, { utilisateur: "ailleurs", role: "exploitation", perimetre: ["garage-essai"] });
  etat.qui = "exploitant";
});
afterEach(() => {
  delete process.env.BETTER_AUTH_SECRET;
});

describe("la clé d'une personne", () => {
  it("est stable, 16 caractères hexadécimaux, dépend du client et du secret, et ne contient pas le numéro", () => {
    const k = cle("+41790000001");
    expect(k).toMatch(/^[0-9a-f]{16}$/);
    expect(cle("+41790000001")).toBe(k);
    expect(clePersonne("boulangerie-essai", "+41790000001")).toBe(k); // le secret de l'environnement, BETTER_AUTH_SECRET
    expect(new Set([k, cle("+41790000001", "garage-essai"), clePersonne("boulangerie-essai", "+41790000001", "un-autre-secret"),
      cle("+41790000002")]).size).toBe(4);
    expect(k).not.toMatch(/41790000001|0000001/);
  });

  it("ne se calcule pas sans secret", () => {
    delete process.env.BETTER_AUTH_SECRET;
    expect(() => clePersonne("boulangerie-essai", "+41790000001")).toThrow();
  });
});

describe("le fil d'une personne", () => {
  it("s'ouvre par sa clé, en lecture, et se note au journal : la cible est le client, le numéro réduit à ses quatre derniers chiffres", async () => {
    const vu = html(await fil("boulangerie-essai", cle("+41790000001")));
    expect(simule.appels).toEqual(["client boulangerie-essai", "conversations boulangerie-essai", "echanges boulangerie-essai +41790000001"]);
    expect(vu).toContain("+41790000001");
    // Reçu d'abord, à gauche ; puis la réponse de l'agent, à droite ; aucun champ ni bouton : en lecture seule.
    const recu = vu.indexOf(enHtml(`${TA.recu} </span>${MESSAGES[0].texte}`));
    const envoye = vu.indexOf(enHtml(`${TA.envoye} </span>${MESSAGES[1].texte}`));
    expect([recu > 0, envoye > recu]).toEqual([true, true]);
    expect(vu).not.toMatch(/<(input|textarea|button|form)\b/);
    expect(journal()).toEqual([expect.objectContaining({ qui: "exploitant", courriel: "exploitant@megga.test", action: "conversations.lire",
      cible: "client:boulangerie-essai", resultat: "ok", detail: { personne: "…0001" } })]);
    expect(JSON.stringify(etat.db.prepare("SELECT * FROM admin_journal").all())).not.toContain("41790000001");
  });

  it("une personne venue par API s'ouvre aussi, et reste entière au journal", async () => {
    await fil("boulangerie-essai", cle("api:caisse:client-42"));
    expect(simule.appels.at(-1)).toBe("echanges boulangerie-essai api:caisse:client-42");
    expect(journal().map((l) => l.detail)).toEqual([{ personne: "api:caisse:client-42" }]);
  });

  it("une clé mal formée : 404, sans aucun appel à l'atelier ni ligne au journal", async () => {
    for (const k of ["+41790000001", "%2B41790000001", "41790000001", cle("+41790000001").toUpperCase(), "0123", "..",
      cle("+41790000001") + "0", "0123456789abcdeg"]) {
      await expect(fil("boulangerie-essai", k), k).rejects.toThrow("404");
    }
    expect([simule.appels, journal()]).toEqual([[], []]);
  });

  it("une clé bien formée mais inconnue (une autre personne, un autre client, un autre secret) : 404, aucun fil lu ni noté", async () => {
    for (const k of ["0123456789abcdef", cle("+41790000009"), cle("+41790000001", "garage-essai"),
      clePersonne("boulangerie-essai", "+41790000001", "un-autre-secret")]) {
      await expect(fil("boulangerie-essai", k), k).rejects.toThrow("404");
    }
    expect([simule.appels.filter((x) => x.startsWith("echanges")), journal()]).toEqual([[], []]);
  });

  it("un fil que l'atelier refuse : sa phrase, la tentative notée refusée", async () => {
    simule.echanges = new RefusChamps(502, TA.atelierInjoignable);
    expect(html(await fil("boulangerie-essai", cle("+41790000001")))).toContain(enHtml(TA.atelierInjoignable));
    expect(journal().map((l) => [l.cible, l.resultat, l.detail])).toEqual([["client:boulangerie-essai", "refuse 502", { personne: "…0001" }]]);
  });

  it("chez le client (hors Cloudflare) : la phrase de l'atelier ; aucune personne n'est connue, rien n'est noté", async () => {
    simule.conversations = new RefusChamps(409, HORS_CLOUDFLARE);
    expect(html(await fil("boulangerie-essai", cle("+41790000001")))).toContain(enHtml(HORS_CLOUDFLARE));
    expect([simule.appels.filter((x) => x.startsWith("echanges")), journal()]).toEqual([[], []]);
  });

  it("sans conversations.lire, ou hors du périmètre : 404, sans appel à l'atelier ni ligne au journal", async () => {
    for (const qui of ["lecteur", "ailleurs"]) {
      etat.qui = qui;
      await expect(fil("boulangerie-essai", cle("+41790000001")), qui).rejects.toThrow("404");
      await expect(liste("boulangerie-essai"), qui).rejects.toThrow("404");
    }
    expect([simule.appels, journal()]).toEqual([[], []]);
  });

  it("un client jamais mis en service : un bandeau, rien de lu ni de noté", async () => {
    simule.client = { ...BOULANGERIE, version_en_service: null };
    expect(html(await fil("boulangerie-essai", cle("+41790000001")))).toContain(enHtml(TA.jamaisSansConversation));
    expect(html(await liste("boulangerie-essai"))).toContain(enHtml(TA.jamaisSansConversation));
    expect([simule.appels.filter((x) => !x.startsWith("client")), journal()]).toEqual([[], []]);
  });
});

describe("la liste des conversations", () => {
  it("les personnes, la plus récente d'abord comme l'atelier les rend, chacune liée par sa clé : aucun lien ne porte un numéro", async () => {
    const vu = html(await liste("boulangerie-essai"));
    const liens = [...vu.matchAll(/href="([^"]*)"/g)].map((m) => m[1]);
    expect(liens).toEqual(PERSONNES.map((p) => `/admin/clients/boulangerie-essai/conversations/${cle(p.personne)}`));
    for (const l of liens) expect(l).not.toMatch(/4179|%2B|\+|api|caisse/);
    expect([...vu.matchAll(/>(\+41\d+)</g)].map((m) => m[1])).toEqual(["+41790000002", "+41790000001"]);
    expect(journal()).toEqual([]);
  });

  it("chez le client (hors Cloudflare) : la phrase de l'atelier", async () => {
    simule.conversations = new RefusChamps(409, HORS_CLOUDFLARE);
    expect(html(await liste("boulangerie-essai"))).toContain(enHtml(HORS_CLOUDFLARE));
  });
});
