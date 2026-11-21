// Les alertes envoyées (20.11.2026) : le déclencheur fait évaluer l'atelier, la porte envoie les courriels.
import assert from "node:assert/strict";
import { test } from "node:test";
import { courrielHtml, courrielValide, francais, evaluerAlertes, evaluerRecharges } from "../src/alertes.js";
import { declencher, recevoir, stripeBienForme } from "../src/index.js";

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
  assert.deepEqual(envoyes, [{ to: COURRIEL.a, from: { email: "alertes@megga.ai", name: "MEGGA" }, subject: COURRIEL.sujet, text: francais(COURRIEL.texte), html: courrielHtml(COURRIEL.sujet, COURRIEL.texte) }]);
  assert.equal((await poster({ ...COURRIEL, a: "x" }, env)).status, 400);
  const refuse = { ...env, COURRIEL: { send: async () => { throw Object.assign(new Error("julien@example.com"), { code: "E_REFUS" }); } } };
  const r2 = await poster(COURRIEL, refuse);
  assert.equal(r2.status, 502);
  assert.ok(!(await r2.text()).includes("julien@example.com"));
  assert.equal((await poster(COURRIEL, { ADMIN_TOKEN: "admin" })).status, 503); // liaison absente
});

test("le courriel au dessin de MEGGA : le sujet en titre, le texte échappé, le bouton vers les alertes", () => {
  const html = courrielHtml("Alerte : <b>Exemple</b> & Cie", "Ligne une.\n\nLigne <deux>.");
  assert.ok(html.includes("Alerte : &lt;b&gt;Exemple&lt;/b&gt; &amp; Cie"));
  assert.ok(html.includes(">Ligne une.</td>") && html.includes(">Ligne &lt;deux&gt;.</td>"));
  assert.ok(!html.includes("<deux>") && !html.includes("<b>Exemple"));
  assert.ok(html.includes('alt="MEGGA"') && html.includes('href="https://console.megga.ai/admin/alertes"'));
  assert.ok(html.includes('bgcolor="#03030f"')); // le bloc bleu foncé, aussi pour les messageries qui ignorent les styles
  assert.ok(!/[\u2014\u2013\u00b7]/.test(html)); // ni tiret long ni point médian
});

test("des textes harmonisés : le titre une fois, la typographie française", () => {
  assert.equal(francais("Tours en échec : 12 % ; « oui » ?"), "Tours en échec\u00a0: 12 %\u00a0; «\u00a0oui\u00a0»\u00a0?");
  assert.equal(francais("Prix: 3"), "Prix\u00a0: 3");
  const html = courrielHtml("Alerte : Agent silencieux, Exemple SA", "Alerte : Agent silencieux, Exemple SA.\nSans relevé depuis 52 minutes.");
  assert.equal(html.split("Agent silencieux").length - 1, 2); // le titre de la page et le titre du courriel, pas le texte
  assert.ok(html.includes("Alerte\u00a0: Agent silencieux") && html.includes(">Sans relevé depuis 52 minutes.</td>"));
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
  assert.deepEqual(await Promise.all(attendus), [200, 200]);
  // Après les alertes, les recharges sous le seuil (Stripe).
  assert.deepEqual(vues.slice(1).map((v) => v[1]), ["/atelier/alertes/evaluer", "/atelier/recharges/evaluer"]);
  assert.equal(await evaluerRecharges({ ADMIN_TOKEN: "admin" }, null), null);
});

test("un événement de Stripe : signature et longueur bien formées, sinon l'atelier ne se réveille pas", async () => {
  const signature = "t=1794950000,v1=" + "a".repeat(64);
  const entetes = (s, l = "20") => new Headers({ "stripe-signature": s, "content-length": l });
  assert.equal(stripeBienForme(entetes(signature)), true);
  assert.equal(stripeBienForme(entetes("t=1794950000,v0=abc,v1=" + "b".repeat(64))), true);
  for (const faux of [entetes(""), entetes("t=x,v1=" + "a".repeat(64)), entetes("t=1,v1=court"), entetes(signature, String(300 * 1024)),
    new Headers({ "stripe-signature": signature })]) {
    assert.equal(stripeBienForme(faux), false);
  }
  const vus = [];
  const env = { ATELIER: { jurisdiction: () => ({ getByName: () => ({ fetch: async (r) => { vus.push(new URL(r.url).pathname); return new Response("{}"); } }) }) } };
  const corps = '{"type":"x"}';
  const envoyer = (s) => recevoir(new Request("https://porte.essai/stripe", { method: "POST", headers: { "stripe-signature": s, "content-length": String(corps.length) }, body: corps }), env);
  assert.equal((await envoyer("t=1,v1=faux")).status, 400);
  assert.deepEqual(vus, []);
  assert.equal((await envoyer(signature)).status, 200);
  assert.deepEqual(vus, ["/stripe"]);
});
