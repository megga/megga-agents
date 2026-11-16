// Lot 6.6 : l'entrée par API. Un logiciel parle à l'agent d'un client à travers la porte.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { DatabaseSync } from "node:sqlite";
import { test } from "node:test";
import { AgentEurope, jetonInterne } from "../src/agent.js";
import { clientParNumero, inscrire, lister } from "../src/annuaire.js";
import { recevoir } from "../src/index.js";

const CLE = "mga_" + "a".repeat(43);

function d1() {
  const db = new DatabaseSync(":memory:");
  for (const f of ["0001_annuaire.sql", "0002_versions.sql"]) db.exec(readFileSync(new URL(`../migrations/${f}`, import.meta.url), "utf8"));
  // Un client d'avant la migration : il garde son numéro.
  db.prepare("INSERT INTO clients (id, numero_id, zone, config, version) VALUES (?, ?, ?, ?, ?)").run("ancien", "100000000000009", "europe", "{}", 2);
  db.exec(readFileSync(new URL("../migrations/0003_sans_whatsapp.sql", import.meta.url), "utf8"));
  const requete = (sql, args = []) => ({
    bind: (...a) => requete(sql, a),
    first: async () => db.prepare(sql).get(...args) ?? null,
    all: async () => ({ results: db.prepare(sql).all(...args) }),
    run: async () => db.prepare(sql).run(...args),
  });
  return { prepare: (sql) => requete(sql) };
}

// Une fausse liaison : l'objet du client note ce qu'il reçoit et répond comme le conteneur.
function liaison(journal, reponse = () => Response.json({ reponse: "Bonjour !" })) {
  return {
    jurisdiction: (j) => ({
      getByName: (nom) => ({
        fetch: async (r) => {
          journal.push({ j, nom, chemin: new URL(r.url).pathname + new URL(r.url).search, auth: r.headers.get("authorization"), corps: await r.text() });
          return reponse(r);
        },
        cles: async (methode, chemin, corps) => {
          journal.push({ j, nom, cles: methode, chemin, corps });
          return { statut: 200, donnees: { cles: [] } };
        },
      }),
    }),
  };
}

async function env(journal, reponse) {
  const annuaire = d1();
  await inscrire(annuaire, "cabinet", { version: 1, config: { version: 1, id: "cabinet", zone: "europe", nom_agent: "Alix" } });
  return { ADMIN_TOKEN: "admin", ANNUAIRE: annuaire, AGENTS_EUROPE: liaison(journal, reponse), AGENTS_ETATS_UNIS: liaison(journal, reponse) };
}

const message = (e, id, corps, cle = CLE, extra = {}, hote = "porte") => {
  const texte = typeof corps === "string" ? corps : JSON.stringify(corps);
  return recevoir(
    new Request(`https://${hote}/api/${id}/messages`, {
      method: "POST",
      body: texte,
      headers: { authorization: `Bearer ${cle}`, "content-type": "application/json", "content-length": String(new TextEncoder().encode(texte).length), ...extra },
    }),
    e,
  );
};

test("l'annuaire : un client sans WhatsApp, et la migration garde les numéros", async () => {
  const journal = [];
  const e = await env(journal);
  const tous = await lister(e.ANNUAIRE);
  assert.deepEqual(tous.map((c) => [c.id, c.numero_id]), [["ancien", "100000000000009"], ["cabinet", null]]);
  assert.deepEqual(await clientParNumero(e.ANNUAIRE, "100000000000009"), { id: "ancien", zone: "europe" });
  // Deux clients sans numéro ne se gênent pas ; un numéro mal formé reste refusé.
  await inscrire(e.ANNUAIRE, "site", { version: 1, config: { version: 1, id: "site", zone: "europe", whatsapp: null } });
  await assert.rejects(inscrire(e.ANNUAIRE, "faux", { version: 1, config: { id: "faux", zone: "europe", whatsapp: { numero_id: "abc" } } }), (x) => x.statut === 400);
  await assert.rejects(inscrire(e.ANNUAIRE, "faux", { version: 1, config: { id: "faux", zone: "europe", whatsapp: {} } }), (x) => x.statut === 400);
});

