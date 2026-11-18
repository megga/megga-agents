import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { DatabaseSync } from "node:sqlite";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { TA } from "@/lib/admin/textes";

// La commande telle que package.json la lance (npm run admin:inviter -- <courriel>), sous Node, sans compilation.
const CONSOLE = join(__dirname, "../..");
const script = (JSON.parse(readFileSync(join(CONSOLE, "package.json"), "utf8")) as { scripts: Record<string, string> }).scripts["admin:inviter"];
const ARGUMENTS = script.split(" ").slice(1); // sans « node »

let dossier: string;
beforeEach(() => {
  dossier = mkdtempSync(join(tmpdir(), "admin-inviter-"));
});
afterEach(() => rmSync(dossier, { recursive: true, force: true }));

function lancer(...args: string[]): { code: number; sortie: string; erreurs: string } {
  const env: NodeJS.ProcessEnv = { ...process.env, CONSOLE_BASE: join(dossier, "b.sqlite") };
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
  it("imprime le lien d'une invitation superadmin, et elle est en base", () => {
    const r = lancer("Chef@Megga.test");
    expect(r.code).toBe(0);
    expect(r.sortie).toMatch(/^http:\/\/localhost:3000\/admin\/invitation\/[A-Za-z0-9_-]{43}\n$/);
    const db = new DatabaseSync(join(dossier, "b.sqlite"));
    expect(db.prepare("SELECT courriel, role, externe, perimetre, fin_acces FROM admin_invitation").all())
      .toEqual([{ courriel: "chef@megga.test", role: "superadmin", externe: 0, perimetre: null, fin_acces: null }]);
    db.close();
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
