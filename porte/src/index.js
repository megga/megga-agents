// La porte des agents MEGGA : le seul point public des zones Europe et États-Unis.
//
//   GET  /meta                     l'abonnement du webhook de l'app Meta « Alix MEGGA »
//   POST /meta                     un webhook : signature vérifiée, puis transmis tel quel
//                                  au conteneur de chaque client concerné
//   POST /api/:client/messages     un logiciel parle à l'agent d'un client (clé du logiciel, vérifiée
//                                  par le conteneur) : transmis tel quel, réponse rendue telle quelle.
//                                  Adresse publique : https://api.megga.ai (API_HOTE), qui ne sert que
//                                  cette route ; workers.dev la sert aussi, en secours
//   POST /site/:client/(bien|demande)
//                                  le site d'un client (lot 7.4) : un bien entré en ligne, une demande d'information
//                                  d'une fiche ; transmis tel quel, la clé du site (SITE_CLE) vérifiée par le conteneur
//   GET|POST /admin/clients/:id/cles, DELETE /admin/clients/:id/cles/:cle
//                                  les clés des logiciels, gardées en empreinte par le conteneur (jeton ADMIN_TOKEN)
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
// L'entrée par API : une clé bien formée (noyau/api.py), un corps de 16 Kio au plus.
const CLE_API = /^Bearer mga_[A-Za-z0-9_-]{43}$/;
const FLUX = /\btext\/event-stream\b/;
const TAILLE_API = 16 * 1024;
const HOTE_API = "api.megga.ai";
// Le site d'un client (lot 7.4) : une clé d'au moins 32 caractères, un corps de 16 Kio au plus.
const CLE_SITE = /^Bearer [\x21-\x7e]{32,200}$/;
// L'atelier est unique, en zone Europe.
const atelierDe = (env) => env.ATELIER?.jurisdiction("eu").getByName("megga") ?? null;
// Le pilotage : l'heure d'une requête signée, à 5 minutes près, et un relevé de 256 Kio au plus.
const FENETRE_PILOTAGE_S = 300;
const TAILLE_PILOTAGE = 256 * 1024;

