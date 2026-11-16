// La vraie gestion du site de Four Seasons (son _worker.js), servie en local pour le banc de parité : la donnée
// de son dépôt, GitHub et R2 simulés comme dans les essais d'Alix (tests/gestion-faux.mjs). Rien ne sort de la
// machine. Le socle l'appelle en HTTP, comme il appellerait le vrai site.
//
//   node parite/gestion.mjs <dépôt fourseasonsproperties> <port>
//
// Écrit « pret <port> » quand il écoute. Une instance par cas : chaque cas part de la même donnée.
import http from "node:http";
import path from "node:path";
import { pathToFileURL } from "node:url";

const [racine, port] = process.argv.slice(2);
const SITE = path.join(racine, "templates", "myproperties");
const worker = (await import(pathToFileURL(path.join(SITE, "_worker.js")))).default;
const { fabriquerHash } = await import(pathToFileURL(path.join(SITE, "gestion", "serveur.mjs")));
const { fauxGithub, fauxR2 } = await import(pathToFileURL(path.join(racine, "tests", "gestion-faux.mjs")));

export const CLE = "k".repeat(40);
fauxGithub(racine); // remplace fetch pour l'API de GitHub
const envSite = {
  GESTION_COMPTES: JSON.stringify([{ courtier: "gregory-lyonnet", email: "gl@fourseasonsgroup.ch", role: "admin", hash: await fabriquerHash("essai") }]),
  GESTION_SECRET: "s".repeat(40), GESTION_GITHUB_TOKEN: "jeton", GESTION_ALIX_CLE: CLE,
  GESTION_ALIX_COMPTES: "gl@fourseasonsgroup.ch", MYPROPERTIES_ACCES: "preversion", PHOTOS: fauxR2(),
  ASSETS: { fetch: () => new Response("absent", { status: 404 }) },
  ALIX: { fetch: async () => new Response("ignoré", { status: 202 }) },
};

http.createServer(async (req, res) => {
  const morceaux = [];
  for await (const m of req) morceaux.push(m);
  const corps = Buffer.concat(morceaux);
  const entetes = new Headers();
  for (const [k, v] of Object.entries(req.headers)) if (typeof v === "string") entetes.set(k, v);
  try {
    const r = await worker.fetch(new Request(`https://fourseasonsproperties.ch${req.url}`, {
      method: req.method, headers: entetes, body: ["GET", "HEAD"].includes(req.method) ? undefined : corps,
    }), envSite, { waitUntil: () => {} });
    const sortie = Buffer.from(await r.arrayBuffer());
    res.writeHead(r.status, Object.fromEntries(r.headers));
    res.end(sortie);
  } catch (e) {
    res.writeHead(500, { "content-type": "application/json" });
    res.end(JSON.stringify({ erreur: String(e?.message ?? e).slice(0, 200) }));
  }
}).listen(Number(port), "127.0.0.1", () => console.log(`pret ${port}`));
