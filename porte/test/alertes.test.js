// Les alertes envoyées (20.11.2026) : le déclencheur fait évaluer l'atelier, la porte envoie les courriels.
import assert from "node:assert/strict";
import { test } from "node:test";
import { courrielValide, evaluerAlertes } from "../src/alertes.js";
import { declencher, recevoir } from "../src/index.js";

const COURRIEL = { a: "julien@example.com", sujet: "Alerte : Tours en échec, Exemple SA", texte: "Tours en échec : 12 %." };

function poster(corps, env, jeton = "admin") {
  return recevoir(
    new Request("https://porte.essai/admin/courriel", {
      method: "POST",
      headers: { authorization: `Bearer ${jeton}`, "content-type": "application/json" },
      body: JSON.stringify(corps),
    }),
    env,
  );
}

test("un courriel d'alerte : une adresse, un sujet d'une ligne, un texte borné", () => {
  assert.deepEqual(courrielValide(COURRIEL), COURRIEL);
  for (const faux of [
    { ...COURRIEL, a: "pas une adresse" },
    { ...COURRIEL, a: ["julien@example.com"] },
    { ...COURRIEL, sujet: "Alerte\r\nBcc: autre@example.com" },
    { ...COURRIEL, sujet: "" },
    { ...COURRIEL, texte: "x".repeat(4001) },
    null,
  ]) {
    assert.equal(courrielValide(faux), null);
  }
});

test("la porte envoie le courriel par sa liaison, jeton d'administration exigé", async () => {
  const envoyes = [];
  const env = { ADMIN_TOKEN: "admin", COURRIEL_DE: "alertes@megga.ai", COURRIEL: { send: async (m) => envoyes.push(m) } };
  assert.equal((await poster(COURRIEL, env, "faux")).status, 401);
  assert.equal(envoyes.length, 0);
  const r = await poster(COURRIEL, env);
  assert.equal(r.status, 200);
  assert.deepEqual(envoyes, [{ to: COURRIEL.a, from: { email: "alertes@megga.ai", name: "MEGGA" }, subject: COURRIEL.sujet, text: COURRIEL.texte }]);
  assert.equal((await poster({ ...COURRIEL, a: "x" }, env)).status, 400);
  const refuse = { ...env, COURRIEL: { send: async () => { throw Object.assign(new Error("julien@example.com"), { code: "E_REFUS" }); } } };
  const r2 = await poster(COURRIEL, refuse);
  assert.equal(r2.status, 502);
  assert.ok(!(await r2.text()).includes("julien@example.com"));
  assert.equal((await poster(COURRIEL, { ADMIN_TOKEN: "admin" })).status, 503); // liaison absente
});

test("le déclencheur demande l'évaluation à l'atelier, avec le jeton de MEGGA", async () => {
  const vues = [];
  const atelier = { fetch: async (r) => { vues.push([r.method, new URL(r.url).pathname, r.headers.get("authorization")]); return new Response("{}"); } };
  assert.equal(await evaluerAlertes({ ADMIN_TOKEN: "admin" }, atelier), 200);
  assert.deepEqual(vues, [["POST", "/atelier/alertes/evaluer", "Bearer admin"]]);
  assert.equal(await evaluerAlertes({ ADMIN_TOKEN: "admin" }, { fetch: async () => { throw new Error("injoignable"); } }), 0);
  assert.equal(await evaluerAlertes({ ADMIN_TOKEN: "admin" }, null), null);

  const attendus = [];
  const env = { ADMIN_TOKEN: "admin", ATELIER: { jurisdiction: () => ({ getByName: () => atelier }) } };
  declencher({}, env, { waitUntil: (p) => attendus.push(p) });
  assert.equal(await attendus[0], 200);
  assert.equal(vues.length, 2);
});
