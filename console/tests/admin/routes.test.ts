import { mkdirSync, mkdtempSync, readdirSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, relative, resolve, sep } from "node:path";
import type { DatabaseSync } from "node:sqlite";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Droit } from "@/lib/admin/droits";
import { GARDE } from "@/lib/admin/garde";
import { baseEssai, compte, membre, roleVide } from "./aides";

// Toutes les routes de /api/admin passent par garde ou gardeSession : la liste ci-dessous est celle de la carte des fichiers
// du plan ; une route sur le disque qui n'y est pas, ou une route qui n'est pas gardée, fait échouer l'essai.

type Methode = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
export const ROUTES: { fichier: string; methodes: Methode[]; droit: Droit | "session"; params: Record<string, string>; client: boolean }[] = [];

/** Les route.ts d'un dossier, chemins relatifs (séparés par /) triés ; [] si le dossier n'existe pas encore. */
export function routesSurDisque(dossier: string): string[] {
  const racine = resolve(dossier);
  const parcourir = (d: string): string[] =>
    readdirSync(d).flatMap((n) => {
      const c = join(d, n);
      return statSync(c).isDirectory() ? parcourir(c) : n === "route.ts" ? [relative(racine, c).split(sep).join("/")] : [];
    });
  try {
    return parcourir(racine).sort();
  } catch (e) {
    if ((e as NodeJS.ErrnoException).code === "ENOENT") return [];
    throw e;
  }
}

const etat = vi.hoisted(() => ({ db: undefined as unknown as DatabaseSync }));
vi.mock("@/lib/base", async (original) => ({ ...(await original<typeof import("@/lib/base")>()), base: () => etat.db }));
vi.mock("@/lib/auth", async (original) => ({
  ...(await original<typeof import("@/lib/auth")>()),
  sessionDe: async (r: Request) => {
    const qui = r.headers.get("x-essai-qui");
    return qui ? { user: { id: qui, email: `${qui}@megga.test`, name: qui } } : null;
  },
}));

beforeEach(async () => {
  etat.db = await baseEssai();
  compte(etat.db, { id: "inconnu", courriel: "inconnu@megga.test" });
  membre(etat.db, { utilisateur: "vide", role: roleVide(etat.db) });
  membre(etat.db, { utilisateur: "limite", role: "administration", perimetre: ["garage-essai"] });
});

type Gestionnaire = ((r: Request, ctx: { params: Promise<Record<string, string>> }) => Promise<Response>) & { [GARDE]?: true };

function appeler(f: Gestionnaire, fichier: string, methode: Methode, params: Record<string, string>, qui: string | null) {
  const chemin = dirname(fichier).replace(/\[(\w+)\]/g, (_, p: string) => params[p] ?? p);
  const headers: Record<string, string> = { origin: "http://localhost" };
  if (qui) headers["x-essai-qui"] = qui;
  const requete = new Request(`http://localhost/api/admin/${chemin}`, { method: methode, headers, body: methode === "GET" ? undefined : "{}" });
  return f(requete, { params: Promise.resolve(params) });
}

describe("les routes de /api/admin", () => {
  it("sont toutes dans la liste", () => {
    expect(routesSurDisque("src/app/api/admin")).toEqual(ROUTES.map((r) => r.fichier).sort());
  });

  it("se trouvent sur le disque, à toute profondeur, sans les pages", () => {
    const d = mkdtempSync(join(tmpdir(), "routes-admin-"));
    try {
      for (const f of ["a/route.ts", "b/c/route.ts", "b/page.tsx"]) {
        mkdirSync(dirname(join(d, f)), { recursive: true });
        writeFileSync(join(d, f), "");
      }
      expect(routesSurDisque(d)).toEqual(["a/route.ts", "b/c/route.ts"]);
      expect(routesSurDisque(join(d, "absent"))).toEqual([]);
    } finally {
      rmSync(d, { recursive: true, force: true });
    }
  });

  for (const r of ROUTES) {
    it(`${r.fichier} : gardée, 401 sans session, 404 sans être membre, 403 sans le droit, 404 hors périmètre`, async () => {
      const route = (await import(/* @vite-ignore */ resolve("src/app/api/admin", r.fichier))) as Record<string, unknown>;
      const exportees = Object.keys(route).filter((k) => ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"].includes(k));
      expect(exportees.sort()).toEqual([...r.methodes].sort());
      for (const m of r.methodes) {
        const f = route[m] as Gestionnaire;
        expect(f[GARDE], `${m} gardée`).toBe(true);
        expect((await appeler(f, r.fichier, m, r.params, null)).status, `${m} sans session`).toBe(401);
        if (r.droit === "session") continue;
        expect((await appeler(f, r.fichier, m, r.params, "inconnu")).status, `${m} sans être membre`).toBe(404);
        expect((await appeler(f, r.fichier, m, r.params, "vide")).status, `${m} sans le droit`).toBe(403);
        if (r.client) {
          const dehors = { ...r.params, id: "boulangerie-essai" };
          expect((await appeler(f, r.fichier, m, dehors, "limite")).status, `${m} hors périmètre`).toBe(404);
        }
      }
    });
  }
});
