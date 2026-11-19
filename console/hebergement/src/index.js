// Le Worker megga-console : il porte la console MEGGA (console/Dockerfile) dans un seul conteneur, en juridiction UE,
// derrière console.megga.ai. Il transmet tout au conteneur, et fait trois choses de plus :
//  - il attend que la console réponde sur /api/sante avant de transmettre (le premier visiteur après la veille attend) ;
//  - il écrit x-forwarded-for avec l'adresse que Cloudflare a vue (cf-connecting-ip), en écrasant ce que le client a
//    envoyé : Better Auth compte alors les connexions par visiteur, et personne ne choisit son adresse ;
//  - si le conteneur ne démarre pas, il répond une page d'attente en français (503), jamais une erreur brute.
// Sur le modèle de Conteneur dans porte/src/agent.js, sans rien partager avec la porte.
import { DurableObject } from "cloudflare:workers";

const PORT = 3000;
const INACTIVITE_MS = 15 * 60 * 1000; // le conteneur s'endort après 15 minutes sans visite
const DEMARRAGE_MS = 60 * 1000; // le temps laissé à la console pour répondre sur /api/sante
const NOM = "console"; // un seul objet, donc un seul conteneur

// Les secrets du Worker remis au conteneur (secrets.sh). Sans les deux premiers, la console ne démarre pas : sans
// CONSOLE_BASE_URL, elle écrirait dans un fichier SQLite du conteneur, perdu à la veille.
const SECRETS_REQUIS = ["BETTER_AUTH_SECRET", "CONSOLE_BASE_URL"];
const SECRETS_FACULTATIFS = ["ATELIER_JETON"];
const VARIABLES = ["BETTER_AUTH_URL", "ATELIER_URL"];

export const PAGE_ATTENTE = `<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="10">
<title>MEGGA</title>
<style>
  /* Les couleurs de la console (console/src/app/globals.css : --side, --bg, --ink, --muted ; sombre : « Nuit douce »). */
  body { margin: 0; min-height: 100vh; display: grid; place-items: center; background: #f7f7fc; color: #1b1b2f;
    font: 16px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
  main { max-width: 360px; padding: 32px 28px; margin: 16px; border-radius: 28px; background: #ffffff; text-align: center; }
  h1 { margin: 0 0 8px; font-size: 22px; }
  p { margin: 0; color: #6a6a85; }
  @media (prefers-color-scheme: dark) {
    body { background: #15171c; color: #f2f3f5; }
    main { background: #0f1014; }
    p { color: #9aa0ab; }
  }
</style>
</head>
<body>
<main>
<h1>La console se réveille</h1>
<p>Elle sera prête dans un instant. Cette page se recharge toute seule.</p>
</main>
</body>
</html>
`;

/** La page d'attente : 503, en français, rien de technique ; le navigateur réessaie dans 10 secondes. */
export function pageAttente() {
  return new Response(PAGE_ATTENTE, {
    status: 503,
    headers: { "content-type": "text/html; charset=utf-8", "retry-after": "10", "cache-control": "no-store" },
  });
}

/** Ce que le conteneur reçoit : les variables du wrangler.jsonc, le mode invitation, la révision, les secrets posés. */
export function environnement(env) {
  const manquants = SECRETS_REQUIS.filter((k) => !env[k]);
  if (manquants.length) throw new Error(`secrets manquants : ${manquants.join(", ")}`); // les noms seulement
  const e = { CONSOLE_INSCRIPTION: "invitation" };
  for (const k of [...VARIABLES, ...SECRETS_REQUIS, ...SECRETS_FACULTATIFS]) if (env[k]) e[k] = env[k];
  // Le commit déployé (wrangler deploy --tag) : l'image construite par Cloudflare ne le connaît pas.
  if (env.VERSION?.tag) e.CONSOLE_REVISION = env.VERSION.tag;
  return e;
}