test("un message par API : transmis tel quel au conteneur du client, réponse rendue", async () => {
  const journal = [];
  const e = await env(journal);
  const r = await message(e, "cabinet", { personne: "patient-42", texte: "Bonjour" });
  assert.equal(r.status, 200);
  assert.deepEqual(await r.json(), { reponse: "Bonjour !" });
  assert.deepEqual(journal, [{ j: "eu", nom: "cabinet", chemin: "/api/messages", auth: `Bearer ${CLE}`, corps: JSON.stringify({ personne: "patient-42", texte: "Bonjour" }) }]);
});

test("la porte refuse sans réveiller le conteneur : clé, méthode, taille, client", async () => {
  const journal = [];
  const e = await env(journal);
  assert.equal((await message(e, "cabinet", { texte: "x" }, "")).status, 401);
  assert.equal((await message(e, "cabinet", { texte: "x" }, "mga_court")).status, 401);
  assert.equal((await message(e, "cabinet", { texte: "x" }, "admin")).status, 401);
  assert.equal((await message(e, "cabinet", "x".repeat(17 * 1024))).status, 413);
  assert.equal((await message(e, "inconnu", { texte: "x" })).status, 404);
  assert.equal((await message(e, "Cabinet", { texte: "x" })).status, 404);
  const get = await recevoir(new Request("https://porte/api/cabinet/messages", { headers: { authorization: `Bearer ${CLE}` } }), e);
  assert.equal(get.status, 405);
  const sansLongueur = await recevoir(new Request("https://porte/api/cabinet/messages", { method: "POST", body: new ReadableStream({ start: (c) => c.close() }), duplex: "half", headers: { authorization: `Bearer ${CLE}` } }), e);
  assert.equal(sansLongueur.status, 411);
  assert.deepEqual(journal, []);
});

test("la réponse du conteneur : statut, type et attente seulement", async () => {
  const journal = [];
  const e = await env(journal, () => new Response(JSON.stringify({ erreur: "trop de messages pour cette clé", attente: 12 }), { status: 429, headers: { "content-type": "application/json", "retry-after": "12", "x-interne": "secret" } }));
  const r = await message(e, "cabinet", { personne: "p1", texte: "x" });
  assert.equal(r.status, 429);
  assert.equal(r.headers.get("retry-after"), "12");
  assert.equal(r.headers.get("x-interne"), null);
});

test("la réponse au fil de l'eau : Accept transmis, flux rendu morceau par morceau", async () => {
  const journal = [];
  const vus = [];
  let pousser;
  const e = await env(journal, (r) => {
    vus.push(r.headers.get("accept"));
    const corps = new ReadableStream({ start: (c) => (pousser = c) });
    return new Response(corps, { headers: { "content-type": "text/event-stream; charset=utf-8", "x-interne": "secret" } });
  });
  const r = await message(e, "cabinet", { personne: "p1", texte: "Bonjour" }, CLE, { accept: "text/event-stream" });
  assert.equal(r.status, 200);
  assert.equal(r.headers.get("content-type"), "text/event-stream; charset=utf-8");
  assert.equal(r.headers.get("cache-control"), "no-store");
  assert.equal(r.headers.get("x-interne"), null);
  // Le premier morceau arrive au logiciel avant que le conteneur ait fini.
  const lecteur = r.body.getReader();
  const morceau = new TextEncoder().encode('event: texte\ndata: {"texte": "Bon"}\n\n');
  pousser.enqueue(morceau);
  assert.deepEqual((await lecteur.read()).value, morceau);
  pousser.close();
  assert.equal((await lecteur.read()).done, true);
  // Un autre Accept ne passe pas ; sans Accept, rien.
  await message(e, "cabinet", { personne: "p1", texte: "x" }, CLE, { accept: "application/xml" });
  await message(e, "cabinet", { personne: "p1", texte: "x" });
  assert.deepEqual(vus, ["text/event-stream", null, null]);
});

test("un conteneur injoignable : 503, sans texte du message dans le journal", async () => {
  const journal = [];
  const e = await env(journal, () => {
    throw new Error("le conteneur ne répond pas");
  });
  const erreurs = [];
  const avant = console.error;
  console.error = (...a) => erreurs.push(a.join(" "));
  try {
    const r = await message(e, "cabinet", { personne: "p1", texte: "mon secret médical" });
    assert.equal(r.status, 503);
  } finally {
    console.error = avant;
  }
  assert.equal(erreurs.length, 1);
  assert.ok(!erreurs[0].includes("médical") && !erreurs[0].includes("p1"));
});

