import { describe, expect, it, vi } from "vitest";
import { GET } from "@/app/api/compte/photo/[utilisateur]/route";
import { lirePhoto, PHOTO_MAX_OCTETS, poserPhoto, retirerPhoto } from "@/lib/admin/photo";
import { TA } from "@/lib/admin/textes";
import type { Base } from "@/lib/donnees/base";
import { moteursEssai } from "../moteurs";
import { baseEssai, refusAsync } from "./aides";

// La photo de profil : rangée dans la base de la console (compte_photo), servie à qui est connecté. Seules des images WebP,
// JPEG ou PNG passent, d'après leurs premiers octets, pas d'après le type annoncé ; 200 Ko au plus.

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

/** Un WebP minimal : RIFF, sa taille, WEBP, puis un morceau VP8L. */
function webp(): Uint8Array {
  const corps = [..."WEBP"].map((c) => c.charCodeAt(0)).concat([..."VP8L"].map((c) => c.charCodeAt(0)), [5, 0, 0, 0, 0x2f, 0, 0, 0, 0]);
  const taille = corps.length;
  return Uint8Array.from([..."RIFF"].map((c) => c.charCodeAt(0)).concat([taille & 0xff, (taille >> 8) & 0xff, 0, 0], corps));
}
const PNG = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];
const png = (n = 32) => Uint8Array.from({ length: n }, (_, i) => (i < PNG.length ? PNG[i] : i % 251));
const base64 = (o: Uint8Array) => Buffer.from(o).toString("base64");

describe.each(moteursEssai())("la photo, sous %s", (moteur) => {
  it("range et relit une photo WebP", async () => {
    const b = await baseEssai(moteur);
    const octets = webp();
    const adresse = await poserPhoto(b, "u1", base64(octets), "image/webp");
    expect(adresse).toMatch(/^\/api\/compte\/photo\/u1\?v=[0-9a-f]{12}$/);
    const lue = await lirePhoto(b, "u1");
    expect(lue?.type).toBe("image/webp");
    expect([...lue!.octets]).toEqual([...octets]);
  });

  it("refuse des octets qui ne sont pas l'image annoncée", async () => {
    const b = await baseEssai(moteur);
    const svg = new TextEncoder().encode('<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>');
    const html = new TextEncoder().encode("<!doctype html><script>alert(1)</script>");
    for (const [octets, type] of [[svg, "image/png"], [svg, "image/svg+xml"], [html, "image/jpeg"], [png(), "image/webp"], [webp(), "text/html"]] as const) {
      const r = await refusAsync(() => poserPhoto(b, "u1", base64(octets), type));
      expect(r.statut, type).toBe(400);
      expect(r.message).toBe(TA.photoInvalide);
    }
    const r = await refusAsync(() => poserPhoto(b, "u1", "pas du base64 !", "image/png"));
    expect(r.statut).toBe(400);
    expect(await lirePhoto(b, "u1")).toBeUndefined();
    expect(await b.tous("SELECT utilisateur FROM compte_photo")).toEqual([]);
  });

  it("refuse une photo trop lourde", async () => {
    const b = await baseEssai(moteur);
    const r = await refusAsync(() => poserPhoto(b, "u1", base64(png(PHOTO_MAX_OCTETS + 1)), "image/png"));
    expect(r.statut).toBe(413);
    expect(r.message).toBe(TA.photoTropLourde);
    expect(await lirePhoto(b, "u1")).toBeUndefined();
    // À la limite exacte, elle passe.
    await poserPhoto(b, "u1", base64(png(PHOTO_MAX_OCTETS)), "image/png");
    expect((await lirePhoto(b, "u1"))?.octets.length).toBe(PHOTO_MAX_OCTETS);
  });

  it("remplace puis retire", async () => {
    const b = await baseEssai(moteur);
    const a1 = await poserPhoto(b, "u1", base64(webp()), "image/webp");
    const a2 = await poserPhoto(b, "u1", base64(png()), "image/png");
    expect(a2).not.toBe(a1);
    expect((await lirePhoto(b, "u1"))?.type).toBe("image/png");
    expect(await b.tous("SELECT utilisateur FROM compte_photo")).toEqual([{ utilisateur: "u1" }]);
    await retirerPhoto(b, "u1");
    expect(await lirePhoto(b, "u1")).toBeUndefined();
    await retirerPhoto(b, "u1"); // retirer une photo absente ne refuse rien
  });

  it("vérifie aussi un JPEG", async () => {
    const b = await baseEssai(moteur);
    await poserPhoto(b, "u1", base64(Uint8Array.from([0xff, 0xd8, 0xff, 0xe0, 0, 0x10, 0x4a, 0x46])), "image/jpeg");
    expect((await lirePhoto(b, "u1"))?.type).toBe("image/jpeg");
  });
});

describe("la route de la photo", () => {
  const servir = (utilisateur: string, qui: string | null) =>
    GET(new Request(`http://localhost/api/compte/photo/${utilisateur}?v=abc`, { headers: qui ? { "x-essai-qui": qui } : {} }),
      { params: Promise.resolve({ utilisateur }) });

  it("exige une session pour servir une photo", async () => {
    etat.db = await baseEssai();
    await poserPhoto(etat.db, "u1", base64(png()), "image/png");
    const r = await servir("u1", null);
    expect(r.status).toBe(401);
    expect(r.headers.get("content-type")).not.toMatch(/^image\//);
  });

  it("sert la photo avec ses en-têtes", async () => {
    etat.db = await baseEssai();
    const octets = png();
    await poserPhoto(etat.db, "u1", base64(octets), "image/png");
    const r = await servir("u1", "u2"); // un autre compte connecté la voit, comme son nom
    expect(r.status).toBe(200);
    expect(r.headers.get("content-type")).toBe("image/png");
    expect(r.headers.get("cache-control")).toBe("private, max-age=31536000, immutable");
    expect(r.headers.get("x-content-type-options")).toBe("nosniff");
    expect(r.headers.get("content-security-policy")).toBe("default-src 'none'");
    expect([...new Uint8Array(await r.arrayBuffer())]).toEqual([...octets]);
  });

  it("rend 404 sans photo", async () => {
    etat.db = await baseEssai();
    expect((await servir("u1", "u1")).status).toBe(404);
  });
});
