import "server-only";
import { creerTablesAdmin } from "./admin/tables";
import { migrer } from "./auth";
import { ouvrirBase, type Base } from "./donnees/base";

export { cheminBase } from "./donnees/base";

// La base de la console : les comptes de Better Auth, les agents de chaque compte et les tables de l'admin.
// SQLite, intégré à Node, en local et dans les essais ; Postgres quand CONSOLE_BASE_URL est posée (src/lib/donnees).

const globale = globalThis as unknown as { baseConsole?: Base; baseConsolePrete?: Promise<Base> };

/** Les tables de la console sur une base ouverte : les agents de chaque compte, puis celles de l'admin. */
export async function preparer(b: Base): Promise<void> {
  await b.executer(`CREATE TABLE IF NOT EXISTS agent (
    id TEXT PRIMARY KEY,
    utilisateur TEXT NOT NULL,
    prenom TEXT NOT NULL,
    metier TEXT NOT NULL,
    couleur INTEGER NOT NULL DEFAULT 0,
    yeux INTEGER NOT NULL DEFAULT 0,
    epingle INTEGER NOT NULL DEFAULT 0,
    cree_le TEXT NOT NULL
  )`);
  await b.executer("CREATE INDEX IF NOT EXISTS agent_utilisateur ON agent (utilisateur)");
  await creerTablesAdmin(b);
}

/** La base de la console, ouverte une fois ; ses tables sont prêtes après pret(). */
export function donnees(): Base {
  globale.baseConsole ??= ouvrirBase();
  return globale.baseConsole;
}

/** La base de la console, Better Auth migré et ses tables créées : à attendre avant toute requête. */
export function pret(): Promise<Base> {
  globale.baseConsolePrete ??= (async () => {
    const b = donnees();
    await migrer();
    await preparer(b);
    return b;
  })().catch((e: unknown) => {
    globale.baseConsolePrete = undefined; // un échec n'est pas gardé : la prochaine requête réessaie
    throw e;
  });
  return globale.baseConsolePrete;
}
