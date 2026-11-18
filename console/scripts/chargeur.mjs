// Fait tourner un script TypeScript de la console sous Node, sans compilation ni dépendance (npm run admin:inviter).
// Node retire lui-même les types (--experimental-transform-types) ; ce chargeur ne fait que la résolution que Next.js
// et Vitest font d'habitude : « @/x » vers console/src/x, et un chemin relatif sans extension complété sous console/,
// en essayant "", .ts, .tsx, /index.ts. Tout le reste passe à la résolution de Node (--conditions=react-server rend
// server-only vide). Les fichiers .ts de la console sont des modules ES.
import { statSync } from "node:fs";
import { registerHooks } from "node:module";
import { dirname, join, resolve, sep } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const CONSOLE = fileURLToPath(new URL("..", import.meta.url));
const SRC = join(CONSOLE, "src");
const SUFFIXES = ["", ".ts", ".tsx", "/index.ts"];

const ici = (chemin) => chemin.startsWith(CONSOLE) && !chemin.includes(`${sep}node_modules${sep}`);

function fichier(base) {
  for (const s of SUFFIXES) {
    try {
      if (statSync(base + s).isFile()) return base + s;
    } catch {
      // pas celui-là
    }
  }
  return null;
}

function cheminVoulu(specifier, parentURL) {
  if (specifier.startsWith("@/")) return join(SRC, specifier.slice(2));
  if (!parentURL?.startsWith("file:") || !(specifier.startsWith("./") || specifier.startsWith("../"))) return null;
  const parent = fileURLToPath(parentURL);
  return ici(parent) ? resolve(dirname(parent), specifier) : null;
}

/** Un fichier .ts de la console est un module ES (le package.json de la console ne dit pas « type »). */
function avecFormat(r) {
  const chemin = r.url.startsWith("file:") ? fileURLToPath(r.url) : "";
  return chemin.endsWith(".ts") && ici(chemin) ? { ...r, format: "module-typescript" } : r;
}

registerHooks({
  resolve(specifier, context, nextResolve) {
    const voulu = cheminVoulu(specifier, context.parentURL);
    const trouve = voulu && fichier(voulu);
    if (trouve) return avecFormat({ url: pathToFileURL(trouve).href, shortCircuit: true });
    return avecFormat(nextResolve(specifier, context));
  },
});
