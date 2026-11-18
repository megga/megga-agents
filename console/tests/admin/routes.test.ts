import { existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, relative, resolve, sep } from "node:path";
import type { DatabaseSync } from "node:sqlite";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DROITS, type Droit } from "@/lib/admin/droits";
import { GARDE } from "@/lib/admin/garde";
import { baseEssai, compte, membre, roleVide } from "./aides";

// Toutes les routes de /api/admin passent par garde ou gardeSession : la liste ci-dessous est celle de la carte des fichiers
// du plan ; une route sur le disque qui n'y est pas, une route qui n'est pas gardée ou gardée par un autre droit, fait échouer
// l'essai. Aucune Server Action (« use server ») sous l'admin : elle échapperait à la garde.

const CONSOLE = join(__dirname, "../..");
const API_ADMIN = join(CONSOLE, "src/app/api/admin");

type Methode = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
export const ROUTES: { fichier: string; methodes: Methode[]; droit: Droit | "session"; params: Record<string, string>; client: boolean }[] = [
  { fichier: "equipe/membres/[id]/route.ts", methodes: ["PATCH", "DELETE"], droit: "equipe.gerer", params: { id: "limite" }, client: false },
  { fichier: "equipe/invitations/route.ts", methodes: ["POST"], droit: "equipe.gerer", params: {}, client: false },
  { fichier: "equipe/invitations/[id]/route.ts", methodes: ["DELETE"], droit: "equipe.gerer", params: { id: "in_x" }, client: false },
  { fichier: "equipe/roles/route.ts", methodes: ["POST"], droit: "equipe.gerer", params: {}, client: false },
  { fichier: "equipe/roles/[id]/route.ts", methodes: ["PATCH", "DELETE"], droit: "equipe.gerer", params: { id: "lecture" }, client: false },
  { fichier: "invitation/route.ts", methodes: ["POST"], droit: "session", params: {}, client: false },
  { fichier: "tarifs/route.ts", methodes: ["PUT"], droit: "tarifs.regler", params: {}, client: false },
  { fichier: "clients/[id]/valider/route.ts", methodes: ["POST"], droit: "versions.preparer", params: { id: "garage-essai" }, client: true },
  { fichier: "clients/[id]/versions/route.ts", methodes: ["POST"], droit: "versions.preparer", params: { id: "garage-essai" }, client: true },
  { fichier: "clients/[id]/versions/[numero]/essai/route.ts", methodes: ["POST"], droit: "versions.preparer", params: { id: "garage-essai", numero: "1" },
    client: true },
  { fichier: "clients/[id]/versions/[numero]/activer/route.ts", methodes: ["POST"], droit: "clients.piloter", params: { id: "garage-essai", numero: "1" },
    client: true },
];

/** Les fichiers d'un dossier, à toute profondeur, qui passent le filtre ; chemins relatifs (séparés par /) triés. Dossier absent : erreur. */
function fichiersDe(dossier: string, garder: (nom: string, chemin: string) => boolean): string[] {
  const racine = resolve(dossier);
  const parcourir = (d: string): string[] =>
    readdirSync(d).flatMap((n) => {
      const c = join(d, n);
      return statSync(c).isDirectory() ? parcourir(c) : garder(n, c) ? [relative(racine, c).split(sep).join("/")] : [];
    });
  return parcourir(racine).sort();
}

/** Les route.ts, .tsx, .js et .mjs d'un dossier (un dossier absent est une erreur). */
export function routesSurDisque(dossier: string): string[] {
  return fichiersDe(dossier, (n) => /^route\.(ts|tsx|js|mjs)$/.test(n));
}