test("les clés : jeton d'administration, méthodes et chemins bornés", async () => {
  const journal = [];
  const e = await env(journal);
  const appel = (methode, chemin = "", corps, jeton = "admin") =>
    recevoir(new Request(`https://porte/admin/clients/cabinet/cles${chemin}`, { method: methode, body: corps ? JSON.stringify(corps) : undefined, headers: { authorization: `Bearer ${jeton}` } }), e);
  assert.equal((await appel("GET", "", null, "autre")).status, 401);
  assert.equal((await appel("GET")).status, 200);
  assert.equal((await appel("POST", "", { id: "0123456789ab", logiciel: "dossier", empreinte: "0".repeat(64) })).status, 200);
  assert.equal((await appel("DELETE", "/0123456789ab")).status, 200);
  assert.equal((await appel("DELETE", "/autre")).status, 400);
  assert.equal((await appel("DELETE")).status, 405);
  assert.equal((await appel("PUT")).status, 405);
  assert.deepEqual(journal.map((j) => [j.cles, j.chemin]), [["GET", ""], ["POST", ""], ["DELETE", "/0123456789ab"]]);
});

test("l'objet du client : les clés passent au conteneur avec le jeton interne", async () => {
  const appels = [];
  const ctx = {
    id: { name: "cabinet" },
    blockConcurrencyWhile: (f) => f(),
    storage: { get: async () => undefined, put: async () => {} },
    container: {
      running: true,
      setInactivityTimeout: async () => {},
      getTcpPort: () => ({
        fetch: async (u, o) => {
          appels.push([o.method, new URL(u).pathname, o.headers["x-megga-interne"], o.body ?? null]);
          return Response.json({ ok: true });
        },
      }),
    },
  };
  const a = new AgentEurope(ctx, { ADMIN_TOKEN: "admin" });
  a.demarrer = async () => {};
  const jeton = await jetonInterne("admin", "cabinet");
  assert.deepEqual(await a.cles("POST", "", { id: "x" }), { statut: 200, donnees: { ok: true } });
  await a.cles("DELETE", "/0123456789ab");
  assert.deepEqual(appels, [["POST", "/interne/cles", jeton, '{"id":"x"}'], ["DELETE", "/interne/cles/0123456789ab", jeton, null]]);
  await assert.rejects(a.cles("GET", "/../rappels"), /chemin de clé/);
  // Le suivi d'une personne venue par API se lit aussi.
  await a.suivre("/conversations/api:dossier:patient-42");
  assert.equal(appels.at(-1)[1], "/interne/suivi/conversations/api%3Adossier%3Apatient-42");
});

test("api.megga.ai : l'adresse publique ne sert que l'entrée par API", async () => {
  const journal = [];
  const e = await env(journal);
  const r = await message(e, "cabinet", { personne: "patient-42", texte: "Bonjour" }, CLE, {}, "api.megga.ai");
  assert.equal(r.status, 200);
  assert.deepEqual(await r.json(), { reponse: "Bonjour !" });
  assert.equal(journal.length, 1);
  // Ni Meta, ni l'administration, ni l'atelier, ni le pilotage, ni la page d'accueil
  const essais = [
    ["GET", "/"],
    ["GET", "/meta?hub.mode=subscribe"],
    ["POST", "/meta"],
    ["GET", "/admin/clients"],
    ["GET", "/admin/clients/cabinet/cles"],
    ["POST", "/admin/redemarrer"],
    ["GET", "/atelier/catalogue"],
    ["POST", "/pilotage/releve"],
    ["POST", "/api/cabinet/autre"],
    ["POST", "/api/cabinet/messages/en-trop"],
  ];
  for (const [methode, chemin] of essais) {
    const x = await recevoir(new Request(`https://api.megga.ai${chemin}`, { method: methode, headers: { authorization: "Bearer admin" } }), e);
    assert.equal(x.status, 404, `${methode} ${chemin}`);
  }
  assert.equal(journal.length, 1);
  // L'hôte se règle (API_HOTE) ; workers.dev sert toujours l'administration et, en secours, l'API.
  const e2 = { ...e, API_HOTE: "api.essai.invalid" };
  assert.equal((await recevoir(new Request("https://api.essai.invalid/admin/clients", { headers: { authorization: "Bearer admin" } }), e2)).status, 404);
  assert.equal((await recevoir(new Request("https://megga-agents.essai.workers.dev/admin/clients/cabinet/cles", { headers: { authorization: "Bearer admin" } }), e)).status, 200);
  assert.equal((await message(e, "cabinet", { personne: "p1", texte: "x" }, CLE, {}, "megga-agents.essai.workers.dev")).status, 200);
});

