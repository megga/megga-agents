// Le relevé chiffré (20.11.2026) : rangé par l'objet de chaque client, lu d'un coup par la console de MEGGA.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { DatabaseSync } from "node:sqlite";
import { test } from "node:test";
import { AgentEurope } from "../src/agent.js";
import { recevoir } from "../src/index.js";
import { RELEVE_MS, lireReleves, nettoyer, ranger, releverSiDu } from "../src/releves.js";

const AUJOURDHUI = new Date().toISOString().slice(0, 10);
const NUMERO = "+41790000000";

function d1() {
  const db = new DatabaseSync(":memory:");
  for (const f of ["0001_annuaire.sql", "0002_versions.sql", "0003_sans_whatsapp.sql", "0004_releves.sql"]) {
    db.exec(readFileSync(new URL(`../migrations/${f}`, import.meta.url), "utf8"));
  }
  db.prepare("INSERT INTO clients (id, numero_id, zone, config, version) VALUES (?, ?, ?, ?, ?)").run("essai", "100000000000001", "europe", "{}", 3);
  db.prepare("INSERT INTO clients (id, numero_id, zone, config, version) VALUES (?, ?, ?, ?, ?)").run("muet", "100000000000002", "etats-unis", "{}", 1);
  const requete = (sql, args = []) => ({
    bind: (...a) => requete(sql, a),
    first: async () => db.prepare(sql).get(...args) ?? null,
    all: async () => ({ results: db.prepare(sql).all(...args) }),
    run: async () => db.prepare(sql).run(...args),
  });
  return { prepare: (sql) => requete(sql), brut: db };
}

const jour = (tours) => ({
  tours, tours_api: 0, tours_en_echec: 0, secours: 0, personnes: 1,
  modeles: { "claude-sonnet-5-5": { fournisseur: "Anthropic", tours, entree: 100, sortie: 10, cache_lecture: 0, cache_ecriture: 0 } },
  journal: { tour_echec: { nombre: 0, quantite: 0 } },
  delais: { lecture: { nombre: 1, moyenne: 2.5 }, reponse: { nombre: 1, moyenne: 8 }, lentes: 0 },
});
const RELEVE = { forme: 1, image: { version: "0.7.0", revision: "dede0e8" }, rappels_en_attente: 2, derniere_activite: 1795000000, jours: { [AUJOURDHUI]: jour(4) } };

test("le relevé est reconstruit champ par champ : rien de privé ne passe", () => {
  const sale = structuredClone(RELEVE);
  sale.personne = NUMERO;
  sale.messages = ["Bonjour Greg"];
  sale.image.revision = NUMERO;
  const j = sale.jours[AUJOURDHUI];
  j.conversations = [{ personne: NUMERO, texte: "Bonjour" }];
  j.modeles[NUMERO] = { fournisseur: "Greg Dupont +33 6 12 34 56 78", tours: 1 };
  j.modeles["claude-sonnet-5-5"].fournisseur = "<script>";
  j.journal["Bonjour Greg"] = { nombre: 1, quantite: 1 };
  j.journal.tour_echec.detail = "RuntimeError chez +41790000000";
  j.tours = "dix";
  sale.jours["pas un jour"] = jour(1);
  const propre = nettoyer(sale);
  const texte = JSON.stringify(propre);
  for (const prive of ["4179", "Greg", "Bonjour", "RuntimeError", "script", "dix"]) assert.ok(!texte.includes(prive), prive);
  assert.equal(propre.jours[AUJOURDHUI].tours, 0);
  assert.equal(propre.jours[AUJOURDHUI].modeles["claude-sonnet-5-5"].fournisseur, null);
  assert.deepEqual(Object.keys(propre.jours), [AUJOURDHUI]);
  assert.deepEqual(propre.image, { version: "0.7.0", revision: null });
});

test("un relevé sans la forme attendue est refusé", () => {
  assert.equal(nettoyer(null), null);
  assert.equal(nettoyer({ ...RELEVE, forme: 2 }), null);
  assert.equal(nettoyer({ ...RELEVE, jours: { hier: jour(1) } }), null);
});

test("ranger puis lire : un rang par jour, l'état, et les clients sans relevé", async () => {
  const db = d1();
  const maintenant = Date.now();
  await ranger(db, "essai", nettoyer(RELEVE), { demarre: true, alertes: [{ quand: maintenant - 1000, quoi: "releve", message: "secret", resolue: null }] }, maintenant);
  await ranger(db, "essai", nettoyer({ ...RELEVE, jours: { [AUJOURDHUI]: jour(6) } }), { demarre: true, alertes: [] }, maintenant + 1);
  const ancien = new Date(maintenant - 500 * 86400 * 1000).toISOString().slice(0, 10);
  db.brut.prepare("INSERT INTO releves (client, jour, chiffres, maj_le) VALUES ('essai', ?, '{}', 1)").run(ancien);
  await ranger(db, "essai", nettoyer(RELEVE), { demarre: true, alertes: [] }, maintenant + 2);
  assert.equal(db.brut.prepare("SELECT count(*) AS n FROM releves WHERE jour = ?").get(ancien).n, 0); // plus de 400 jours : effacé
  const lu = await lireReleves(db, 7, maintenant);
  const [essai, muet] = lu.clients;
  assert.equal(essai.id, "essai");
  assert.equal(essai.jours[AUJOURDHUI].tours, 4);
  assert.equal(essai.releve_le, maintenant + 2);
  assert.deepEqual(essai.etat.image, { version: "0.7.0", revision: "dede0e8" });
  assert.equal(essai.etat.rappels_en_attente, 2);
  assert.deepEqual([muet.id, muet.etat, muet.releve_le, muet.jours], ["muet", null, null, {}]);
  // L'état rangé ne garde que le genre et l'heure des pannes : pas leur message.
  await ranger(db, "essai", nettoyer(RELEVE), { demarre: true, alertes: [{ quand: maintenant, quoi: "releve", message: "secret", resolue: null }] }, maintenant + 3);
  const etat = (await lireReleves(db, 7, maintenant)).clients[0].etat;
  assert.deepEqual(etat.pannes_en_cours, [{ quoi: "releve", quand: maintenant }]);
  assert.ok(!JSON.stringify(etat).includes("secret"));
});

