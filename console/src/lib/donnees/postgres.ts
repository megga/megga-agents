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

/** Attendre une connexion du Pool, un verrou, ou une transaction restée ouverte : jamais sans fin, une erreur au bout. */
const DELAIS = { connexionMs: 5_000, verrou: "5s", transactionInactive: "15s" } as const;

/**
 * pg traite déjà « prefer », « require » et « verify-ca » comme « verify-full » et l'écrit à chaque connexion. On écrit
 * « verify-full » nous-mêmes, ce qui ne change rien au comportement et fait taire l'avertissement. L'adresse n'est jamais
 * journalisée : une adresse qu'on ne sait pas lire est rendue telle quelle.
 */
export function normaliserSsl(url: string): string {
  return url.replace(/([?&]sslmode=)(?:require|prefer|verify-ca)(?=&|$)/, "$1verify-full");
}

export function basePostgres(url: string): Base {
  const pool = new Pool({ connectionString: normaliserSsl(url), max: 5, connectionTimeoutMillis: DELAIS.connexionMs });
  // Une connexion du pool coupée (Neon qui s'endort) : notée, sans tuer le processus ; le pool la remplace.
  pool.on("error", (e) => console.error("base postgres, connexion perdue :", e.message));

  let fermee: Promise<void> | null = null;
  const fermer = () => (fermee ??= pool.end());

  /**
   * Une connexion sortie du Pool pour une transaction. Le Pool n'écoute plus ses erreurs tant qu'elle est sortie : sans
   * écouteur, une coupure (Neon, pg_terminate_backend) tuerait le processus. L'écouteur note la panne, la requête en cours ou
   * la suivante échoue, et la connexion est jetée à sa remise (rendre(erreur)).
   */
  async function sortir(): Promise<{ client: PoolClient; rendre: (e?: Error) => void; panne: () => Error | undefined }> {
    const client = await pool.connect();
    let perdue: Error | undefined;
    const ecouteur = (e: Error) => {
      perdue ??= e;
      console.error("base postgres, connexion perdue pendant une transaction :", e.message);
    };
    client.on("error", ecouteur);
    return {
      client,
      panne: () => perdue,
      rendre: (e) => {
        client.removeListener("error", ecouteur);
        client.release(e ?? perdue);
      },
    };
  }

  async function ouvrir(): Promise<Awaited<ReturnType<typeof sortir>>> {
    const sortie = await sortir();
    try {
      await sortie.client.query("BEGIN");
      await sortie.client.query(`SET LOCAL lock_timeout = '${DELAIS.verrou}'`);
      await sortie.client.query(`SET LOCAL idle_in_transaction_session_timeout = '${DELAIS.transactionInactive}'`);
      await sortie.client.query(`SELECT pg_advisory_xact_lock(${VERROU})`);
      return sortie;
    } catch (e) {
      sortie.rendre(e instanceof Error ? e : new Error(String(e)));
      throw e;
    }
  }

  async function transaction<T>(f: (tx: Base) => Promise<T>): Promise<T> {
    let sortie: Awaited<ReturnType<typeof sortir>>;
    try {
      sortie = await ouvrir();
    } catch (e) {
      if (!coupee(e)) throw e;
      sortie = await ouvrir();
    }
    const { client } = sortie;
    const tx: Base = { dialecte: "postgres", ...operations(client, false), transaction: (g) => g(tx), pourAuth: () => pool, fermer };
    let casse: Error | undefined;
    try {
      const r = await f(tx);
      const panne = sortie.panne();
      if (panne) throw panne; // une coupure pendant f, sans requête en cours pour la voir : rien n'est validé
      const fin = await client.query("COMMIT");
      // Sur une transaction en erreur, Postgres répond « ROLLBACK » à COMMIT, sans lever d'erreur : rien n'est validé.
      if (fin.command !== "COMMIT") throw new Error("base postgres, la transaction n'a pas été validée");
      return r;
    } catch (e) {
      casse = sortie.panne();
      if (!casse) {
        await client.query("ROLLBACK").catch((x: Error) => {
          casse = x;
        });
      }
      throw e;
    } finally {
      sortie.rendre(casse);
    }
  }

  return { dialecte: "postgres", ...operations(pool, true), transaction, pourAuth: () => pool, fermer };
}
