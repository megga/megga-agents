// Lot 6.3 : le pilote d'une installation hors Cloudflare passe par la porte jusqu'à l'atelier.
import assert from "node:assert/strict";
import { test } from "node:test";
import { Atelier } from "../src/agent.js";
import { pilotageBienForme, recevoir } from "../src/index.js";

const NONCE = "0123456789abcdef0123456789abcdef";
const SIGNATURE = "A".repeat(86); // 64 octets en base64 sans remplissage
const entetes = (autres = {}) => ({
  "x-megga-installation": "exemple",
  "x-megga-heure": String(Math.floor(Date.now() / 1000)),
  "x-megga-nonce": NONCE,
  "x-megga-signature": SIGNATURE,
  "content-type": "application/json",
  ...autres,
});

// Une fausse liaison vers l'atelier : elle note ce qui lui parvient.
function env(journal) {
  return {
    ADMIN_TOKEN: "admin",
    ATELIER: {
      jurisdiction: (j) => ({
        getByName: (nom) => ({
          fetch: async (r) => {
            journal.push({ j, nom, chemin: new URL(r.url).pathname, signature: r.headers.get("x-megga-signature"), corps: await r.text() });
            return Response.json({ heure: 1, ordres: [] });
          },
          poserSecrets: async (s) => Object.keys(s),
        }),
      }),
    },
  };
}

const releve = (e, h = entetes(), corps = '{"pilotage":"suivi"}', methode = "POST") =>
  recevoir(
    new Request("https://porte/pilotage/releve", {
      method: methode,
      headers: methode === "POST" ? { "content-length": String(new TextEncoder().encode(corps).length), ...h } : h,
      body: methode === "POST" ? corps : undefined,
    }),
    e,
  );

test("un relevé signé et récent est transmis tel quel à l'atelier, qui vérifie la signature", async () => {
  const journal = [];
  const r = await releve(env(journal));
  assert.equal(r.status, 200);
  assert.deepEqual(await r.json(), { heure: 1, ordres: [] });
  assert.deepEqual(journal, [{ j: "eu", nom: "megga", chemin: "/pilotage/releve", signature: SIGNATURE, corps: '{"pilotage":"suivi"}' }]);
});

test("sans requête signée, récente et bien formée, l'atelier n'est pas réveillé", async () => {
  const journal = [];
  const e = env(journal);
  const vieille = String(Math.floor(Date.now() / 1000) - 400);
  const mauvaises = [
    { "x-megga-signature": "" },
    { "x-megga-signature": "court" },
    { "x-megga-installation": "Pas Un Id" },
    { "x-megga-nonce": "abc" },
    { "x-megga-heure": vieille },
    { "x-megga-heure": "maintenant" },
  ];
  for (const m of mauvaises) assert.equal((await releve(e, entetes(m))).status, 401, JSON.stringify(m));
  assert.equal((await releve(e, entetes(), undefined, "GET")).status, 405);
  assert.equal((await releve(e, entetes({ "content-length": String(300 * 1024) }), "x".repeat(300 * 1024))).status, 413);
  // un corps en flux, sans longueur annoncée : refusé avant l'atelier
  const flux = new ReadableStream({ start: (c) => (c.enqueue(new TextEncoder().encode("x".repeat(1024))), c.close()) });
  const r = await recevoir(new Request("https://porte/pilotage/releve", { method: "POST", headers: entetes(), body: flux, duplex: "half" }), e);
  assert.equal(r.status, 411);
  assert.equal((await releve({ ...e, ATELIER: undefined })).status, 503);
  assert.deepEqual(journal, []);
  // à 5 minutes près
  const h = new Headers(entetes({ "x-megga-heure": "1000" }));
  assert.equal(pilotageBienForme(h, 1_299_000), true);
  assert.equal(pilotageBienForme(h, 1_301_000), false);
});

function ctx({ running = false, secrets = {} } = {}) {
  const stock = new Map([["secrets", secrets]]);
  const journal = [];
  const c = {
    running,
    start: (o) => {
      journal.push(["start", o]);
      c.running = true;
    },
    destroy: async () => {
      c.running = false;
    },
    setInactivityTimeout: async () => {},
    getTcpPort: () => ({ fetch: async () => new Response("ok") }),
  };
  return { ctx: { id: { name: "megga" }, blockConcurrencyWhile: (f) => f(), storage: { get: async (k) => stock.get(k), put: async (k, v) => stock.set(k, v) }, container: c }, journal, stock };
}

test("l'atelier range sa clé de pilotage, sans la rendre, et la remet à son conteneur", async () => {
  const a = ctx({ secrets: { DATABASE_URL: "postgresql://atelier" } });
  const atelier = new Atelier(a.ctx, { ADMIN_TOKEN: "admin", PORTE_URL: "https://porte" });
  assert.deepEqual(await atelier.poserSecrets({ PILOTAGE_CLE: "cle-privee", META_TOKEN: "non" }), ["PILOTAGE_CLE"]);
  assert.deepEqual(a.stock.get("secrets"), { DATABASE_URL: "postgresql://atelier", PILOTAGE_CLE: "cle-privee" });
  await atelier.demarrer();
  const [[, o]] = a.journal;
  assert.equal(o.env.PILOTAGE_CLE, "cle-privee");
  assert.equal(o.env.META_TOKEN, undefined);
  // la route d'administration ne rend que les noms
  const r = await recevoir(
    new Request("https://porte/admin/atelier/secrets", { method: "PUT", body: JSON.stringify({ PILOTAGE_CLE: "cle-privee" }), headers: { authorization: "Bearer admin" } }),
    env([]),
  );
  assert.equal(await r.text(), "rangés : PILOTAGE_CLE");
});
