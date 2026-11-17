// Lot 5 : l'annuaire tenu par l'atelier, le redémarrage des conteneurs, l'atelier derrière la porte.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { DatabaseSync } from "node:sqlite";
import { test } from "node:test";
import { AgentEurope, Atelier, jetonInterne } from "../src/agent.js";
import { clientParNumero, inscrire, lister } from "../src/annuaire.js";
import { recevoir } from "../src/index.js";

// Un vrai SQLite (le moteur de D1), avec les migrations de l'annuaire, derrière l'interface de D1.
function d1() {
  const db = new DatabaseSync(":memory:");
  for (const f of ["0001_annuaire.sql", "0002_versions.sql", "0003_sans_whatsapp.sql"]) db.exec(readFileSync(new URL(`../migrations/${f}`, import.meta.url), "utf8"));
  const requete = (sql, args = []) => ({
    bind: (...a) => requete(sql, a),
    first: async () => db.prepare(sql).get(...args) ?? null,
    all: async () => ({ results: db.prepare(sql).all(...args) }),
    run: async () => db.prepare(sql).run(...args),
  });
  return { prepare: (sql) => requete(sql) };
}

const config = (id = "exemple", autres = {}) => ({ version: 1, id, zone: "europe", whatsapp: { numero_id: "100000000000001" }, nom_agent: "Alix", ...autres });

// Une fausse liaison : chaque objet note ses redémarrages et dit s'il tourne.
function liaison(journal, demarres = new Set(), enPanne = new Set()) {
  return {
    jurisdiction: (j) => ({
      getByName: (nom) => ({
        redemarrer: async () => {
          if (enPanne.has(nom)) throw new Error("objet injoignable");
          journal.push({ j, nom, redemarre: demarres.has(nom) });
          return demarres.has(nom);
        },
        etat: async () => {
          journal.push({ j, nom, etat: true });
          return { demarre: demarres.has(nom) };
        },
        suivre: async (chemin, recherche) => {
          journal.push({ j, nom, suivi: chemin, recherche });
          if (chemin === "/panne") throw new Error("le conteneur ne répond pas");
          return { statut: 200, donnees: { tours: 3 } };
        },
        poserSecrets: async (s) => {
          journal.push({ j, nom, secrets: Object.keys(s) });
          return Object.keys(s);
        },
        fetch: async (r) => {
          journal.push({ j, nom, chemin: new URL(r.url).pathname, auth: r.headers.get("authorization"), corps: await r.text() });
          return Response.json({ ok: true });
        },
      }),
    }),
  };
}

function env(journal, demarres, enPanne) {
  return { ADMIN_TOKEN: "admin", ANNUAIRE: d1(), AGENTS_EUROPE: liaison(journal, demarres, enPanne), AGENTS_ETATS_UNIS: liaison(journal, demarres, enPanne), ATELIER: liaison(journal) };
}

const put = (e, id, corps, jeton = "admin") =>
  recevoir(new Request(`https://porte/admin/clients/${id}/config`, { method: "PUT", body: JSON.stringify(corps), headers: { authorization: `Bearer ${jeton}` } }), e);

test("l'annuaire : inscrire, remplacer, lister", async () => {
  const db = d1();
  await inscrire(db, "exemple", { version: 1, config: config() });
  await inscrire(db, "exemple", { version: 3, config: config("exemple", { nom_agent: "Lea" }) });
  const [c] = await lister(db);
  assert.equal(c.id, "exemple");
  assert.equal(c.version, 3);
  assert.equal(c.actif, 1);
  assert.ok(c.maj_le);
  assert.equal(c.config, undefined); // la liste ne rend pas les configurations
  assert.deepEqual(await clientParNumero(db, "100000000000001"), { id: "exemple", zone: "europe" });
  const l = await db.prepare("SELECT config FROM clients WHERE id = ?").bind("exemple").first();
  assert.equal(JSON.parse(l.config).nom_agent, "Lea");
});

test("l'annuaire refuse ce qui ne tient pas", async () => {
  const db = d1();
  await inscrire(db, "exemple", { version: 1, config: config() });
  const refus = async (id, corps, statut) => {
    await assert.rejects(inscrire(db, id, corps), (e) => e.statut === statut);
  };
  await refus("exemple", { version: 2, config: config("autre") }, 400);
  await refus("exemple", { version: 0, config: config() }, 400);
  await refus("exemple", { version: 2, config: config("exemple", { whatsapp: { numero_id: "abc" } }) }, 400);
  await refus("exemple", { version: 2, config: config("exemple", { zone: "etats-unis" }) }, 409);
  await refus("autre", { version: 1, config: config("autre") }, 409); // numéro déjà servi
  await refus("Mauvais id", { version: 1, config: config("Mauvais id") }, 400);
});