export async function recevoir(requete, env, ctx) {
  const url = new URL(requete.url);
  const api = url.pathname.match(/^\/api\/([^/]+)\/messages$/);
  // Sur l'hôte de l'API, rien d'autre : ni Meta, ni l'administration, ni l'atelier, ni le pilotage.
  if (url.hostname === (env.API_HOTE || HOTE_API)) return api ? messageApi(requete, env, api[1]) : json({ erreur: "introuvable" }, 404);
  if (url.pathname === "/" && requete.method === "GET") return texte("ok");
  if (url.pathname === "/meta" && requete.method === "GET") {
    const defi = defiAbonnement(requete.url, env.META_VERIFY_TOKEN);
    return defi === null ? texte("refusé", 403) : texte(defi);
  }
  if (url.pathname === "/meta" && requete.method === "POST") return webhook(requete, env, ctx);
  if (api) return messageApi(requete, env, api[1]);
  const site = url.pathname.match(/^\/site\/([^/]+)\/(bien|demande)$/);
  if (site) return messageSite(requete, env, site[1], site[2]);
  const cles = url.pathname.match(/^\/admin\/clients\/([^/]+)\/cles(\/[^/]+)?$/);
  if (cles) return clesApi(requete, env, cles[1], cles[2] ?? "");
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

/** Le pilote d'une installation : sans requête bien formée, récente et de taille bornée, rien ne réveille l'atelier. */
async function pilote(requete, env) {
  if (requete.method !== "POST") return texte("méthode", 405);
  if (!pilotageBienForme(requete.headers)) return texte("requête signée attendue", 401);
  // Une longueur annoncée, et bornée : sans elle (corps en flux), le relevé n'est pas transmis.
  const longueur = requete.headers.get("content-length") ?? "";
  if (!/^[0-9]{1,9}$/.test(longueur)) return texte("longueur attendue", 411);
  if (Number(longueur) > TAILLE_PILOTAGE) return texte("relevé trop gros", 413);
  const atelier = atelierDe(env);
  return atelier ? atelier.fetch(requete) : texte("atelier absent", 503);
}

/**
 * Un message d'un logiciel pour l'agent d'un client. La porte ne garde rien et ne journalise aucun texte :
 * elle vérifie la forme (clé, taille), puis transmet au conteneur, qui vérifie la clé et répond.
 */
/**
 * Le site d'un client : un bien entré en ligne, une demande d'information. La porte ne connaît pas la clé du site :
 * le conteneur la vérifie ; sans clé bien formée, rien ne réveille le conteneur.
 */
async function messageSite(requete, env, id, route) {
  if (requete.method !== "POST") return json({ erreur: "méthode : POST" }, 405);
  if (!CLE_SITE.test(requete.headers.get("authorization") ?? "")) return json({ erreur: "clé refusée" }, 401);
  const longueur = requete.headers.get("content-length") ?? "";
  if (!/^[0-9]{1,9}$/.test(longueur)) return json({ erreur: "longueur attendue" }, 411);
  if (Number(longueur) > TAILLE_API) return json({ erreur: "requête trop grosse" }, 413);
  const client = idValide(id) ? await clientParId(env.ANNUAIRE, id) : null;
  const agent = client && agentDe(env, client);
  if (!agent) return json({ erreur: "agent inconnu" }, 404);
  try {
    const r = await agent.fetch(
      new Request(`http://agent/site/${route}`, {
        method: "POST",
        body: await requete.arrayBuffer(),
        headers: { authorization: requete.headers.get("authorization"), "content-type": "application/json" },
      }),
    );
    return new Response(r.body, { status: r.status, headers: { "content-type": r.headers.get("content-type") ?? "application/json" } });
  } catch (e) {
    console.error("message du site en échec", id, String(e?.message ?? e).slice(0, 200));
    return json({ erreur: "agent injoignable" }, 503);
  }
}

async function messageApi(requete, env, id) {
  if (requete.method !== "POST") return json({ erreur: "méthode : POST" }, 405);
  // Sans clé bien formée, rien ne réveille le conteneur.
  if (!CLE_API.test(requete.headers.get("authorization") ?? "")) return json({ erreur: "clé refusée" }, 401);
  const longueur = requete.headers.get("content-length") ?? "";
  if (!/^[0-9]{1,9}$/.test(longueur)) return json({ erreur: "longueur attendue" }, 411);
  if (Number(longueur) > TAILLE_API) return json({ erreur: "requête trop grosse" }, 413);
  const client = idValide(id) ? await clientParId(env.ANNUAIRE, id) : null;
  const agent = client && agentDe(env, client);
  if (!agent) return json({ erreur: "agent inconnu" }, 404);
  const corps = await requete.arrayBuffer();
  try {
    const r = await agent.fetch(
      new Request("http://agent/api/messages", {
        method: "POST",
        body: corps,
        headers: {
          authorization: requete.headers.get("authorization"),
          "content-type": "application/json",
          // La réponse au fil de l'eau (docs/api.md) : de l'en-tête Accept, seul ce type passe.
          ...(FLUX.test(requete.headers.get("accept") ?? "") ? { accept: "text/event-stream" } : {}),
        },
      }),
    );
    // Seuls le statut, le type et l'attente passent : rien d'autre du conteneur ne sort. Le corps n'est pas lu
    // ici : un flux part au logiciel morceau par morceau.
    const entetes = { "content-type": r.headers.get("content-type") ?? "application/json" };
    const attente = r.headers.get("retry-after");
    if (attente) entetes["retry-after"] = attente;
    if (FLUX.test(entetes["content-type"])) entetes["cache-control"] = "no-store";
    return new Response(r.body, { status: r.status, headers: entetes });
  } catch (e) {
    console.error("message par API en échec", id, String(e?.message ?? e).slice(0, 200));
    return json({ erreur: "agent injoignable" }, 503);
  }
}

/** Les clés des logiciels d'un client : la porte transmet à son conteneur, qui les garde en empreinte. */
async function clesApi(requete, env, id, chemin) {
  if (!autorise(requete, env)) return texte("refusé", 401);
  const permis = chemin ? requete.method === "DELETE" : ["GET", "POST"].includes(requete.method);
  if (!permis) return texte("méthode", 405);
  if (chemin && !/^\/[0-9a-f]{12}$/.test(chemin)) return texte("identifiant de clé", 400);
  const client = await clientParId(env.ANNUAIRE, id);
  const agent = client && agentDe(env, client);
  if (!agent) return texte("client inconnu", 404);
  let corps = null;
  if (requete.method === "POST") {
    try {
      corps = await requete.json();
    } catch {
      return texte("corps", 400);
    }
  }
  try {
    const { statut, donnees } = await agent.cles(requete.method, chemin, corps);
    return json(donnees, statut);
  } catch (e) {
    console.error("clés en échec", id, String(e?.message ?? e).slice(0, 200));
    return json({ erreur: "conteneur injoignable" }, 503);
  }
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