// Un faux objet de client : stockage, et le conteneur qui rend son relevé.
function objet(env, reponse = () => Response.json(RELEVE)) {
  const stock = new Map();
  const vus = [];
  const port = {
    fetch: async (u, o = {}) => {
      vus.push([new URL(u).pathname + new URL(u).search, o.headers?.["x-megga-interne"] ?? null]);
      if (new URL(u).pathname === "/interne/rappels") return Response.json({ prochain: null });
      return new URL(u).pathname === "/interne/releve" ? reponse() : new Response("ok");
    },
  };
  const ctx = {
    id: { name: "essai" },
    blockConcurrencyWhile: (f) => f(),
    storage: {
      getAlarm: async () => null,
      setAlarm: async () => {},
      get: async (k) => stock.get(k),
      put: async (k, v) => stock.set(k, v),
      delete: async (k) => stock.delete(k),
    },
    container: { running: true, setInactivityTimeout: async () => {}, getTcpPort: () => port },
  };
  const a = new AgentEurope(ctx, { ADMIN_TOKEN: "admin", ...env });
  a.demarrer = async () => {};
  return { a, port, vus, stock };
}

test("un relevé au plus par quart d'heure, avec le jeton interne", async () => {
  const db = d1();
  const { a, port, vus } = objet({ ANNUAIRE: db });
  const t = Date.now();
  assert.equal(await releverSiDu(a, port, "jeton", t), true);
  assert.deepEqual(vus, [["/interne/releve?jours=2", "jeton"]]);
  assert.equal(await releverSiDu(a, port, "jeton", t + RELEVE_MS - 1), false);
  assert.equal(await releverSiDu(a, port, "jeton", t + RELEVE_MS), true);
  assert.equal((await lireReleves(db, 1)).clients[0].releve_le, t + RELEVE_MS);
});

test("un relevé en échec ne range rien et ne se retente qu'au quart d'heure suivant", async () => {
  const db = d1();
  const { a, port, vus } = objet({ ANNUAIRE: db }, () => new Response("panne", { status: 500 }));
  await assert.rejects(releverSiDu(a, port, "jeton"), /relevé 500/);
  assert.equal(await releverSiDu(a, port, "jeton"), false);
  assert.equal(vus.length, 1);
  assert.equal((await lireReleves(db, 1)).clients[0].releve_le, null);
  const mal = objet({ ANNUAIRE: db }, () => Response.json({ forme: 1, jours: {} }));
  await assert.rejects(releverSiDu(mal.a, mal.port, "jeton"), /mal formé/);
});

test("à l'alarme : rappels puis relevé ; un relevé en panne n'arrête pas les rappels", async () => {
  const db = d1();
  const { a, vus } = objet({ ANNUAIRE: db });
  await a.alarm();
  assert.deepEqual(vus.map(([chemin]) => chemin), ["/interne/rappels", "/interne/releve?jours=2"]);
  assert.equal((await lireReleves(db, 1)).clients[0].jours[AUJOURDHUI].tours, 4);
  const enPanne = objet({ ANNUAIRE: db }, () => new Response("panne", { status: 503 }));
  await enPanne.a.alarm();
  assert.equal(enPanne.stock.get("echecs_alarme"), undefined); // l'alarme a réussi : les rappels sont partis
  assert.equal(enPanne.stock.get("alertes").at(-1).quoi, "releve");
});

test("GET /admin/releves : le jeton de MEGGA, des jours bornés, sans réveiller aucun conteneur", async () => {
  const db = d1();
  await ranger(db, "essai", nettoyer(RELEVE), { demarre: true, alertes: [] });
  const env = { ADMIN_TOKEN: "admin", ANNUAIRE: db };
  const lire = (chemin, jeton = "admin") => recevoir(new Request(`https://porte.essai${chemin}`, { headers: { authorization: `Bearer ${jeton}` } }), env);
  assert.equal((await lire("/admin/releves", "faux")).status, 401);
  for (const faux of ["abc", "1000", "-1"]) assert.equal((await lire(`/admin/releves?jours=${faux}`)).status, 400);
  const r = await lire("/admin/releves?jours=30");
  assert.equal(r.status, 200);
  const d = await r.json();
  assert.equal(d.jours, 30);
  assert.deepEqual(d.clients.map((c) => c.id), ["essai", "muet"]);
  assert.equal(d.clients[0].jours[AUJOURDHUI].tours, 4);
});
