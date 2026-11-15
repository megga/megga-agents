// La porte des agents MEGGA : le seul point public des zones Europe et États-Unis.
//
//   GET  /meta                     l'abonnement du webhook de l'app Meta « Alix MEGGA »
//   POST /meta                     un webhook : signature vérifiée, puis transmis tel quel
//                                  au conteneur de chaque client concerné
//   PUT  /admin/clients/:id/secrets les secrets d'un client (jeton ADMIN_TOKEN), écriture seule
//   PUT  /admin/clients/:id/config  la configuration mise en service par l'atelier : annuaire,
//                                  puis redémarrage du conteneur du client (jeton ADMIN_TOKEN)
//   GET  /admin/clients[?id=]      les clients de l'annuaire et l'état de leur conteneur
//   GET  /admin/clients/:id/suivi[/conversations[/:personne]|/alertes]
//                                  le suivi d'un client, lu dans son conteneur (jeton ADMIN_TOKEN)
//   PUT  /admin/atelier/secrets    la base de l'atelier (jeton ADMIN_TOKEN), écriture seule
//   POST /admin/redemarrer         après un déploiement : chaque conteneur allumé finit ses tours,
//                                  puis repart sur la nouvelle image (jeton ADMIN_TOKEN)
//   *    /atelier/…                l'API de l'atelier, transmise telle quelle à son conteneur,
//                                  qui vérifie lui-même les jetons (MEGGA ou client)
//   POST /pilotage/…               le pilote d'une installation hors Cloudflare (chez le client, zone
//                                  suisse) : requête signée de sa clé, transmise à l'atelier qui la vérifie
//
// Elle ne garde aucun message et ne journalise ni texte ni numéro de personne.
// Le routeur megga-whatsapp (megga-erp) et l'app « Alix FSP » ne passent pas ici.
import { RefusAnnuaire, clientParId, clientParNumero, idValide, inscrire, lister } from "./annuaire.js";
import { defiAbonnement, egal, numerosDe, signatureValide } from "./meta.js";
import { agentDe } from "./zones.js";

export { AgentEtatsUnis, AgentEurope, Atelier } from "./agent.js";

const texte = (t, status = 200) => new Response(t, { status, headers: { "content-type": "text/plain; charset=utf-8" } });
const json = (v, status = 200) => Response.json(v, { status });
const autorise = (requete, env) => Boolean(env.ADMIN_TOKEN) && egal((requete.headers.get("authorization") ?? "").replace(/^Bearer /, ""), env.ADMIN_TOKEN);
// L'atelier est unique, en zone Europe.
const atelierDe = (env) => env.ATELIER?.jurisdiction("eu").getByName("megga") ?? null;
// Le pilotage : l'heure d'une requête signée, à 5 minutes près, et un relevé de 256 Kio au plus.
const FENETRE_PILOTAGE_S = 300;
const TAILLE_PILOTAGE = 256 * 1024;

export async function recevoir(requete, env, ctx) {
  const url = new URL(requete.url);
  if (url.pathname === "/" && requete.method === "GET") return texte("ok");
  if (url.pathname === "/meta" && requete.method === "GET") {
    const defi = defiAbonnement(requete.url, env.META_VERIFY_TOKEN);
    return defi === null ? texte("refusé", 403) : texte(defi);
  }
  if (url.pathname === "/meta" && requete.method === "POST") return webhook(requete, env, ctx);
  const admin = url.pathname.match(/^\/admin\/clients\/([^/]+)\/(secrets|config)$/);
  if (admin && requete.method === "PUT") return admin[2] === "secrets" ? secrets(requete, env, admin[1]) : configuration(requete, env, admin[1]);
  if (url.pathname === "/admin/clients" && requete.method === "GET") return clients(requete, env, url.searchParams.get("id"));
  const suivi = url.pathname.match(/^\/admin\/clients\/([^/]+)\/suivi(\/.*)?$/);
  if (suivi && requete.method === "GET") return suivre(requete, env, suivi[1], suivi[2] ?? "", url.searchParams);
  if (url.pathname === "/admin/atelier/secrets" && requete.method === "PUT") return secretsAtelier(requete, env);
  if (url.pathname === "/admin/redemarrer" && requete.method === "POST") return redemarrerTout(requete, env);
  if (url.pathname === "/pilotage" || url.pathname.startsWith("/pilotage/")) return pilote(requete, env);
  if (url.pathname === "/atelier" || url.pathname.startsWith("/atelier/")) {
    // Sans jeton, rien ne réveille le conteneur de l'atelier ; c'est lui qui vérifie le jeton.
    if (!/^Bearer \S+$/.test(requete.headers.get("authorization") ?? "")) return texte("jeton attendu", 401);
    const atelier = atelierDe(env);
    return atelier ? atelier.fetch(requete) : texte("atelier absent", 503);
  }
  return texte("introuvable", 404);
}

/**
 * Une requête de pilote bien formée : installation, heure récente, nonce et signature (noyau/pilotage.py).
 * La porte ne connaît pas les clés des installations : l'atelier vérifie la signature elle-même.
 */
export function pilotageBienForme(entetes, maintenant = Date.now()) {
  const heure = entetes.get("x-megga-heure") ?? "";
  return (
    idValide(entetes.get("x-megga-installation")) &&
    /^[0-9]{1,12}$/.test(heure) &&
    Math.abs(maintenant / 1000 - Number(heure)) <= FENETRE_PILOTAGE_S &&
    /^[0-9a-f]{32}$/.test(entetes.get("x-megga-nonce") ?? "") &&
    /^[A-Za-z0-9_-]{86}$/.test(entetes.get("x-megga-signature") ?? "")
  );
}