test("mise en service par l'atelier : annuaire puis redémarrage", async () => {
  const journal = [];
  const e = env(journal, new Set(["exemple"]));
  assert.equal((await put(e, "exemple", { version: 2, config: config() }, "faux")).status, 401);
  assert.equal((await put(e, "exemple", { version: 2, config: config("exemple", { zone: "suisse" }) })).status, 400);
  const r = await put(e, "exemple", { version: 2, config: config() });
  assert.equal(r.status, 200);
  assert.deepEqual(await r.json(), { ok: true, id: "exemple", version: 2, redemarre: true });
  assert.deepEqual(journal, [{ j: "eu", nom: "exemple", redemarre: true }]);
  // un conflit ne redémarre rien
  const r2 = await put(e, "exemple", { version: 3, config: config("exemple", { zone: "etats-unis" }) });
  assert.equal(r2.status, 409);
  assert.equal(journal.length, 1);
});

test("un redémarrage en échec n'annule pas l'annuaire, il est signalé", async () => {
  const e = env([], new Set(), new Set(["exemple"]));
  const r = await put(e, "exemple", { version: 2, config: config() });
  assert.equal(r.status, 200);
  const d = await r.json();
  assert.equal(d.redemarre, null);
  assert.match(d.alerte, /redémarrage/);
  assert.equal((await lister(e.ANNUAIRE))[0].version, 2);
});

test("la liste des clients et l'état des conteneurs, pour MEGGA seulement", async () => {
  const journal = [];
  const e = env(journal, new Set(["exemple"]));
  await put(e, "exemple", { version: 1, config: config() });
  await put(e, "loin", { version: 4, config: config("loin", { zone: "etats-unis", whatsapp: { numero_id: "100000000000002" } }) });
  const get = (jeton) => recevoir(new Request("https://porte/admin/clients", { headers: { authorization: `Bearer ${jeton}` } }), e);
  assert.equal((await get("faux")).status, 401);
  const { clients } = await (await get("admin")).json();
  assert.deepEqual(clients.map((c) => [c.id, c.zone, c.version, c.conteneur.demarre]), [["exemple", "europe", 1, true], ["loin", "etats-unis", 4, false]]);
  // un seul client : seul son objet est interrogé
  journal.length = 0;
  const seul = await recevoir(new Request("https://porte/admin/clients?id=loin", { headers: { authorization: "Bearer admin" } }), e);
  assert.deepEqual((await seul.json()).clients.map((c) => c.id), ["loin"]);
  assert.deepEqual(journal, [{ j: "us", nom: "loin", etat: true }]);
});

test("l'atelier derrière la porte : transmis tel quel, jeton compris", async () => {
  const journal = [];
  const e = env(journal);
  const r = await recevoir(new Request("https://porte/atelier/clients", { headers: { authorization: "Bearer jeton-client" } }), e);
  assert.equal(r.status, 200);
  assert.deepEqual(journal, [{ j: "eu", nom: "megga", chemin: "/atelier/clients", auth: "Bearer jeton-client", corps: "" }]);
  assert.equal((await recevoir(new Request("https://porte/atelier/clients", { headers: { authorization: "Bearer x" } }), { ...e, ATELIER: undefined })).status, 503);
  // sans jeton, le conteneur de l'atelier n'est pas réveillé
  for (const h of [{}, { authorization: "Bearer " }, { authorization: "Basic abc" }]) {
    assert.equal((await recevoir(new Request("https://porte/atelier/clients", { headers: h }), e)).status, 401);
  }
  assert.equal(journal.length, 1);
  assert.equal((await recevoir(new Request("https://porte/atelierx"), e)).status, 404);
  // sa base se pose comme celle d'un client, écriture seule
  const s = await recevoir(new Request("https://porte/admin/atelier/secrets", { method: "PUT", body: JSON.stringify({ DATABASE_URL: "postgresql://x" }), headers: { authorization: "Bearer admin" } }), e);
  assert.equal(await s.text(), "rangés : DATABASE_URL");
  assert.equal(JSON.stringify(journal).includes("postgresql://x"), false);
});

// Les objets eux-mêmes

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
      journal.push(["destroy"]);
      c.running = false;
    },
    setInactivityTimeout: async () => {},
    getTcpPort: () => ({ fetch: async () => new Response("ok") }),
  };
  return { ctx: { id: { name: "megga" }, blockConcurrencyWhile: (f) => f(), storage: { get: async (k) => stock.get(k), put: async (k, v) => stock.set(k, v) }, container: c }, journal, stock };
}

test("l'atelier redémarre tout de suite, seulement s'il tourne", async () => {
  const a = ctx({ running: true });
  const atelier = new Atelier(a.ctx, {});
  assert.deepEqual(await atelier.etat(), { demarre: true, alertes: [] });
  assert.equal(await atelier.redemarrer(), true);
  assert.equal(await atelier.redemarrer(), false);
  assert.deepEqual(a.journal, [["destroy"]]);
  assert.deepEqual(await atelier.etat(), { demarre: false, alertes: [] });
});

