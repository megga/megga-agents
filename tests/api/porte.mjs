// L'essai de bout en bout de l'entrée par API, côté porte : le vrai code de la porte (routes, annuaire,
// objet du client) devant un vrai agent qui tourne sur ce poste. Seul le démarrage du conteneur est simulé :
// l'objet parle à l'agent local au lieu d'un conteneur Cloudflare.
//   node --import ./test/bouchons/enregistrer.js ../tests/api/porte.mjs <port de l'agent> <clé> <client>
// Écrit une ligne JSON par requête : {statut, retry, corps}.
import { readFileSync } from "node:fs";
import { DatabaseSync } from "node:sqlite";
import { AgentEurope } from "../../porte/src/agent.js";
import { inscrire } from "../../porte/src/annuaire.js";
import { recevoir } from "../../porte/src/index.js";

const [port, cle, client] = process.argv.slice(2);

function d1() {
  const db = new DatabaseSync(":memory:");
  for (const f of ["0001_annuaire.sql", "0002_versions.sql", "0003_sans_whatsapp.sql"])
    db.exec(readFileSync(new URL(`../../porte/migrations/${f}`, import.meta.url), "utf8"));
  const requete = (sql, args = []) => ({
    bind: (...a) => requete(sql, a),
    first: async () => db.prepare(sql).get(...args) ?? null,
    all: async () => ({ results: db.prepare(sql).all(...args) }),
    run: async () => db.prepare(sql).run(...args),
  });
  return { prepare: (sql) => requete(sql) };
}

// Le conteneur du client : l'agent local.
const stock = new Map();
const ctx = {
  id: { name: client },
  blockConcurrencyWhile: (f) => f(),
  storage: { get: async (k) => stock.get(k), put: async (k, v) => stock.set(k, v), delete: async (k) => stock.delete(k), getAlarm: async () => null, setAlarm: async () => {} },
  container: {
    running: true,
    setInactivityTimeout: async () => {},
    getTcpPort: () => ({
      fetch: async (u, o) => {
        const r = new Request(u, o);
        const url = new URL(r.url);
        url.protocol = "http:";
        url.host = `127.0.0.1:${port}`;
        const corps = ["GET", "HEAD"].includes(r.method) ? undefined : await r.arrayBuffer();
        return fetch(url, { method: r.method, headers: r.headers, body: corps });
      },
    }),
  },
};
const objet = new AgentEurope(ctx, { ADMIN_TOKEN: "admin" });
const annuaire = d1();
await inscrire(annuaire, client, { version: 1, config: { version: 1, id: client, zone: "europe", nom_agent: "Alix" } });
const env = { ADMIN_TOKEN: "admin", ANNUAIRE: annuaire, AGENTS_EUROPE: { jurisdiction: () => ({ getByName: () => objet }) } };

async function envoyer(corps, autreCle = cle) {
  const texte = JSON.stringify(corps);
  const r = await recevoir(
    new Request(`https://api.megga.ai/api/${client}/messages`, {
      method: "POST",
      body: texte,
      headers: { authorization: `Bearer ${autreCle}`, "content-type": "application/json", "content-length": String(Buffer.byteLength(texte)) },
    }),
    env,
  );
  console.log(JSON.stringify({ statut: r.status, retry: r.headers.get("retry-after"), corps: await r.json() }));
}

await envoyer({ personne: "patient-42", texte: "Bonjour, je m'appelle Jeanne." });
await envoyer({ personne: "patient-42", texte: "Comment je m'appelle ?" });
await envoyer({ personne: "+41791234567", texte: "Bonjour" });
await envoyer({ personne: "patient-42", texte: "Bonjour" }, "mga_" + "x".repeat(43));
await envoyer({ personne: "patient-43", texte: "Bonjour" });
await envoyer({ personne: "patient-44", texte: "Bonjour" });