/** Le pilote d'une installation : sans requête signée et récente, rien ne réveille l'atelier. */
async function pilote(requete, env) {
  if (requete.method !== "POST") return texte("méthode", 405);
  if (!pilotageBienForme(requete.headers)) return texte("requête signée attendue", 401);
  if (Number(requete.headers.get("content-length") ?? 0) > TAILLE_PILOTAGE) return texte("relevé trop gros", 413);
  const atelier = atelierDe(env);
  return atelier ? atelier.fetch(requete) : texte("atelier absent", 503);
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
  if (!autorise(requete, env)) return texte("refusé", 401);
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

/** La configuration mise en service par l'atelier : l'annuaire d'abord, puis le conteneur redémarre. */
async function configuration(requete, env, id) {
  if (!autorise(requete, env)) return texte("refusé", 401);
  if (!idValide(id)) return texte("identifiant", 400);
  let corps;
  try {
    corps = await requete.json();
  } catch {
    return texte("corps", 400);
  }
  const agent = agentDe(env, { id, zone: corps?.config?.zone });
  if (!agent) return texte("zone non servie ici", 400);
  try {
    await inscrire(env.ANNUAIRE, id, corps);
  } catch (e) {
    if (e instanceof RefusAnnuaire) return texte(e.message, e.statut);
    throw e;
  }
  // Le conteneur relit sa configuration au démarrage : il redémarre dès qu'il a fini ses tours.
  // L'annuaire est déjà à jour : un échec ici n'annule rien, il est rendu à l'atelier.
  try {
    const redemarre = await agent.redemarrer();
    return json({ ok: true, id, version: corps.version, redemarre });
  } catch (e) {
    console.error("redémarrage en échec", id, String(e?.message ?? e).slice(0, 200));
    return json({ ok: true, id, version: corps.version, redemarre: null, alerte: "redémarrage en échec : la configuration s'appliquera au prochain réveil" });
  }
}

async function clients(requete, env, seul) {
  if (!autorise(requete, env)) return texte("refusé", 401);
  const tous = (await lister(env.ANNUAIRE)).filter((c) => !seul || c.id === seul);
  const etats = await Promise.all(
    tous.map((c) => (agentDe(env, c)?.etat() ?? Promise.resolve(null)).catch(() => null)),
  );
  return json({ clients: tous.map((c, i) => ({ ...c, conteneur: etats[i] })) });
}

/** Le suivi d'un client : la porte ne lit rien elle-même, elle transmet à son conteneur et rend la réponse. */
async function suivre(requete, env, id, chemin, params) {
  if (!autorise(requete, env)) return texte("refusé", 401);
  const client = await clientParId(env.ANNUAIRE, id);
  const agent = client && agentDe(env, client);
  if (!agent) return texte("client inconnu", 404);
  const gardes = new URLSearchParams();
  for (const k of ["depuis", "limite"]) {
    const v = params.get(k);
    if (v !== null && /^\d{1,12}(\.\d+)?$/.test(v)) gardes.set(k, v);
  }
  const recherche = gardes.size ? `?${gardes}` : "";
  let lu;
  try {
    lu = decodeURIComponent(chemin);
  } catch {
    return texte("chemin de suivi", 400);
  }
  try {
    const { statut, donnees } = await agent.suivre(lu, recherche);
    return json(donnees, statut);
  } catch (e) {
    const message = String(e?.message ?? e).slice(0, 200);
    return json({ erreur: message === "chemin de suivi" ? message : "conteneur injoignable" }, message === "chemin de suivi" ? 400 : 503);
  }
}

/**
 * Après un déploiement, un conteneur déjà allumé garde l'ancienne image jusqu'à son sommeil.
 * Celui de chaque client actif redémarre en douceur (ses tours finis) ; celui de l'atelier, tout de suite.
 */
async function redemarrerTout(requete, env) {
  if (!autorise(requete, env)) return texte("refusé", 401);
  const actifs = (await lister(env.ANNUAIRE)).filter((c) => c.actif);
  const clients = await Promise.all(
    actifs.map(async (c) => {
      const agent = agentDe(env, c);
      if (!agent) return { id: c.id, redemarre: null, erreur: "zone non servie ici" };
      try {
        return { id: c.id, redemarre: await agent.redemarrer() };
      } catch {
        return { id: c.id, redemarre: null, erreur: "objet injoignable" };
      }
    }),
  );
  let atelier = null;
  try {
    atelier = (await atelierDe(env)?.redemarrer()) ?? null;
  } catch {
    atelier = null;
  }
  return json({ clients, atelier });
}

async function secretsAtelier(requete, env) {
  if (!autorise(requete, env)) return texte("refusé", 401);
  const atelier = atelierDe(env);
  if (!atelier) return texte("atelier absent", 503);
  let corps;
  try {
    corps = await requete.json();
  } catch {
    return texte("corps", 400);
  }
  try {
    const noms = await atelier.poserSecrets(corps);
    return texte(`rangés : ${noms.join(", ")}`);
  } catch (e) {
    return texte(String(e?.message ?? e).slice(0, 100), 400);
  }
}

export default { fetch: recevoir };
