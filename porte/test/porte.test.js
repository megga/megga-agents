import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import { test } from "node:test";
import { AgentEurope } from "../src/agent.js";
import { recevoir } from "../src/index.js";
import { defiAbonnement, egal, numerosDe, signatureValide } from "../src/meta.js";
import { agentDe } from "../src/zones.js";

const SECRET = "secret-essai";
const signe = (c) => "sha256=" + createHmac("sha256", SECRET).update(c).digest("hex");
const corps = (numero = "100000000000001") =>
  JSON.stringify({ object: "whatsapp_business_account", entry: [{ changes: [{ field: "messages", value: { metadata: { phone_number_id: numero }, messages: [{ from: "41790000000", id: "w1", type: "text", text: { body: "Bonjour" } }] } }] }] });

// Un faux annuaire D1.
function annuaire(clients) {
  return {
    prepare: (sql) => ({
      bind: (v) => ({
        first: async () => clients.find((c) => c.actif !== 0 && (sql.includes("numero_id") ? c.numero_id === v : c.id === v)) ?? null,
      }),
    }),
  };
}

// Une fausse liaison de Durable Objects, qui note les juridictions et les envois.
function liaison(journal) {
  return {
    jurisdiction: (j) => ({
      getByName: (nom) => ({
        fetch: async (r) => {
          journal.push({ j, nom, chemin: new URL(r.url).pathname, signature: r.headers.get("x-hub-signature-256"), corps: await r.text() });
          return new Response("reçu 1");
        },
        poserSecrets: async (s) => {
          journal.push({ j, nom, secrets: Object.keys(s) });
          return Object.keys(s);
        },
      }),
    }),
  };
}

const CLIENTS = [
  { id: "essai-eu", numero_id: "100000000000001", zone: "europe", config: "{}" },
  { id: "essai-us", numero_id: "100000000000002", zone: "etats-unis", config: "{}" },
  { id: "eteint", numero_id: "100000000000003", zone: "europe", config: "{}", actif: 0 },
];

function env(journal) {
  return { META_APP_SECRET: SECRET, META_VERIFY_TOKEN: "jeton", ADMIN_TOKEN: "admin", ANNUAIRE: annuaire(CLIENTS), AGENTS_EUROPE: liaison(journal), AGENTS_ETATS_UNIS: liaison(journal) };
}

test("signature", async () => {
  const c = corps();
  assert.equal(await signatureValide(c, signe(c), SECRET), true);
  assert.equal(await signatureValide(c, signe(c), "autre"), false);
  assert.equal(await signatureValide(c, "sha256=xyz", SECRET), false);
  assert.equal(await signatureValide(c, signe(c), ""), false);
});

test("numéros d'un webhook", () => {
  assert.deepEqual(numerosDe(JSON.parse(corps())), ["100000000000001"]);
  assert.deepEqual(numerosDe({ object: "autre" }), []);
});

test("abonnement du webhook", () => {
  assert.equal(defiAbonnement("https://x/meta?hub.mode=subscribe&hub.verify_token=jeton&hub.challenge=42", "jeton"), "42");
  assert.equal(defiAbonnement("https://x/meta?hub.mode=subscribe&hub.verify_token=faux&hub.challenge=42", "jeton"), null);
  assert.equal(defiAbonnement("https://x/meta?hub.mode=subscribe&hub.verify_token=&hub.challenge=42", ""), null);
  assert.ok(egal("abc", "abc") && !egal("abc", "abd") && !egal("abc", "abcd"));
});

test("chaque client va dans sa juridiction", () => {
  const journal = [];
  const e = env(journal);
  assert.ok(agentDe(e, { id: "a", zone: "europe" }));
  assert.equal(agentDe(e, { id: "a", zone: "suisse" }), null);
  assert.equal(agentDe(e, { id: "a", zone: "client" }), null);
});

test("un webhook signé est transmis tel quel au bon client", async () => {
  const journal = [];
  const c = corps();
  const r = await recevoir(new Request("https://porte/meta", { method: "POST", body: c, headers: { "x-hub-signature-256": signe(c) } }), env(journal));
  assert.equal(await r.text(), "reçu 1");
  assert.deepEqual(journal, [{ j: "eu", nom: "essai-eu", chemin: "/whatsapp", signature: signe(c), corps: c }]);
});

test("zone États-Unis, client éteint, numéro inconnu", async () => {
  const journal = [];
  for (const n of ["100000000000002", "100000000000003", "100000000000099"]) {
    const c = corps(n);
    await recevoir(new Request("https://porte/meta", { method: "POST", body: c, headers: { "x-hub-signature-256": signe(c) } }), env(journal));
  }
  assert.deepEqual(journal.map((x) => [x.j, x.nom]), [["us", "essai-us"]]);
});

test("webhook sans signature valide : rien n'est transmis", async () => {
  const journal = [];
  const r = await recevoir(new Request("https://porte/meta", { method: "POST", body: corps(), headers: { "x-hub-signature-256": "sha256=" + "0".repeat(64) } }), env(journal));
  assert.equal(r.status, 401);
  assert.equal(journal.length, 0);
});

test("secrets d'un client : jeton exigé, écriture seule", async () => {
  const journal = [];
  const put = (jeton, id = "essai-eu") =>
    recevoir(new Request(`https://porte/admin/clients/${id}/secrets`, { method: "PUT", body: JSON.stringify({ DATABASE_URL: "postgresql://x" }), headers: { authorization: `Bearer ${jeton}` } }), env(journal));
  assert.equal((await put("faux")).status, 401);
  assert.equal((await put("admin", "inconnu")).status, 404);
  const r = await put("admin");
  assert.equal(await r.text(), "rangés : DATABASE_URL");
  assert.equal(JSON.stringify(journal).includes("postgresql://x"), false);
});

test("l'objet ne garde que les secrets prévus, sans les rendre", async () => {
  const stock = new Map();
  const ctx = { storage: { get: async (k) => stock.get(k), put: async (k, v) => stock.set(k, v) }, container: { running: false } };
  const a = new AgentEurope(ctx, {});
  assert.deepEqual(await a.poserSecrets({ DATABASE_URL: "postgresql://x", AUTRE: "y" }), ["DATABASE_URL"]);
  assert.deepEqual(stock.get("secrets"), { DATABASE_URL: "postgresql://x" });
  await assert.rejects(a.poserSecrets({ AUTRE: "y" }));
});

test("les simples accusés de Meta ne réveillent pas le conteneur ; un envoi refusé, si", () => {
  const statut = (s) => ({ object: "whatsapp_business_account", entry: [{ changes: [{ field: "messages", value: { metadata: { phone_number_id: "100000000000001" }, statuses: [{ status: s }] } }] }] });
  for (const s of ["sent", "delivered", "read"]) assert.deepEqual(numerosDe(statut(s)), []);
  assert.deepEqual(numerosDe(statut("failed")), ["100000000000001"]);
});
