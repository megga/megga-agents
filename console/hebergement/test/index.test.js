// Le Worker megga-console, sans Cloudflare : un faux ctx.container, sur le modèle de porte/test.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import Worker, { ConsoleConteneur, environnement, PAGE_ATTENTE } from "../src/index.js";

const SECRETS = { BETTER_AUTH_SECRET: "secret-auth", CONSOLE_BASE_URL: "postgres://u:mdp@neon.test/console" };
const VARS = { BETTER_AUTH_URL: "https://console.megga.ai", ATELIER_URL: "https://megga-agents.api-963.workers.dev" };

/**
 * Un faux conteneur : il note son démarrage et les requêtes reçues. sante : ce que rend /api/sante (un statut, ou une
 * erreur levée) ; demarre : un échec de start().
 */
function conteneur({ sante = 200, demarre = null } = {}) {
  const journal = { starts: [], requetes: [], inactivite: [] };
  const c = {
    running: false,
    start(opts) {
      if (demarre) throw demarre;
      journal.starts.push(opts);
      c.running = true;
    },
    async setInactivityTimeout(ms) {
      journal.inactivite.push(ms);
    },
    getTcpPort(port) {
      return {
        async fetch(entree, init) {
          const r = new Request(entree, init);
          if (new URL(r.url).pathname === "/api/sante") {
            if (sante instanceof Error) throw sante;
            return new Response(JSON.stringify({ ok: sante === 200 }), { status: sante });
          }
          journal.requetes.push({ port, url: r.url, entetes: Object.fromEntries(r.headers), corps: await r.text() });
          return new Response("console", { status: 200 });
        },
      };
    },
  };
  return { c, journal };
}

function objet(env, options) {
  const { c, journal } = conteneur(options);
  const ctx = { container: c, blockConcurrencyWhile: (f) => f() };
  const o = new ConsoleConteneur(ctx, env);
  o.attenteMs = 300; // le démarrage abandonne vite dans les essais
  return { o, journal };
}

test("transmet à la console et écrase x-forwarded-for", async () => {
  const { o, journal } = objet({ ...VARS, ...SECRETS });
  const r = await o.fetch(new Request("https://console.megga.ai/admin?x=1", {
    method: "POST",
    body: "corps",
    headers: { "x-forwarded-for": "6.6.6.6", "cf-connecting-ip": "1.2.3.4", cookie: "s=1" },
  }));
  assert.equal(r.status, 200);
  assert.equal(await r.text(), "console");
  const [req] = journal.requetes;
  assert.equal(req.port, 3000);
  assert.equal(req.url, "http://container/admin?x=1");
  assert.equal(req.entetes["x-forwarded-for"], "1.2.3.4");
  assert.equal(req.entetes["x-forwarded-host"], "console.megga.ai");
  assert.equal(req.entetes["x-forwarded-proto"], "https");
  assert.equal(req.entetes.cookie, "s=1");
  assert.equal(req.corps, "corps");
});

test("sans cf-connecting-ip, l'x-forwarded-for du client ne passe pas", async () => {
  const { o, journal } = objet({ ...VARS, ...SECRETS });
  await o.fetch(new Request("https://console.megga.ai/", { headers: { "x-forwarded-for": "6.6.6.6" } }));
  assert.equal(journal.requetes[0].entetes["x-forwarded-for"], undefined);
});

test("démarre le conteneur avec ses variables", async () => {
  const { o, journal } = objet({ ...VARS, ...SECRETS, VERSION: { tag: "abc1234" } });
  await o.fetch(new Request("https://console.megga.ai/connexion"));
  assert.equal(journal.starts.length, 1);
  assert.equal(journal.starts[0].enableInternet, true);
  assert.deepEqual(journal.starts[0].env, {
    CONSOLE_INSCRIPTION: "invitation",
    BETTER_AUTH_URL: "https://console.megga.ai",
    ATELIER_URL: "https://megga-agents.api-963.workers.dev",
    BETTER_AUTH_SECRET: "secret-auth",
    CONSOLE_BASE_URL: "postgres://u:mdp@neon.test/console",
    CONSOLE_REVISION: "abc1234",
  });
  assert.ok(!("ATELIER_JETON" in journal.starts[0].env));
  assert.deepEqual(journal.inactivite, [15 * 60 * 1000]);
  // Déjà démarré : la requête suivante ne le relance pas.
  await o.fetch(new Request("https://console.megga.ai/admin"));
  assert.equal(journal.starts.length, 1);
});

test("remet ATELIER_JETON quand il est posé", () => {
  assert.equal(environnement({ ...VARS, ...SECRETS, ATELIER_JETON: "jeton" }).ATELIER_JETON, "jeton");
});

test("ne démarre pas sans ses secrets requis, et ne nomme que ce qui manque", async () => {
  assert.throws(() => environnement({ ...VARS, BETTER_AUTH_SECRET: "x" }), /^Error: secrets manquants : CONSOLE_BASE_URL$/);
  const erreurs = [];
  const avant = console.error;
  console.error = (...a) => erreurs.push(a.join(" "));
  try {
    const { o, journal } = objet({ ...VARS, CONSOLE_BASE_URL: SECRETS.CONSOLE_BASE_URL });
    const r = await o.fetch(new Request("https://console.megga.ai/"));
    assert.equal(r.status, 503);
    assert.equal(journal.starts.length, 0);
  } finally {
    console.error = avant;
  }
  assert.equal(erreurs.length, 1);
  assert.match(erreurs[0], /BETTER_AUTH_SECRET/);
  assert.doesNotMatch(erreurs[0], /mdp|neon\.test/); // jamais une valeur de secret dans le journal
});

