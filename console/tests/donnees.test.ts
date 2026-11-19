import { Client, type Pool } from "pg";
import { describe, expect, it } from "vitest";
import { baseVide, moteursEssai } from "./moteurs";

// L'interface de base, jouée sur chaque moteur d'essai (Postgres seulement si CONSOLE_BASE_ESSAI_URL est posée).

const attendre = (ms: number) => new Promise((r) => setTimeout(r, ms));

describe.each(moteursEssai())("la base, sous %s", (moteur) => {
  it("écrit puis relit une ligne", async () => {
    const b = await baseVide(moteur);
    await b.executer("CREATE TABLE t (id TEXT PRIMARY KEY, n INTEGER)");
    expect(await b.ecrire("INSERT INTO t VALUES (?, ?)", "a", 1)).toEqual({ changements: 1 });
    expect(await b.un("SELECT n FROM t WHERE id = ?", "a")).toEqual({ n: 1 });
    expect(await b.un("SELECT n FROM t WHERE id = ?", "z")).toBeUndefined();
    expect(await b.tous("SELECT id, n FROM t")).toEqual([{ id: "a", n: 1 }]);
  });

  it("annule une transaction qui échoue", async () => {
    const b = await baseVide(moteur);
    await b.executer("CREATE TABLE t (id TEXT PRIMARY KEY)");
    await expect(
      b.transaction(async (tx) => {
        await tx.ecrire("INSERT INTO t VALUES (?)", "a");
        throw new Error("échec voulu");
      }),
    ).rejects.toThrow("échec voulu");
    expect(await b.tous("SELECT id FROM t")).toEqual([]);
  });

  it("sérialise une écriture lancée pendant une transaction", async () => {
    const b = await baseVide(moteur);
    await b.executer("CREATE TABLE t (id TEXT PRIMARY KEY)");
    const dedans = b.transaction(async (tx) => {
      await tx.ecrire("INSERT INTO t VALUES (?)", "a");
      await attendre(20);
      throw new Error("échec voulu");
    });
    await attendre(5); // la transaction a écrit a et attend
    const dehors = b.ecrire("INSERT INTO t VALUES (?)", "b");
    const [r1, r2] = await Promise.allSettled([dedans, dehors]);
    expect(r1.status).toBe("rejected");
    expect(r2).toEqual({ status: "fulfilled", value: { changements: 1 } });
    expect(await b.tous("SELECT id FROM t ORDER BY id")).toEqual([{ id: "b" }]);
  });

  it("ne numérote pas un ? entre apostrophes", async () => {
    const b = await baseVide(moteur);
    expect(await b.un("SELECT '?' AS q, ? AS v", "x")).toEqual({ q: "?", v: "x" });
  });

  it("rend le nombre de lignes touchées", async () => {
    const b = await baseVide(moteur);
    await b.executer("CREATE TABLE t (id TEXT PRIMARY KEY, n INTEGER)");
    await b.ecrire("INSERT INTO t VALUES (?, ?), (?, ?)", "a", 1, "b", 1);
    expect(await b.ecrire("UPDATE t SET n = ? WHERE n = ?", 2, 1)).toEqual({ changements: 2 });
    expect(await b.un("SELECT COUNT(*) AS n, SUM(n) AS s FROM t")).toEqual({ n: 2, s: 4 });
  });

  it.runIf(moteur === "postgres")("lit un horodatage en texte ISO", async () => {
    const b = await baseVide(moteur);
    await b.executer("CREATE TABLE h (quand timestamptz, sans timestamp)");
    await b.ecrire("INSERT INTO h VALUES (?, ?)", "2026-11-18T10:00:00Z", "2026-11-18 10:00:00");
    expect(await b.un("SELECT quand, sans FROM h")).toEqual({ quand: "2026-11-18T10:00:00.000Z", sans: "2026-11-18T10:00:00.000Z" });
  });

  it.runIf(moteur === "postgres")("survit à une connexion coupée", async () => {
    const b = await baseVide(moteur);
    expect(await b.un("SELECT 1 AS n")).toEqual({ n: 1 }); // une connexion reste ouverte dans le pool
    const autre = new Client({ connectionString: (b.pourAuth() as Pool).options.connectionString });
    await autre.connect();
    try {
      const { rowCount } = await autre.query(
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = current_database() AND pid <> pg_backend_pid()",
      );
      expect(rowCount).toBeGreaterThan(0);
    } finally {
      await autre.end();
    }
    expect(await b.un("SELECT 1 AS n")).toEqual({ n: 1 });
  });
});
