import assert from "node:assert/strict";
import { test } from "node:test";
import { AgentEurope, jetonInterne } from "../src/agent.js";

// Un faux objet : stockage avec alarme, conteneur qui répond aux routes internes.
function objet(reponse = { prochain: null }) {
  const journal = [];
  const stock = new Map();
  let alarme = null;
  const ctx = {
    id: { name: "essai" },
    blockConcurrencyWhile: (f) => f(),
    storage: {
      getAlarm: async () => alarme,
      setAlarm: async (t) => { alarme = t; journal.push(["alarme", t]); },
      get: async (k) => stock.get(k),
      put: async (k, v) => stock.set(k, v),
      delete: async (k) => stock.delete(k),
    },
    container: {
      running: true,
      setInactivityTimeout: async () => {},
      getTcpPort: () => ({
        fetch: async (u, o = {}) => {
          const url = typeof u === "string" ? u : u.url;
          journal.push(["conteneur", new URL(url).pathname, (o.headers ?? u.headers)?.["x-megga-interne"] ?? (u.headers?.get?.("x-megga-interne") ?? null)]);
          if (new URL(url).pathname === "/interne/rappels") return new Response(JSON.stringify(reponse), { headers: { "content-type": "application/json" } });
          return new Response("reçu 1");
        },
      }),
    },
  };
  const a = new AgentEurope(ctx, { ADMIN_TOKEN: "admin" });
  a.demarrer = async () => {};
  return { a, journal, alarme: () => alarme, ctx, stock };
}

test("le jeton interne est propre à chaque client", async () => {
  const x = await jetonInterne("admin", "client-a");
  assert.match(x, /^[0-9a-f]{64}$/);
  assert.notEqual(x, await jetonInterne("admin", "client-b"));
  assert.notEqual(x, await jetonInterne("autre", "client-a"));
});

test("après un message, une vérification des rappels est posée", async () => {
  const { a, alarme } = objet();
  const avant = Date.now();
  await a.fetch(new Request("http://agent/whatsapp", { method: "POST", body: "{}" }));
  assert.ok(alarme() >= avant + 80_000 && alarme() <= Date.now() + 100_000);
});

test("une alarme plus proche n'est pas repoussée", async () => {
  const { a, alarme } = objet();
  const proche = Date.now() + 10_000;
  await a.ctx.storage.setAlarm(proche);
  await a.verifierBientot();
  assert.equal(alarme(), proche);
});

test("à l'alarme : rappels envoyés avec le jeton, puis le prochain est programmé", async () => {
  const dans1h = Date.now() / 1000 + 3600;
  const { a, journal, alarme } = objet({ prochain: dans1h });
  await a.alarm();
  const appel = journal.find((j) => j[0] === "conteneur");
  assert.equal(appel[1], "/interne/rappels");
  assert.equal(appel[2], await jetonInterne("admin", "essai"));
  // Le rappel est dans une heure : la veille passe avant, dans 4 minutes, et le conteneur ne s'endort pas.
  assert.ok(alarme() >= Date.now() + 230_000 && alarme() <= Date.now() + 240_000);
});

test("un rappel plus proche que la veille garde son heure", async () => {
  const dans2min = Date.now() / 1000 + 120;
  const { a, alarme } = objet({ prochain: dans2min });
  await a.alarm();
  assert.equal(alarme(), Math.round(dans2min * 1000));
});

test("sans rappel à venir, la veille : une alarme dans 4 minutes", async () => {
  const { a, alarme } = objet({ prochain: null });
  await a.alarm();
  assert.ok(alarme() >= Date.now() + 230_000 && alarme() <= Date.now() + 240_000);
});

test("un message pour un conteneur endormi : gardé, et l'alarme le réveille tout de suite", async () => {
  const { a, journal, alarme, ctx, stock } = objet();
  ctx.container.running = false;
  const avant = Date.now();
  const r = await a.fetch(new Request("http://agent/whatsapp", { method: "POST", body: '{"x":1}', headers: { "x-hub-signature-256": "sha256=ab" } }));
  assert.equal(r.status, 202);
  assert.equal(journal.filter((j) => j[0] === "conteneur").length, 0); // la porte n'attend pas le réveil
  assert.deepEqual(stock.get("webhooks").map((w) => [w.corps, w.signature]), [['{"x":1}', "sha256=ab"]]);
  assert.ok(alarme() >= avant && alarme() <= Date.now());
});