// Lot 7.4 : le site d'un client (un bien entré en ligne, une demande d'information), transmis tel quel.
const CLE_SITE = "s".repeat(40);
const duSite = (e, id, route, corps, cle = CLE_SITE, methode = "POST") => {
  const texte = JSON.stringify(corps);
  return recevoir(
    new Request(`https://porte/site/${id}/${route}`, {
      method: methode,
      body: methode === "POST" ? texte : undefined,
      headers: { authorization: `Bearer ${cle}`, "content-type": "application/json", "content-length": String(new TextEncoder().encode(texte).length) },
    }),
    e,
  );
};

test("le site d'un client : transmis tel quel, refusé sans réveiller le conteneur", async () => {
  const journal = [];
  const e = await env(journal, () => Response.json({ signale: "G8LR2DW8" }, { status: 202 }));
  const r = await duSite(e, "cabinet", "bien", { reference: "G8LR2DW8" });
  assert.equal(r.status, 202);
  assert.deepEqual(await r.json(), { signale: "G8LR2DW8" });
  assert.deepEqual(journal, [{ j: "eu", nom: "cabinet", chemin: "/site/bien", auth: `Bearer ${CLE_SITE}`, corps: JSON.stringify({ reference: "G8LR2DW8" }) }]);
  assert.equal((await duSite(e, "cabinet", "demande", { nom: "Anna" })).status, 202);
  journal.length = 0;
  assert.equal((await duSite(e, "cabinet", "bien", {}, "court")).status, 401);
  assert.equal((await duSite(e, "cabinet", "bien", {}, "")).status, 401);
  assert.equal((await duSite(e, "cabinet", "bien", { x: "y".repeat(17 * 1024) })).status, 413);
  assert.equal((await duSite(e, "inconnu", "bien", {})).status, 404);
  assert.equal((await duSite(e, "cabinet", "bien", {}, CLE_SITE, "GET")).status, 405);
  assert.equal((await duSite(e, "cabinet", "autre", {})).status, 404);
  // Sur l'hôte de l'API, rien d'autre que /api/…
  const hote = await recevoir(new Request("https://api.megga.ai/site/cabinet/bien", { method: "POST", body: "{}", headers: { authorization: `Bearer ${CLE_SITE}`, "content-length": "2" } }), e);
  assert.equal(hote.status, 404);
  assert.deepEqual(journal, []);
});

test("le journal des conversations, pour la gestion du site : lu, jamais gardé", async () => {
  const journal = [];
  const e = await env(journal, () => Response.json({ total: 1, personnes: [] }));
  const lire = (chemin, cle = CLE_SITE, methode = "GET") =>
    recevoir(new Request(`https://porte${chemin}`, { method: methode, headers: { authorization: `Bearer ${cle}` } }), e);
  const r = await lire("/site/cabinet/journal?jours=7&qui=Marion"); // qui : jamais transmis
  assert.equal(r.status, 200);
  assert.equal(r.headers.get("cache-control"), "no-store");
  assert.deepEqual(await r.json(), { total: 1, personnes: [] });
  assert.equal(journal.length, 1);
  assert.equal(journal[0].chemin, "/site/journal?jours=7");
  assert.equal(journal[0].auth, `Bearer ${CLE_SITE}`);
  journal.length = 0;
  assert.equal((await lire("/site/cabinet/journal?jours=abc")).status, 200);
  assert.equal(journal[0].chemin, "/site/journal?jours=1");
  journal.length = 0;
  assert.equal((await lire("/site/cabinet/journal", "court")).status, 401);
  assert.equal((await lire("/site/cabinet/journal", CLE_SITE, "POST")).status, 405);
  assert.equal((await lire("/site/inconnu/journal")).status, 404);
  assert.deepEqual(journal, []);
});
