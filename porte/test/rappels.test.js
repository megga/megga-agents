import assert from "node:assert/strict";
import { test } from "node:test";
import { AgentEurope, jetonInterne } from "../src/agent.js";

// Un faux objet : stockage avec alarme, conteneur qui répond aux routes internes.
function objet(reponse = { prochain: null }) {
  const journal = [];
  let alarme = null;
  const ctx = {
    id: { name: "essai" },
    blockConcurrencyWhile: (f) => f(),
    storage: { getAlarm: async () => alarme, setAlarm: async (t) => { alarme = t; journal.push(["alarme", t]); } },
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
  return { a, journal, alarme: () => alarme };
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
  assert.equal(alarme(), Math.round(dans1h * 1000));
});

test("sans rappel à venir, aucune alarme", async () => {
  const { a, alarme } = objet({ prochain: null });
  await a.alarm();
  assert.equal(alarme(), null);
});
