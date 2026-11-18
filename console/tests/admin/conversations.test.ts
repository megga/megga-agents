import type { DatabaseSync } from "node:sqlite";
import type { ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import PageFil from "@/app/admin/(espace)/clients/[id]/conversations/[personne]/page";
import PageConversations from "@/app/admin/(espace)/clients/[id]/conversations/page";
import { RefusChamps } from "@/lib/admin/atelier";
import { lireJournal } from "@/lib/admin/journal";
import { TA } from "@/lib/admin/textes";
import { acces, baseEssai, membre } from "./aides";

// Les deux pages des conversations, appelées comme Next.js les rend, sans réseau : la session vient de etat.qui, la base
// est celle de l'essai, l'atelier est simulé. Le fil se dessine en HTML ; la liste (ses liens ont besoin du routeur) se lit
// dans l'arbre que la page rend.

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

/** Les textes d'un arbre rendu par une page (ses éléments et leurs props), sans rien dessiner. */
function textes(n: unknown): string[] {
  if (typeof n === "string" || typeof n === "number") return [String(n)];
  if (Array.isArray(n)) return n.flatMap(textes);
  if (n && typeof n === "object" && "props" in n) return Object.values((n as { props: Record<string, unknown> }).props).flatMap(textes);
  return [];
}

/** Le HTML d'une page qui n'a ni lien ni composant du navigateur (le fil). */
const html = (n: unknown) => renderToStaticMarkup(n as ReactNode);
/** Un texte tel que le HTML l'écrit (l'apostrophe échappée). */
const enHtml = (t: string) => t.replaceAll("'", "&#x27;");

const journal = () => lireJournal(etat.db, acces({ superadmin: true }), { page: 1 }).lignes;
const fil = (id: string, personne: string) => PageFil({ params: Promise.resolve({ id, personne }) } as never);
const liste = (id: string) => PageConversations({ params: Promise.resolve({ id }) } as never);

const BOULANGERIE = { id: "boulangerie-essai", nom_agent: "Lou", entreprise: "Boulangerie", version_en_service: 1, derniere_version: 1, gere_par_megga: false, config: {} };
const MESSAGES = [
  { quand: 1_800_000_000, sens: "recu", genre: "texte", texte: "Vous avez encore des tresses ?" },
  { quand: 1_800_000_060, sens: "envoye", genre: "texte", texte: "Oui, je vous en mets une de côté." },
];
const HORS_CLOUDFLARE = "les conversations d'une installation hors Cloudflare ne la quittent jamais : elles se lisent chez le client";

beforeEach(async () => {
  etat.db = await baseEssai();
  simule.appels = [];
  simule.client = BOULANGERIE;
  simule.conversations = { conversations: [{ personne: "+41790000002", messages: 2, derniere: 1_800_000_100 }, { personne: "+41790000001", messages: 4, derniere: 1_800_000_000 }] };
  simule.echanges = { personne: "+41790000001", messages: MESSAGES };
  membre(etat.db, { utilisateur: "exploitant", role: "exploitation" });
  membre(etat.db, { utilisateur: "lecteur", role: "lecture" });
  membre(etat.db, { utilisateur: "ailleurs", role: "exploitation", perimetre: ["garage-essai"] });
  etat.qui = "exploitant";
});

describe("le fil d'une personne", () => {
  it("s'ouvre, en lecture, et se note au journal : la cible est le client, le numéro réduit à ses quatre derniers chiffres", async () => {
    const vu = html(await fil("boulangerie-essai", "%2B41790000001"));
    expect(simule.appels).toEqual(["client boulangerie-essai", "echanges boulangerie-essai +41790000001"]);
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

  it("se lit aussi d'une personne déjà décodée, ou venue par API (qui reste entière au journal)", async () => {
    await fil("boulangerie-essai", "+41790000001");
    await fil("boulangerie-essai", "api%3Acaisse%3Aclient-42");
    expect(simule.appels.filter((x) => x.startsWith("echanges"))).toEqual(["echanges boulangerie-essai +41790000001",
      "echanges boulangerie-essai api:caisse:client-42"]);
    expect(journal().map((l) => l.detail)).toEqual([{ personne: "api:caisse:client-42" }, { personne: "…0001" }]);
  });

  it("chez le client (hors Cloudflare) : la phrase de l'atelier, et la tentative notée refusée", async () => {
    simule.echanges = new RefusChamps(409, HORS_CLOUDFLARE);
    expect(html(await fil("boulangerie-essai", "%2B41790000001"))).toContain(enHtml(HORS_CLOUDFLARE));
    expect(journal().map((l) => `${l.action} ${l.cible} ${l.resultat}`)).toEqual(["conversations.lire client:boulangerie-essai refuse 409"]);
  });

  it("sans conversations.lire, ou hors du périmètre : 404, sans appel à l'atelier ni ligne au journal", async () => {
    for (const qui of ["lecteur", "ailleurs"]) {
      etat.qui = qui;
      await expect(fil("boulangerie-essai", "%2B41790000001"), qui).rejects.toThrow("404");
      await expect(liste("boulangerie-essai"), qui).rejects.toThrow("404");
    }
    expect([simule.appels, journal()]).toEqual([[], []]);
  });

  it("une personne tapée à la main, mal formée : 404, sans appel à l'atelier ni ligne au journal", async () => {
    for (const p of ["..", "%2E%2E", "abc", "%E0%A4%A"]) await expect(fil("boulangerie-essai", p), p).rejects.toThrow("404");
    expect([simule.appels, journal()]).toEqual([[], []]);
  });

  it("un client jamais mis en service : un bandeau, rien de lu ni de noté", async () => {
    simule.client = { ...BOULANGERIE, version_en_service: null };
    expect(textes(await fil("boulangerie-essai", "%2B41790000001"))).toContain(TA.jamaisSansConversation);
    expect(textes(await liste("boulangerie-essai"))).toContain(TA.jamaisSansConversation);
    expect([simule.appels.filter((x) => !x.startsWith("client")), journal()]).toEqual([[], []]);
  });
});

describe("la liste des conversations", () => {
  it("les personnes, la plus récente d'abord comme l'atelier les rend ; ouvrir la liste ne se note pas", async () => {
    const vu = textes(await liste("boulangerie-essai"));
    expect(vu.filter((t) => t.startsWith("+41"))).toEqual(["+41790000002", "+41790000001"]);
    expect(journal()).toEqual([]);
  });

  it("chez le client (hors Cloudflare) : la phrase de l'atelier", async () => {
    simule.conversations = new RefusChamps(409, HORS_CLOUDFLARE);
    expect(textes(await liste("boulangerie-essai"))).toContain(HORS_CLOUDFLARE);
  });
});
