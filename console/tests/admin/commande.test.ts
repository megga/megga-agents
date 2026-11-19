import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { TA } from "@/lib/admin/textes";
import type { Base } from "@/lib/donnees/base";
import { basePostgres } from "@/lib/donnees/postgres";
import { baseSqlite } from "@/lib/donnees/sqlite";
import { moteurParDefaut, nouvelleBasePostgres } from "../moteurs";

// La commande telle que package.json la lance (npm run admin:inviter -- <courriel>), sous Node, sans compilation, sur le
// moteur des essais : un fichier SQLite (CONSOLE_BASE), ou une base Postgres neuve du serveur d'essai (CONSOLE_BASE_URL).
const CONSOLE = join(__dirname, "../..");
const script = (JSON.parse(readFileSync(join(CONSOLE, "package.json"), "utf8")) as { scripts: Record<string, string> }).scripts["admin:inviter"];
const ARGUMENTS = script.split(" ").slice(1); // sans « node »

let dossier: string;
let postgres: string | null;
beforeEach(async () => {
  dossier = mkdtempSync(join(tmpdir(), "admin-inviter-"));
  postgres = moteurParDefaut() === "postgres" ? (await nouvelleBasePostgres()).url : null; // supprimée après l'essai
});
afterEach(() => rmSync(dossier, { recursive: true, force: true }));

/** La base que la commande a écrite. */
async function lire<T>(f: (b: Base) => Promise<T>): Promise<T> {
  const b = postgres ? basePostgres(postgres) : baseSqlite(join(dossier, "b.sqlite"));
  try {
    return await f(b);
  } finally {
    await b.fermer();
  }
}

function lancer(...args: string[]): { code: number; sortie: string; erreurs: string } {
  const env: NodeJS.ProcessEnv = { ...process.env, CONSOLE_BASE: join(dossier, "b.sqlite") };
  if (postgres) env.CONSOLE_BASE_URL = postgres;
  else delete env.CONSOLE_BASE_URL;
  delete env.BETTER_AUTH_URL;
  try {
    const sortie = execFileSync(process.execPath, [...ARGUMENTS, ...args], { cwd: CONSOLE, env, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] });
    return { code: 0, sortie, erreurs: "" };
  } catch (e) {
    const x = e as { status: number; stdout: string; stderr: string };
    return { code: x.status, sortie: x.stdout, erreurs: x.stderr };
  }
}

describe("npm run admin:inviter", () => {
  it("imprime le lien d'une invitation superadmin, et elle est en base", async () => {
    const r = lancer("Chef@Megga.test");
    expect(r.code).toBe(0);
    expect(r.sortie).toMatch(/^http:\/\/localhost:3000\/admin\/invitation\/[A-Za-z0-9_-]{43}\n$/);
    expect(await lire((db) => db.tous("SELECT courriel, role, externe, perimetre, fin_acces FROM admin_invitation")))
      .toEqual([{ courriel: "chef@megga.test", role: "superadmin", externe: 0, perimetre: null, fin_acces: null }]);
  });

  it("note son geste au journal, sans le jeton", async () => {
    const r = lancer("chef@megga.test");
    const jeton = r.sortie.trim().split("/").at(-1)!;
    const { id, lignes, tout } = await lire(async (db) => ({
      id: (await db.un<{ id: string }>("SELECT id FROM admin_invitation"))!.id,
      lignes: await db.tous("SELECT qui, courriel, action, cible, resultat, detail FROM admin_journal"),
      tout: await db.tous("SELECT * FROM admin_journal"),
    }));
    expect(lignes).toEqual([{ qui: null, courriel: null, action: "invitations.commande", cible: `invitation:${id}`, resultat: "ok",
      detail: JSON.stringify({ courriel: "chef@megga.test" }) }]);
    expect(JSON.stringify(tout)).not.toContain(jeton);
  });

  it("sans courriel, ou avec un courriel refusé : le message sur la sortie d'erreur, code 1", () => {
    const sans = lancer();
    expect(sans.code).toBe(1);
    expect(sans.erreurs).toContain(TA.usageCommande);
    expect(sans.sortie).toBe("");
    const refuse = lancer("chef.megga.test");
    expect(refuse.code).toBe(1);
    expect(refuse.erreurs).toContain(TA.courrielInvalide);
  });
});
