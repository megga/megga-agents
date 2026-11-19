import { cloneElement, isValidElement, type ReactElement, type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import PageMonCompte from "@/app/admin/(espace)/compte/page";
import { TA } from "@/lib/admin/textes";
import type { Base } from "@/lib/donnees/base";
import { T } from "@/lib/textes";
import { baseEssai, compte, membre, roleVide } from "./aides";

// La page Mon compte, appelée comme Next.js la rend (session et base simulées), puis dessinée en HTML : ouverte à tout membre,
// même sans droit ; ses appareils connectés, celui-ci marqué, sans jeton ni adresse IP.

const etat = vi.hoisted(() => ({ db: undefined as unknown as Base, qui: null as string | null }));
vi.mock("next/server", async (original) => ({ ...(await original<typeof import("next/server")>()), connection: async () => {} }));
vi.mock("@/lib/base", async (original) => ({
  ...(await original<typeof import("@/lib/base")>()),
  pret: async () => etat.db,
  donnees: () => etat.db,
}));
vi.mock("@/lib/auth", async (original) => ({
  ...(await original<typeof import("@/lib/auth")>()),
  session: async () =>
    etat.qui ? { user: { id: etat.qui, email: `${etat.qui}@megga.test`, name: etat.qui }, session: { id: `s-${etat.qui}-1` } } : null,
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

async function resoudre(n: unknown): Promise<unknown> {
  if (Array.isArray(n)) return Promise.all(n.map(resoudre));
  if (!isValidElement(n)) return n;
  const el = n as ReactElement<{ children?: unknown }>;
  if (typeof el.type === "function" && el.type.constructor.name === "AsyncFunction") {
    return resoudre(await (el.type as (p: unknown) => Promise<unknown>)(el.props));
  }
  return el.props.children === undefined ? el : cloneElement(el, { children: await resoudre(el.props.children) } as never);
}
const html = async () => renderToStaticMarkup((await resoudre(await PageMonCompte())) as ReactNode);
const enHtml = (t: string) => t.replaceAll("'", "&#x27;");

const CHROME_MAC = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36";
const SAFARI_IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1";

async function session(id: string, utilisateur: string, agent: string, expire = Date.now() + 86_400_000) {
  const maintenant = new Date().toISOString();
  await etat.db.ecrire('INSERT INTO session (id, "expiresAt", token, "createdAt", "updatedAt", "ipAddress", "userAgent", "userId") VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
    id, new Date(expire).toISOString(), `jeton-${id}`, maintenant, maintenant, "203.0.113.42", agent, utilisateur);
}

beforeEach(async () => {
  etat.db = await baseEssai();
  etat.qui = null;
});

describe("la page Mon compte", () => {
  it("s'ouvre à un membre sans aucun droit : son nom, son courriel en lecture, ses appareils, celui-ci marqué", async () => {
    await membre(etat.db, { utilisateur: "v", role: await roleVide(etat.db) });
    await session("s-v-1", "v", CHROME_MAC);
    await session("s-v-2", "v", SAFARI_IPHONE);
    await session("s-v-3", "v", SAFARI_IPHONE, Date.now() - 1000); // expirée : pas un appareil connecté
    await compte(etat.db, { id: "autre", courriel: "autre@megga.test" });
    await session("s-autre", "autre", CHROME_MAC);
    etat.qui = "v";
    const h = await html();
    expect(h).toContain(T.monCompte);
    expect(h).toMatch(/<input[^>]*id="compte-nom"[^>]*value="V"/);
    expect(h).toMatch(/<input[^>]*id="compte-courriel"[^>]*readOnly=""|<input[^>]*readOnly=""[^>]*id="compte-courriel"/i);
    expect(h).toContain("v@megga.test");
    expect(h).toContain("Chrome sur macOS");
    expect(h).toContain("Safari sur iPhone");
    expect(h.match(new RegExp(TA.cetAppareil, "g"))).toHaveLength(1);
    expect(h.indexOf("Chrome sur macOS")).toBeLessThan(h.indexOf("Safari sur iPhone")); // celle-ci d'abord
    expect(h).toContain(TA.deconnecterAutres);
    for (const secret of ["jeton-", "203.0.113.42", "s-autre"]) expect(h).not.toContain(secret);
    expect(h).toContain(enHtml(TA.choisirPhoto));
    expect(h).not.toContain(TA.retirerPhoto);
  });

  it("sans autre appareil, pas de bouton pour les déconnecter ; avec une photo, la photo et de quoi la retirer", async () => {
    await membre(etat.db, { utilisateur: "v", role: "lecture" });
    await session("s-v-1", "v", CHROME_MAC);
    await etat.db.ecrire('UPDATE "user" SET image = ? WHERE id = ?', "/api/compte/photo/v?v=0123456789ab", "v");
    etat.qui = "v";
    const h = await html();
    expect(h).not.toContain(TA.deconnecterAutres);
    expect(h).toMatch(/<img[^>]*src="\/api\/compte\/photo\/v\?v=0123456789ab"/);
    expect(h).toContain(TA.retirerPhoto);
  });

  it("sans session, la connexion ; sans être membre, 404", async () => {
    await expect(PageMonCompte()).rejects.toThrow("redirect:/connexion?retour=/admin");
    await compte(etat.db, { id: "c", courriel: "c@megga.test" });
    etat.qui = "c";
    await expect(PageMonCompte()).rejects.toThrow("404");
  });
});
