import { Pool, types, type PoolClient, type QueryResult } from "pg";
import type { Base, Ligne, Valeur } from "./base";

// Le moteur Postgres (pg) : un Pool de cinq connexions. Le SQL arrive avec des « ? », numérotés ici en $1, $2…
// Toutes les transactions de la console passent l'une après l'autre (un verrou consultatif pris dans la transaction),
// comme sous SQLite. Les horodatages se lisent en texte ISO UTC, int8 et numeric en nombre, comme sous SQLite ; ces
// lectures valent pour les requêtes de la console seulement, Better Auth garde celles de pg sur le même Pool.

/** Le verrou consultatif que prend chaque transaction de la console. */
const VERROU = 4247;

const OID = { int8: 20, numeric: 1700, timestamp: 1114, timestamptz: 1184 } as const;

const enDate = types.getTypeParser(OID.timestamptz) as (texte: string) => Date;

/** Les lectures de la console : horodatages en texte ISO UTC (un timestamp sans fuseau est en UTC), int8 et numeric en nombre. */
const LECTURES = {
  getTypeParser: ((oid: number, format?: "text" | "binary") => {
    if (oid === OID.timestamptz) return (t: string) => enDate(t).toISOString();
    if (oid === OID.timestamp) return (t: string) => enDate(`${t}+00`).toISOString();
    if (oid === OID.int8 || oid === OID.numeric) return (t: string) => Number(t);
    return types.getTypeParser(oid, format);
  }) as typeof types.getTypeParser,
};

/** Les « ? » deviennent $1, $2…, sauf entre apostrophes (une chaîne) ou entre guillemets (un nom). */
export function numeroter(sql: string): string {
  let n = 0;
  let dans: string | null = null;
  let sortie = "";
  for (const c of sql) {
    if (dans) {
      if (c === dans) dans = null;
      sortie += c;
    } else if (c === "'" || c === '"') {
      dans = c;
      sortie += c;
    } else sortie += c === "?" ? `$${++n}` : c;
  }
  return sortie;
}

/**
 * Une connexion coupée avant que la requête parte : le serveur l'a fermée (57P01, Neon qui endort son calcul), ou pg l'a déjà
 * vue tomber. La requête n'a pas été jouée : un nouvel essai, sur une autre connexion, ne la joue pas deux fois.
 */
function coupee(e: unknown): boolean {
  const x = e as { code?: string; message?: string } | null;
  return x?.code === "57P01" || /not queryable/.test(x?.message ?? "");
}

type Cible = Pick<Pool | PoolClient, "query">;

async function jouer(cible: Cible, sql: string, params: Valeur[], reessayer: boolean): Promise<QueryResult> {
  const config = { text: numeroter(sql), values: params, types: LECTURES };
  try {
    return await cible.query(config);
  } catch (e) {
    if (!reessayer || !coupee(e)) throw e;
    return cible.query(config);
  }
}

function operations(cible: Cible, reessayer: boolean) {
  return {
    un: async <T extends Ligne>(sql: string, ...params: Valeur[]) => (await jouer(cible, sql, params, reessayer)).rows[0] as T | undefined,
    tous: async <T extends Ligne>(sql: string, ...params: Valeur[]) => (await jouer(cible, sql, params, reessayer)).rows as T[],
    ecrire: async (sql: string, ...params: Valeur[]) => ({ changements: (await jouer(cible, sql, params, reessayer)).rowCount ?? 0 }),
    executer: async (sql: string) => {
      await jouer(cible, sql, [], reessayer);
    },
  };
}

export function basePostgres(url: string): Base {
  const pool = new Pool({ connectionString: url, max: 5 });
  // Une connexion du pool coupée (Neon qui s'endort) : notée, sans tuer le processus ; le pool la remplace.
  pool.on("error", (e) => console.error("base postgres, connexion perdue :", e.message));

  let fermee: Promise<void> | null = null;
  const fermer = () => (fermee ??= pool.end());

  async function ouvrir(): Promise<PoolClient> {
    const client = await pool.connect();
    try {
      await client.query("BEGIN");
      await client.query(`SELECT pg_advisory_xact_lock(${VERROU})`);
      return client;
    } catch (e) {
      client.release(true);
      throw e;
    }
  }

  async function transaction<T>(f: (tx: Base) => Promise<T>): Promise<T> {
    let client: PoolClient;
    try {
      client = await ouvrir();
    } catch (e) {
      if (!coupee(e)) throw e;
      client = await ouvrir();
    }
    const tx: Base = { dialecte: "postgres", ...operations(client, false), transaction: (g) => g(tx), pourAuth: () => pool, fermer };
    let casse: Error | undefined;
    try {
      const r = await f(tx);
      await client.query("COMMIT");
      return r;
    } catch (e) {
      await client.query("ROLLBACK").catch((x: Error) => {
        casse = x;
      });
      throw e;
    } finally {
      client.release(casse);
    }
  }

  return { dialecte: "postgres", ...operations(pool, true), transaction, pourAuth: () => pool, fermer };
}