/** Les fichiers qui portent la directive « use server » (seule sur sa ligne, en tête de module ou de fonction). */
function fichiersAvecUseServer(dossier: string): string[] {
  return fichiersDe(dossier, (_, c) => /^\s*["']use server["']/m.test(readFileSync(c, "utf8")));
}

/** Un rôle qui a les treize droits sauf un ; rend son identifiant. */
function roleSauf(db: DatabaseSync, droit: Droit): string {
  const id = `sauf-${droit}`;
  db.prepare("INSERT INTO admin_role (id, nom, description, droits, systeme, cree_le, modifie_le) VALUES (?, ?, '', ?, 0, '', '')")
    .run(id, id, JSON.stringify(DROITS.filter((d) => d !== droit)));
  return id;
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

// L'atelier simulé : chaque fonction note son appel ; une route refusée n'en appelle aucune.
const appelsAtelier = vi.hoisted(() => [] as string[]);
vi.mock("@/lib/admin/atelier", async (original) => {
  const vrai = await original<typeof import("@/lib/admin/atelier")>();
  const atelier = Object.fromEntries(Object.keys(vrai.atelier).map((f) => [f, async () => {
    appelsAtelier.push(f);
    return {};
  }]));
  return { ...vrai, atelier, atelierBranche: () => true };
});

beforeEach(async () => {
  appelsAtelier.length = 0;
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
    // Avant la première route, le dossier n'existe pas encore : la liste doit alors être vide.
    const surDisque = existsSync(API_ADMIN) ? routesSurDisque(API_ADMIN) : [];
    expect(surDisque).toEqual(ROUTES.map((r) => r.fichier).sort());
  });

  it("se trouvent sur le disque, à toute profondeur, en .ts, .tsx, .js ou .mjs, sans les pages ; un dossier absent est une erreur", () => {
    const d = mkdtempSync(join(tmpdir(), "routes-admin-"));
    try {
      const fichiers = { "a/route.ts": "", "b/c/route.ts": "", "b/page.tsx": "", "d/route.js": "", "e/route.tsx": "", "f/route.mjs": "",
        "g/route.test.ts": "", "h/routes.ts": "", "i/actions.ts": '"use server";\nexport async function f() {}',
        "j/page.tsx": "export default function P() {\n  async function agir() {\n    'use server';\n  }\n}", "k/notes.ts": "// ici, pas de 'use server'" };
      for (const [f, contenu] of Object.entries(fichiers)) {
        mkdirSync(dirname(join(d, f)), { recursive: true });
        writeFileSync(join(d, f), contenu);
      }
      expect(routesSurDisque(d)).toEqual(["a/route.ts", "b/c/route.ts", "d/route.js", "e/route.tsx", "f/route.mjs"]);
      expect(() => routesSurDisque(join(d, "absent"))).toThrow();
      expect(fichiersAvecUseServer(d)).toEqual(["i/actions.ts", "j/page.tsx"]);
    } finally {
      rmSync(d, { recursive: true, force: true });
    }
  });

  it("n'ont pas d'écriture hors des routes : aucun « use server » sous l'admin", () => {
    for (const d of ["src/app/admin", "src/components/admin", "src/app/api/admin"]) {
      const dossier = join(CONSOLE, d);
      if (!existsSync(dossier)) continue; // pas encore écrit : rien à craindre
      expect(fichiersAvecUseServer(dossier), d).toEqual([]);
    }
  });

  for (const r of ROUTES) {
    it(`${r.fichier} : gardée, 401 sans session, 404 sans être membre, 403 sans son droit, 404 hors périmètre`, async () => {
      const route = (await import(/* @vite-ignore */ join(API_ADMIN, r.fichier))) as Record<string, unknown>;
      if (r.droit !== "session") membre(etat.db, { utilisateur: "presque", role: roleSauf(etat.db, r.droit) });
      const exportees = Object.keys(route).filter((k) => ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"].includes(k));
      expect(exportees.sort()).toEqual([...r.methodes].sort());
      for (const m of r.methodes) {
        const f = route[m] as Gestionnaire;
        expect(f[GARDE], `${m} gardée`).toBe(true);
        expect((await appeler(f, r.fichier, m, r.params, null)).status, `${m} sans session`).toBe(401);
        if (r.droit === "session") continue;
        expect((await appeler(f, r.fichier, m, r.params, "inconnu")).status, `${m} sans être membre`).toBe(404);
        expect((await appeler(f, r.fichier, m, r.params, "vide")).status, `${m} sans aucun droit`).toBe(403);
        expect((await appeler(f, r.fichier, m, r.params, "presque")).status, `${m} avec tous les droits sauf ${r.droit}`).toBe(403);
        if (r.client) {
          const dehors = { ...r.params, id: "boulangerie-essai" };
          expect((await appeler(f, r.fichier, m, dehors, "limite")).status, `${m} hors périmètre`).toBe(404);
        }
        expect(appelsAtelier, `${m} : aucun appel à l'atelier sur un refus`).toEqual([]);
      }
    });
  }
});
