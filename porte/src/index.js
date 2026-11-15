// La porte des agents MEGGA : le seul point public des zones Europe et États-Unis.
//
//   GET  /meta                     l'abonnement du webhook de l'app Meta « Alix MEGGA »
//   POST /meta                     un webhook : signature vérifiée, puis transmis tel quel
//                                  au conteneur de chaque client concerné
//   PUT  /admin/clients/:id/secrets les secrets d'un client (jeton ADMIN_TOKEN), écriture seule
//
// Elle ne garde aucun message et ne journalise ni texte ni numéro de personne.
// Le routeur megga-whatsapp (megga-erp) et l'app « Alix FSP » ne passent pas ici.
import { clientParId, clientParNumero, idValide } from "./annuaire.js";
import { defiAbonnement, egal, numerosDe, signatureValide } from "./meta.js";
import { agentDe } from "./zones.js";

export { AgentEtatsUnis, AgentEurope } from "./agent.js";

const texte = (t, status = 200) => new Response(t, { status, headers: { "content-type": "text/plain; charset=utf-8" } });

export async function recevoir(requete, env, ctx) {
  const url = new URL(requete.url);
  if (url.pathname === "/" && requete.method === "GET") return texte("ok");
  if (url.pathname === "/meta" && requete.method === "GET") {
    const defi = defiAbonnement(requete.url, env.META_VERIFY_TOKEN);
    return defi === null ? texte("refusé", 403) : texte(defi);
  }
  if (url.pathname === "/meta" && requete.method === "POST") return webhook(requete, env, ctx);
  const admin = url.pathname.match(/^\/admin\/clients\/([^/]+)\/secrets$/);
  if (admin && requete.method === "PUT") return secrets(requete, env, admin[1]);
  return texte("introuvable", 404);
}

async function webhook(requete, env, ctx) {
  if (!env.META_APP_SECRET) return texte("configuration", 503);
  const corps = await requete.arrayBuffer();
  const signature = requete.headers.get("x-hub-signature-256");
  if (!(await signatureValide(corps, signature, env.META_APP_SECRET))) return texte("signature", 401);
  let evenement;
  try {
    evenement = JSON.parse(new TextDecoder().decode(corps));
  } catch {
    return texte("corps", 400);
  }
  let transmis = 0;
  for (const numero of numerosDe(evenement)) {
    const client = await clientParNumero(env.ANNUAIRE, numero);
    const agent = client && agentDe(env, client);
    if (!agent) {
      console.warn("numéro sans client servi ici");
      continue;
    }
    // Meta veut une réponse rapide : le conteneur peut mettre quelques secondes à se réveiller.
    const envoi = agent
      .fetch(new Request("http://agent/whatsapp", { method: "POST", body: corps, headers: { "x-hub-signature-256": signature, "content-type": "application/json" } }))
      .then((r) => r.body?.cancel())
      .catch((e) => console.error("transmission en échec", client.id, String(e?.message ?? e).slice(0, 200)));
    ctx?.waitUntil ? ctx.waitUntil(envoi) : await envoi;
    transmis++;
  }
  return texte(`reçu ${transmis}`);
}

async function secrets(requete, env, id) {
  const jeton = (requete.headers.get("authorization") ?? "").replace(/^Bearer /, "");
  if (!env.ADMIN_TOKEN || !egal(jeton, env.ADMIN_TOKEN)) return texte("refusé", 401);
  if (!idValide(id)) return texte("identifiant", 400);
  const client = await clientParId(env.ANNUAIRE, id);
  const agent = client && agentDe(env, client);
  if (!agent) return texte("client inconnu", 404);
  let corps;
  try {
    corps = await requete.json();
  } catch {
    return texte("corps", 400);
  }
  try {
    const noms = await agent.poserSecrets(corps);
    return texte(`rangés : ${noms.join(", ")}`);
  } catch (e) {
    return texte(String(e?.message ?? e).slice(0, 100), 400);
  }
}

export default { fetch: recevoir };