test("l'atelier démarre en service « atelier », avec sa base et sans les secrets de Meta", async () => {
  const a = ctx({ secrets: { DATABASE_URL: "postgresql://atelier" } });
  const envW = { ADMIN_TOKEN: "admin", PORTE_URL: "https://porte", ANTHROPIC_API_KEY: "a", DEEPSEEK_API_KEY: "d", META_TOKEN: "m", META_APP_SECRET: "s" };
  const atelier = new Atelier(a.ctx, envW);
  await atelier.demarrer();
  const [[quoi, o]] = a.journal;
  assert.equal(quoi, "start");
  assert.deepEqual(o.env, { MEGGA_SERVICE: "atelier", DATABASE_URL: "postgresql://atelier", ADMIN_TOKEN: "admin", PORTE_URL: "https://porte", ANTHROPIC_API_KEY: "a", DEEPSEEK_API_KEY: "d" });
  const sans = new Atelier(ctx().ctx, envW);
  await assert.rejects(sans.demarrer(), /DATABASE_URL/);
});

test("le suivi d'un client : réservé à MEGGA, transmis à son conteneur, paramètres filtrés", async () => {
  const journal = [];
  const e = env(journal);
  await put(e, "exemple", { version: 1, config: config() });
  journal.length = 0;
  const get = (chemin, jeton = "admin") => recevoir(new Request(`https://porte/admin/clients/${chemin}`, { headers: { authorization: `Bearer ${jeton}` } }), e);
  assert.equal((await get("exemple/suivi", "faux")).status, 401);
  assert.equal((await get("inconnu/suivi")).status, 404);
  const r = await get("exemple/suivi?depuis=1700000000&limite=5&autre=x");
  assert.equal(r.status, 200);
  assert.deepEqual(await r.json(), { tours: 3 });
  await get("exemple/suivi/conversations/%2B41790000000?depuis=abc");
  await get("exemple/suivi/panne");
  assert.equal((await get("exemple/suivi/%E0")).status, 400);
  assert.deepEqual(journal.map((x) => [x.suivi, x.recherche]), [
    ["", "?depuis=1700000000&limite=5"],
    ["/conversations/+41790000000", ""],
    ["/panne", ""],
  ]);
  const panne = await get("exemple/suivi/panne");
  assert.equal(panne.status, 503);
  assert.deepEqual(await panne.json(), { erreur: "conteneur injoignable" });
});

test("l'objet d'un client : suivi avec le jeton interne, chemins bornés, lecture récente gardée en mémoire", async () => {
  const a = ctx({ running: true });
  const vus = [];
  a.ctx.id.name = "exemple";
  a.ctx.container.getTcpPort = () => ({
    fetch: async (u, o = {}) => {
      const url = new URL(typeof u === "string" ? u : u.url);
      vus.push([url.pathname + url.search, o.headers?.["x-megga-interne"]]);
      return Response.json({ tours: vus.length });
    },
  });
  const agent = new AgentEurope(a.ctx, { ADMIN_TOKEN: "admin" });
  agent.demarrer = async () => {};
  assert.deepEqual(await agent.suivre("/alertes", "?depuis=1"), { statut: 200, donnees: { tours: 1 } });
  assert.deepEqual(vus, [["/interne/suivi/alertes?depuis=1", await jetonInterne("admin", "exemple")]]);
  // la même lecture, tout de suite après : rendue de mémoire, le conteneur n'est pas sollicité
  assert.deepEqual(await agent.suivre("/alertes", "?depuis=1"), { statut: 200, donnees: { tours: 1 } });
  assert.equal(vus.length, 1);
  await agent.suivre("/alertes", "?depuis=2");
  assert.equal(vus.length, 2);
  for (const mauvais of ["/../rappels", "/conversations/abc", "/autre"]) await assert.rejects(agent.suivre(mauvais), /chemin de suivi/);
});

test("un conteneur réveillé pour être lu ne se rendort plus vite : la veille le garde éveillé", async () => {
  const a = ctx({ running: false });
  const sommeils = [];
  a.ctx.container.setInactivityTimeout = async (ms) => sommeils.push(ms);
  a.ctx.container.getTcpPort = () => ({ fetch: async () => Response.json({ tours: 0 }) });
  let alarme = null;
  a.ctx.storage.getAlarm = async () => alarme;
  a.ctx.storage.setAlarm = async (t) => { alarme = t; };
  const agent = new AgentEurope(a.ctx, { ADMIN_TOKEN: "admin" });
  agent.demarrer = async () => {
    a.ctx.container.running = true;
  };
  await agent.suivre("");
  assert.deepEqual(sommeils, []); // plus de sommeil de 2 minutes (Julien, 17.11.2026)
  assert.ok(alarme && alarme <= Date.now() + 4 * 60 * 1000);
});