/** La requête telle que la console la reçoit : vers le conteneur, x-forwarded-for écrit par Cloudflare seulement. */
export function versConsole(requete) {
  const origine = new URL(requete.url);
  const url = new URL(requete.url);
  url.protocol = "http:";
  url.host = "container";
  const transmise = new Request(url, requete);
  transmise.headers.delete("host");
  const ip = requete.headers.get("cf-connecting-ip");
  if (ip) transmise.headers.set("x-forwarded-for", ip);
  else transmise.headers.delete("x-forwarded-for"); // jamais celle du client
  transmise.headers.set("x-forwarded-host", origine.host);
  transmise.headers.set("x-forwarded-proto", origine.protocol.replace(/:$/, ""));
  return transmise;
}

const attendre = (ms) => new Promise((r) => setTimeout(r, ms));

/** L'objet qui fait tourner le conteneur de la console et lui transmet les requêtes. */
export class ConsoleConteneur extends DurableObject {
  /** Le temps laissé à la console pour répondre au démarrage (les essais le raccourcissent). */
  attenteMs = DEMARRAGE_MS;

  constructor(ctx, env) {
    super(ctx, env);
    const c = ctx.container;
    if (c?.running) void ctx.blockConcurrencyWhile(() => c.setInactivityTimeout(INACTIVITE_MS));
  }

  async fetch(requete) {
    try {
      await this.pret();
    } catch (e) {
      console.error("la console ne démarre pas :", String(e?.message ?? e).slice(0, 200));
      return pageAttente();
    }
    try {
      return await this.ctx.container.getTcpPort(PORT).fetch(versConsole(requete));
    } catch (e) {
      this.repond = false; // la prochaine requête revérifie la console avant de lui transmettre
      console.error("la console ne répond pas :", String(e?.message ?? e).slice(0, 200));
      return pageAttente();
    }
  }

  /**
   * La console est vérifiée (/api/sante) au réveil seulement : tant que le conteneur tourne et qu'il a répondu une fois,
   * les requêtes lui vont directement, sans un aller-retour de plus chacune.
   */
  pret() {
    // Le délai d'inactivité est rafraîchi à chaque requête, comme avant : c'est un appel local, sans aller-retour au conteneur.
    if (this.repond && this.ctx.container?.running) return this.ctx.container.setInactivityTimeout(INACTIVITE_MS);
    this.demarrage ??= this.demarrer()
      .then(() => {
        this.repond = true;
      })
      .finally(() => (this.demarrage = undefined));
    return this.demarrage;
  }

  async demarrer() {
    const c = this.ctx.container;
    if (!c.running) c.start({ enableInternet: true, env: environnement(this.env) });
    await c.setInactivityTimeout(INACTIVITE_MS);
    const port = c.getTcpPort(PORT);
    let derniere;
    for (const fin = Date.now() + this.attenteMs; Date.now() < fin; ) {
      try {
        const r = await port.fetch("http://container/api/sante", { signal: AbortSignal.timeout(1000) });
        await r.body?.cancel();
        if (r.ok) return;
        derniere = new Error(`santé ${r.status}`);
      } catch (e) {
        derniere = e;
      }
      await attendre(200);
    }
    throw new Error("le conteneur ne répond pas", { cause: derniere });
  }
}

/**
 * Les fichiers de construction de Next (/_next/static/…) : leur nom change à chaque construction et la console les sert
 * « immutable ». Gardés au bord de Cloudflare, ils ne traversent le conteneur qu'une fois par construction.
 */
export function estStatique(requete) {
  return requete.method === "GET" && new URL(requete.url).pathname.startsWith("/_next/static/");
}

async function versObjet(requete, env) {
  try {
    return await env.CONSOLE.jurisdiction("eu").getByName(NOM).fetch(requete);
  } catch (e) {
    console.error("objet de la console injoignable :", String(e?.message ?? e).slice(0, 200));
    return pageAttente();
  }
}

const worker = {
  /** Tout part au conteneur unique de la console, en juridiction UE ; les fichiers de construction, depuis le cache. */
  async fetch(requete, env, ctx) {
    const cache = globalThis.caches?.default;
    if (!cache || !estStatique(requete)) return versObjet(requete, env);
    const garde = await cache.match(requete);
    if (garde) return garde;
    const r = await versObjet(requete, env);
    if (r.status === 200 && /immutable/.test(r.headers.get("cache-control") ?? "")) ctx?.waitUntil(cache.put(requete, r.clone()));
    return r;
  },
};

export default worker;
