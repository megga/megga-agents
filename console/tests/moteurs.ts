// Les moteurs des essais : SQLite en mémoire, toujours ; Postgres, quand CONSOLE_BASE_ESSAI_URL nomme un serveur d'essai
// (jamais la production). Chaque base Postgres d'essai est une base neuve de ce serveur, au nom tiré au hasard, supprimée
// par fermer(). Les bases ouvertes pendant un essai se ferment après lui (tests/apres.ts).
import { randomBytes } from "node:crypto";
import { Client } from "pg";
import type { Base } from "@/lib/donnees/base";
import { basePostgres } from "@/lib/donnees/postgres";
import { baseSqlite } from "@/lib/donnees/sqlite";

export type Moteur = "sqlite" | "postgres";

/** Les moteurs sur lesquels jouer un essai : SQLite, et Postgres si CONSOLE_BASE_ESSAI_URL est posée. */
export function moteursEssai(): Moteur[] {
  return process.env.CONSOLE_BASE_ESSAI_URL ? ["sqlite", "postgres"] : ["sqlite"];
}

/** Le moteur des essais qui n'en jouent qu'un : CONSOLE_ESSAI_MOTEUR, SQLite par défaut. */
export function moteurParDefaut(): Moteur {
  const m = process.env.CONSOLE_ESSAI_MOTEUR ?? "sqlite";
  if (m !== "sqlite" && m !== "postgres") throw new Error(`CONSOLE_ESSAI_MOTEUR inconnu : ${m}`);
  return m;
}

function serveurEssai(): string {
  const url = process.env.CONSOLE_BASE_ESSAI_URL;
  if (!url) throw new Error("CONSOLE_BASE_ESSAI_URL manquante : les essais sur Postgres demandent un serveur d'essai");
  return url;
}

const ouvertes = new Set<{ fermer(): Promise<void> }>();

/** Ferme ce que les essais ont ouvert et pas encore fermé. */
export async function fermerBasesOuvertes(): Promise<void> {
  const liste = [...ouvertes];
  ouvertes.clear();
  await Promise.all(liste.map((b) => b.fermer().catch((e: unknown) => console.error("fermeture d'une base d'essai :", e))));
}

/**
 * Une base Postgres neuve sur le serveur d'essai : son adresse, et de quoi la supprimer (les connexions encore ouvertes
 * dessus sont coupées). Supprimée après l'essai si personne ne l'a fait avant.
 */
export async function nouvelleBasePostgres(): Promise<{ url: string; fermer(): Promise<void> }> {
  const serveur = serveurEssai();
  const nom = `essai_${randomBytes(8).toString("hex")}`;
  await surServeur(serveur, `CREATE DATABASE ${nom}`);
  const url = new URL(serveur);
  url.pathname = `/${nom}`;
  let supprimee = false;
  const neuve = {
    url: url.toString(),
    async fermer() {
      ouvertes.delete(neuve);
      if (supprimee) return;
      supprimee = true;
      await surServeur(serveur, `DROP DATABASE IF EXISTS ${nom} WITH (FORCE)`);
    },
  };
  ouvertes.add(neuve);
  return neuve;
}

async function surServeur(serveur: string, sql: string): Promise<void> {
  const c = new Client({ connectionString: serveur });
  await c.connect();
  try {
    await c.query(sql);
  } finally {
    await c.end();
  }
}

/** Une base vide du moteur : SQLite en mémoire ; Postgres, une base neuve du serveur d'essai, supprimée par fermer(). */
export async function baseVide(moteur: Moteur): Promise<Base> {
  if (moteur === "sqlite") {
    const b = baseSqlite(":memory:");
    ouvertes.add(b);
    return b;
  }
  const neuve = await nouvelleBasePostgres();
  ouvertes.delete(neuve);
  const b = basePostgres(neuve.url);
  const avecSuppression: Base = {
    ...b,
    async fermer() {
      ouvertes.delete(avecSuppression);
      await b.fermer();
      await neuve.fermer();
    },
  };
  ouvertes.add(avecSuppression);
  return avecSuppression;
}