test("un message pour un conteneur éveillé pose aussi la veille", async () => {
  const { a, alarme } = objet();
  await a.fetch(new Request("http://agent/whatsapp", { method: "POST", body: "{}" }));
  assert.ok(alarme() <= Date.now() + 240_000);
});

test("redémarrage en douceur : à l'alarme, le conteneur finit ses tours, s'arrête, puis repart", async () => {
  const dans1h = Date.now() / 1000 + 3600;
  const { a, journal, alarme, ctx, stock } = objet({ prochain: dans1h });
  ctx.container.destroy = async () => {
    journal.push(["destroy"]);
    ctx.container.running = false;
  };
  a.demarrer = async () => {
    journal.push(["demarrer"]);
    ctx.container.running = true;
  };
  const avant = Date.now();
  assert.equal(await a.redemarrer(), true);
  assert.ok(alarme() >= avant && alarme() <= Date.now()); // tout de suite, mais par l'alarme
  assert.equal(journal.some((j) => j[0] === "destroy"), false); // rien n'est coupé à l'appel
  await a.alarm();
  const jeton = await jetonInterne("admin", "essai");
  assert.deepEqual(journal.filter((j) => j[0] !== "alarme"), [
    ["conteneur", "/interne/vider", jeton],
    ["destroy"],
    ["demarrer"],
    ["conteneur", "/interne/rappels", jeton],
    ["conteneur", "/interne/releve", jeton], // le relevé chiffré, après les rappels (releves.js)
  ]);
  assert.equal(stock.has("a_redemarrer"), false);
  // Le rappel dans une heure garde son heure chez le conteneur ; la veille repasse avant, dans 4 minutes.
  assert.ok(alarme() >= Date.now() + 230_000 && alarme() <= Date.now() + 240_000);
});

test("redémarrer un conteneur endormi : rien à faire", async () => {
  const { a, ctx, alarme } = objet();
  ctx.container.running = false;
  assert.equal(await a.redemarrer(), false);
  assert.equal(alarme(), null);
});

test("une alarme en échec se repose elle-même, de plus en plus tard, puis repart de zéro", async () => {
  const { a, alarme, ctx, stock } = objet();
  a.demarrer = async () => {
    throw new Error("base injoignable");
  };
  const avant = Date.now();
  await a.alarm(); // ne lève plus : Cloudflare l'oublierait après six essais
  assert.ok(alarme() >= avant + 60_000 && alarme() <= Date.now() + 61_000);
  await ctx.storage.setAlarm(null);
  await a.alarm();
  assert.ok(alarme() >= avant + 120_000 && alarme() <= Date.now() + 121_000);
  assert.equal(stock.get("echecs_alarme"), 2);
  assert.ok(stock.get("alertes").every((x) => x.quoi === "rappels"));
  a.demarrer = async () => {};
  await a.alarm();
  assert.equal(stock.has("echecs_alarme"), false);
});

test("un webhook que le conteneur n'a pas reçu est gardé, puis rejoué marqué", async () => {
  const { a, journal, alarme, ctx, stock } = objet();
  a.demarrer = async () => {
    throw new Error("le conteneur ne répond pas");
  };
  const requete = () => new Request("http://agent/whatsapp", { method: "POST", body: '{"w":1}', headers: { "x-hub-signature-256": "sha256=ab" } });
  await assert.rejects(a.fetch(requete()));
  assert.equal(stock.get("webhooks").length, 1);
  assert.ok(alarme() <= Date.now() + 61_000);
  a.demarrer = async () => {};
  const vus = [];
  const port = ctx.container.getTcpPort();
  ctx.container.getTcpPort = () => ({
    fetch: async (u, o = {}) => {
      if (new URL(u).pathname === "/whatsapp") vus.push([o.body, o.headers["x-hub-signature-256"], o.headers["x-megga-rejoue"], o.headers["x-megga-interne"]]);
      return port.fetch(u, o);
    },
  });
  await a.alarm();
  assert.deepEqual(vus, [['{"w":1}', "sha256=ab", "1", await jetonInterne("admin", "essai")]]);
  assert.equal(stock.has("webhooks"), false);
  assert.ok(journal.some((j) => j[1] === "/interne/rappels"));
});