/** Une réponse est la page d'attente : 503, HTML, le texte français, rien de technique. */
async function estPageAttente(r) {
  assert.equal(r.status, 503);
  assert.match(r.headers.get("content-type"), /^text\/html/);
  assert.equal(r.headers.get("retry-after"), "10");
  const texte = await r.text();
  assert.equal(texte, PAGE_ATTENTE);
  assert.match(texte, /La console se réveille/);
  assert.match(texte, /lang="fr"/);
  assert.doesNotMatch(texte, /error|erreur|exception|stack|conteneur|container|503|\bat\s/i);
}

test("répond la page d'attente si le conteneur ne démarre pas", async () => {
  const avant = console.error;
  console.error = () => {};
  try {
    // start() échoue
    await estPageAttente(await objet({ ...VARS, ...SECRETS }, { demarre: new Error("no such image: boom") }).o.fetch(new Request("https://console.megga.ai/")));
    // il démarre, mais /api/sante ne répond jamais
    await estPageAttente(await objet({ ...VARS, ...SECRETS }, { sante: new Error("connection refused") }).o.fetch(new Request("https://console.megga.ai/")));
    // il démarre, mais /api/sante répond mal
    const { o, journal } = objet({ ...VARS, ...SECRETS }, { sante: 500 });
    await estPageAttente(await o.fetch(new Request("https://console.megga.ai/admin")));
    assert.equal(journal.requetes.length, 0); // rien n'a été transmis
  } finally {
    console.error = avant;
  }
});

test("le Worker remet tout à l'objet unique de la console, en UE ; injoignable, la page d'attente", async () => {
  const appels = [];
  const env = {
    CONSOLE: {
      jurisdiction: (j) => ({
        getByName: (nom) => ({
          fetch: async (r) => {
            appels.push({ j, nom, url: r.url });
            return new Response("ok");
          },
        }),
      }),
    },
  };
  const r = await Worker.fetch(new Request("https://console.megga.ai/api/sante"), env);
  assert.equal(await r.text(), "ok");
  assert.deepEqual(appels, [{ j: "eu", nom: "console", url: "https://console.megga.ai/api/sante" }]);

  const avant = console.error;
  console.error = () => {};
  try {
    const panne = { CONSOLE: { jurisdiction: () => ({ getByName: () => ({ fetch: async () => { throw new Error("Durable Object reset"); } }) }) } };
    await estPageAttente(await Worker.fetch(new Request("https://console.megga.ai/"), panne));
  } finally {
    console.error = avant;
  }
});

test("la configuration : une seule origine, en UE, un seul conteneur", () => {
  const texte = readFileSync(new URL("../wrangler.jsonc", import.meta.url), "utf8");
  const config = JSON.parse(texte.replace(/^\s*\/\/.*$/gm, ""));
  assert.equal(config.name, "megga-console");
  assert.equal(config.workers_dev, false);
  assert.equal(config.preview_urls, false);
  assert.deepEqual(config.routes, [{ pattern: "console.megga.ai", custom_domain: true }]);
  assert.equal(config.vars.BETTER_AUTH_URL, "https://console.megga.ai");
  assert.deepEqual(config.containers, [{ class_name: "ConsoleConteneur", image: "../Dockerfile", image_build_context: "..",
    instance_type: "basic", max_instances: 1, constraints: { jurisdiction: "eu" } }]);
  assert.doesNotMatch(texte, /BETTER_AUTH_SECRET"\s*:|CONSOLE_BASE_URL"\s*:|postgres:\/\//); // aucun secret dans le fichier
});

test("la console n'est vérifiée qu'au réveil, puis revérifiée après une panne", async () => {
  let santes = 0;
  const { c } = conteneur();
  const fetchPort = c.getTcpPort;
  c.getTcpPort = (port) => {
    const p = fetchPort(port);
    return {
      async fetch(entree, init) {
        if (new URL(new Request(entree, init).url).pathname === "/api/sante") santes++;
        return p.fetch(entree, init);
      },
    };
  };
  const o = new ConsoleConteneur({ container: c, blockConcurrencyWhile: (f) => f() }, { ...VARS, ...SECRETS });
  for (let i = 0; i < 3; i++) assert.equal(await (await o.fetch(new Request("https://console.megga.ai/admin"))).text(), "console");
  assert.equal(santes, 1);

  c.getTcpPort = () => ({ fetch: async () => { throw new Error("connexion refusée"); } });
  const avant = console.error;
  console.error = () => {};
  try {
    await estPageAttente(await o.fetch(new Request("https://console.megga.ai/admin")));
  } finally {
    console.error = avant;
  }
  assert.equal(o.repond, false);
});

test("les fichiers de construction se servent depuis le cache de Cloudflare", async () => {
  const garde = new Map();
  globalThis.caches = { default: { match: async (r) => garde.get(r.url)?.clone(), put: async (r, rep) => void garde.set(r.url, rep) } };
  let appels = 0;
  const env = { CONSOLE: { jurisdiction: () => ({ getByName: () => ({ fetch: async () => {
    appels++;
    return new Response("js", { headers: { "cache-control": "public, max-age=31536000, immutable" } });
  } }) }) } };
  const attente = [];
  const ctx = { waitUntil: (p) => attente.push(p) };
  try {
    const url = "https://console.megga.ai/_next/static/chunks/a.js";
    assert.equal(await (await Worker.fetch(new Request(url), env, ctx)).text(), "js");
    await Promise.all(attente);
    assert.equal(await (await Worker.fetch(new Request(url), env, ctx)).text(), "js");
    assert.equal(appels, 1);
    await Worker.fetch(new Request("https://console.megga.ai/admin"), env, ctx);
    await Worker.fetch(new Request("https://console.megga.ai/admin"), env, ctx);
    assert.equal(appels, 3); // les pages ne passent jamais par le cache
  } finally {
    delete globalThis.caches;
  }
});