test("les pannes d'un conteneur sont gardées, puis marquées résolues quand il répond de nouveau", async () => {
  const a = ctx({ running: true });
  a.ctx.container.getTcpPort = () => ({ fetch: async () => new Response("ok") });
  const agent = new AgentEurope(a.ctx, { ADMIN_TOKEN: "admin" });
  agent.demarrer = async () => {
    throw new Error("secret du client manquant : DATABASE_URL");
  };
  await assert.rejects(agent.suivre(""));
  await assert.rejects(agent.fetch(new Request("http://agent/interne/autre")));
  let { alertes } = await agent.etat();
  assert.deepEqual(alertes.map((x) => [x.quoi, x.resolue]), [["demarrage", null], ["transmission", null]]);
  assert.match(alertes[0].message, /DATABASE_URL/);
  // le secret est posé : le conteneur démarre et répond à /sante
  delete agent.demarrer;
  agent.environnement = async () => ({});
  a.ctx.container.running = false;
  await agent.fetch(new Request("http://agent/interne/autre"));
  ({ alertes } = await agent.etat());
  assert.equal(alertes.length, 2);
  assert.ok(alertes.every((x) => x.resolue >= x.quand)); // gardées pour l'historique, mais réglées
  for (let i = 0; i < 15; i++) await agent.noterAlerte("transmission", new Error(`panne ${i}`));
  assert.equal((await agent.etat()).alertes.length, 10); // les dix dernières seulement
});

test("après un déploiement : chaque conteneur allumé repart sur la nouvelle image, réservé à MEGGA", async () => {
  const journal = [];
  const e = env(journal, new Set(["exemple"]), new Set(["casse"]));
  await put(e, "exemple", { version: 1, config: config() });
  await put(e, "dort", { version: 1, config: config("dort", { whatsapp: { numero_id: "100000000000005" } }) });
  journal.length = 0;
  const post = (jeton) => recevoir(new Request("https://porte/admin/redemarrer", { method: "POST", headers: { authorization: `Bearer ${jeton}` } }), e);
  assert.equal((await post("faux")).status, 401);
  assert.equal(journal.length, 0);
  const r = await (await post("admin")).json();
  assert.deepEqual(r.clients, [{ id: "dort", redemarre: false }, { id: "exemple", redemarre: true }]);
  // l'atelier aussi (« megga »), pour qu'il reparte lui aussi sur la nouvelle image
  assert.deepEqual(journal.filter((x) => "redemarre" in x).map((x) => x.nom).sort(), ["dort", "exemple", "megga"]);
  assert.equal(r.atelier, false);
});

test("l'atelier ne s'arrête qu'entre deux requêtes : une mise en service en cours va au bout", async () => {
  const a = ctx({ running: true });
  let finir;
  a.ctx.container.getTcpPort = () => ({
    fetch: async () => {
      await new Promise((r) => (finir = r));
      return Response.json({ version_en_service: 2 });
    },
  });
  const atelier = new Atelier(a.ctx, {});
  atelier.demarrer = async () => {};
  const enCours = atelier.fetch(new Request("http://atelier/atelier/clients/x/versions/2/activer", { method: "POST" }));
  await new Promise((r) => setTimeout(r, 0));
  assert.equal(await atelier.redemarrer(), true); // demandé pendant la mise en service
  assert.deepEqual(a.journal, []); // rien n'est coupé
  finir();
  const r = await enCours;
  assert.deepEqual(await r.json(), { version_en_service: 2 }); // la réponse arrive entière
  assert.deepEqual(a.journal, [["destroy"]]); // puis l'atelier repart
  assert.equal(await atelier.redemarrer(), false); // arrêté : plus rien à faire
});

test("le commit déployé (wrangler deploy --tag) est remis au conteneur", async () => {
  const a = ctx({ secrets: { DATABASE_URL: "postgresql://atelier" } });
  const envW = { ADMIN_TOKEN: "admin", PORTE_URL: "https://porte", VERSION_PORTE: { id: "v1", tag: "abc123def456" } };
  await new Atelier(a.ctx, envW).demarrer();
  assert.equal(a.journal[0][1].env.MEGGA_REVISION, "abc123def456");
  const b = ctx({ secrets: { DATABASE_URL: "postgresql://atelier" } });
  await new Atelier(b.ctx, { ...envW, VERSION_PORTE: { id: "v2", tag: "" } }).demarrer();
  assert.equal("MEGGA_REVISION" in b.journal[0][1].env, false); // sans étiquette, l'image garde la sienne
});
