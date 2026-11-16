// L'objet d'un client : il démarre son conteneur, lui remet sa configuration et
// ses secrets, et lui transmet les webhooks. Un objet par client, dans la zone du
// client (juridiction UE ou États-Unis) ; son conteneur, contraint à la même zone.
//
// Les secrets propres au client (l'adresse de sa base) sont rangés dans le stockage
// de cet objet par la route d'administration, jamais relus vers l'extérieur.
// Ceux de MEGGA (clés des modèles, jeton et clé de l'app Meta) sont des secrets du Worker.
//
// L'atelier (lot 5) tourne de la même façon : un objet, un conteneur de la même image.
import { DurableObject } from "cloudflare:workers";
import { clientParId } from "./annuaire.js";

const PORT = 8080;
const INACTIVITE_MS = 15 * 60 * 1000; // le conteneur s'endort après 15 minutes sans message
// Après un message, la porte demande au conteneur s'il a un rappel à venir (le tour a pu en créer un).
const VERIFICATION_MS = 90 * 1000;
// Avant un redémarrage, le conteneur a ce temps pour finir les tours en cours.
const VIDER_MS = 120 * 1000;
// Le suivi : une lecture récente est rendue telle quelle (en mémoire seulement, jamais rangée),
// et un conteneur réveillé seulement pour être lu se rendort vite.
const CACHE_SUIVI_MS = 5 * 60 * 1000;
const CACHE_CONVERSATIONS_MS = 60 * 1000;
const SOMMEIL_SUIVI_MS = 2 * 60 * 1000;
const ALERTES_MAX = 10;
// Une alarme en échec (base ou conteneur indisponible) se repose elle-même, de plus en plus tard, sans jamais
// s'arrêter : Cloudflare ne la retente que six fois, puis l'oublie (relecture du 16.11.2026, I8).
const REESSAIS_ALARME_MS = [60_000, 120_000, 300_000, 600_000, 900_000];
// Un webhook que le conteneur n'a pas reçu (démarrage en échec, panne) est gardé et rejoué, au plus ce nombre,
// pas plus vieux qu'un jour : Meta ne le renvoie pas, la porte lui a déjà répondu (I9).
const GARDES_MAX = 200;
const GARDE_MS = 24 * 3600 * 1000;
const REJOUER_MS = 60_000;

/** Le jeton des routes internes d'un client : HMAC du jeton d'administration et de son nom. */
export async function jetonInterne(admin, nom) {
  const enc = new TextEncoder();
  const k = await crypto.subtle.importKey("raw", enc.encode(admin), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = new Uint8Array(await crypto.subtle.sign("HMAC", k, enc.encode(`interne:${nom}`)));
  return [...sig].map((b) => b.toString(16).padStart(2, "0")).join("");
}
// Les secrets propres à un client, posés par la route d'administration : sa base (exigée), et pour un client
// qui a des rôles et une gestion de site (lot 7.1) ses gestionnaires et la clé de sa gestion, et celle de son site
// pour /site/… (lot 7.4).
export const SECRETS_CLIENT_REQUIS = ["DATABASE_URL"];
// LEADS_SECRET signe les leads envoyés au webhook du client ; MCP_JETON_n ouvre ses serveurs MCP (lot 9.4).
export const SECRETS_CLIENT = [...SECRETS_CLIENT_REQUIS, "GESTIONNAIRES", "GESTION_CLE", "SITE_CLE", "LEADS_SECRET",
  "MCP_JETON_1", "MCP_JETON_2", "MCP_JETON_3", "MCP_JETON_4", "MCP_JETON_5"];
const SECRETS_MEGGA = ["META_TOKEN", "META_APP_SECRET", "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY", "ELEVENLABS_API_KEY"];
// L'atelier n'a besoin que des modèles (mode d'essai) : il n'envoie rien sur WhatsApp.
const SECRETS_ATELIER = ["ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY"];
// Ceux qu'on pose dans l'objet de l'atelier : sa base, et la clé qui signe les ordres de pilotage.
const SECRETS_POSES_ATELIER = ["DATABASE_URL", "PILOTAGE_CLE"];

/** Un objet qui fait tourner un conteneur de l'image unique, et lui transmet les requêtes. */
class Conteneur extends DurableObject {
  constructor(ctx, env) {
    super(ctx, env);
    const c = ctx.container;
    if (c?.running) void ctx.blockConcurrencyWhile(() => c.setInactivityTimeout(INACTIVITE_MS));
  }

  /** Les secrets qu'on peut ranger dans cet objet. */
  secretsPermis() {
    return SECRETS_CLIENT;
  }

  /** Range les secrets propres à cet objet ; ne rend que leurs noms. */
  async poserSecrets(secrets) {
    const gardes = {};
    for (const k of this.secretsPermis()) if (typeof secrets?.[k] === "string" && secrets[k]) gardes[k] = secrets[k];
    if (!Object.keys(gardes).length) throw new Error("aucun secret reconnu");
    const avant = (await this.ctx.storage.get("secrets")) ?? {};
    await this.ctx.storage.put("secrets", { ...avant, ...gardes });
    // Les nouveaux secrets s'appliquent au prochain démarrage du conteneur.
    await this.redemarrer();
    return Object.keys(gardes);
  }

  /** Arrête le conteneur s'il tourne : le prochain appel le relance avec l'annuaire et les secrets du moment. */
  async redemarrer() {
    const c = this.ctx.container;
    if (!c?.running) return false;
    await c.destroy().catch(() => {});
    return true;
  }

  /** L'état du conteneur et ses dernières pannes, sans rien de privé. */
  async etat() {
    return { demarre: Boolean(this.ctx.container?.running), alertes: (await this.ctx.storage.get("alertes")) ?? [] };
  }

  /** Garde une panne (démarrage, transmission, rappels) pour le suivi : l'heure et un message technique. */
  async noterAlerte(quoi, e) {
    const message = String(e?.message ?? e).slice(0, 200);
    const alertes = (await this.ctx.storage.get("alertes").catch(() => null)) ?? [];
    alertes.push({ quand: Date.now(), quoi, message, resolue: null });
    await this.ctx.storage.put("alertes", alertes.slice(-ALERTES_MAX)).catch(() => {});
  }

  /** Le conteneur répond de nouveau : les pannes en cours sont marquées résolues, avec l'heure. */
  async resoudreAlertes() {
    const alertes = (await this.ctx.storage.get("alertes")) ?? [];
    if (!alertes.some((a) => !a.resolue)) return;
    const maintenant = Date.now();
    await this.ctx.storage.put("alertes", alertes.map((a) => (a.resolue ? a : { ...a, resolue: maintenant })));
  }

  async fetch(requete) {
    const url = new URL(requete.url);
    this.activite = Date.now(); // une vraie requête (message, rappel) : le conteneur doit rester éveillé
    try {
      await this.pret();
      url.protocol = "http:";
      url.host = "container";
      const transmise = new Request(url, requete);
      transmise.headers.delete("host");
      const reponse = await this.ctx.container.getTcpPort(PORT).fetch(transmise);
      await this.apres(url.pathname);
      return reponse;
    } catch (e) {
      await this.noterAlerte("transmission", e);
      throw e;
    }
  }

  async apres() {}

  pret() {
    this.demarrage ??= this.demarrer().finally(() => (this.demarrage = undefined));
    return this.demarrage;
  }

  async demarrer() {
    const c = this.ctx.container;
    if (!c.running) {
      const env = await this.environnement();
      // Le commit déployé (wrangler deploy --tag), quand l'image construite par Cloudflare ne le connaît pas.
      const revision = this.env.VERSION_PORTE?.tag;
      if (revision) env.MEGGA_REVISION = revision;
      c.start({ enableInternet: true, env });
    }
    await c.setInactivityTimeout(INACTIVITE_MS);
    const port = c.getTcpPort(PORT);
    let derniere;
    for (let i = 0; i < 100; i++) {
      try {
        const r = await port.fetch("http://container/sante", { signal: AbortSignal.timeout(1000) });
        await r.body?.cancel();
        if (r.ok) {
          await this.resoudreAlertes().catch(() => {});
          return;
        }
        derniere = new Error(`santé ${r.status}`);
      } catch (e) {
        derniere = e;
      }
      await scheduler.wait(200);
    }
    throw new Error("le conteneur ne répond pas", { cause: derniere });
  }
}

class AgentClient extends Conteneur {
  /**
   * Le jeton des routes internes de ce client. Sans ADMIN_TOKEN, il ne se calculerait qu'à partir du nom du client,
   * que tout le monde connaît : refusé (relecture du 16.11.2026).
   */
  async jeton() {
    if (!this.env.ADMIN_TOKEN) throw new Error("ADMIN_TOKEN manquant : pas de jeton interne");
    return jetonInterne(this.env.ADMIN_TOKEN, this.ctx.id.name ?? "");
  }

  /** Un webhook de Meta : s'il n'arrive pas au conteneur, il est gardé pour être rejoué, rien ne se perd. */
  async fetch(requete) {
    if (new URL(requete.url).pathname !== "/whatsapp" || requete.method !== "POST") return super.fetch(requete);
    const corps = await requete.text();
    const signature = requete.headers.get("x-hub-signature-256") ?? "";
    try {
      return await super.fetch(new Request(requete.url, { method: "POST", body: corps, headers: requete.headers }));
    } catch (e) {
      await this.garderWebhook(corps, signature);
      throw e;
    }
  }

  async garderWebhook(corps, signature) {
    const gardes = (await this.ctx.storage.get("webhooks").catch(() => null)) ?? [];
    gardes.push({ quand: Date.now(), corps, signature });
    await this.ctx.storage.put("webhooks", gardes.slice(-GARDES_MAX));
    const t = Date.now() + REJOUER_MS;
    const a = await this.ctx.storage.getAlarm();
    if (!a || a > t) await this.ctx.storage.setAlarm(t);
  }

  /** Les webhooks gardés, rejoués au conteneur qui répond de nouveau (marqués : il les lit même plus vieux que 15 minutes). */
  async rejouerWebhooks(jeton) {
    const gardes = (await this.ctx.storage.get("webhooks")) ?? [];
    if (!gardes.length) return;
    const restants = [];
    for (const w of gardes) {
      if (Date.now() - w.quand > GARDE_MS) continue;
      try {
        const r = await this.ctx.container.getTcpPort(PORT).fetch("http://container/whatsapp", {
          method: "POST",
          body: w.corps,
          headers: { "x-hub-signature-256": w.signature, "content-type": "application/json", "x-megga-interne": jeton, "x-megga-rejoue": "1" },
        });
        await r.body?.cancel();
        if (!r.ok) restants.push(w);
      } catch {
        restants.push(w);
      }
    }
    if (restants.length) await this.ctx.storage.put("webhooks", restants);
    else await this.ctx.storage.delete("webhooks");
    if (restants.length) throw new Error(`${restants.length} webhook(s) gardé(s) pas encore rejoué(s)`);
  }

  async apres(chemin) {
    if (chemin === "/whatsapp") await this.verifierBientot();
  }

  /** Une vérification des rappels sous peu, sauf si une alarme plus proche est déjà posée. */
  async verifierBientot(maintenant = Date.now()) {
    const t = maintenant + VERIFICATION_MS;
    const a = await this.ctx.storage.getAlarm();
    if (!a || a > t) await this.ctx.storage.setAlarm(t);
  }

  /**
   * Un redémarrage en douceur : il se fait à l'alarme, qui laisse le conteneur finir ses
   * tours en cours (réponse en route, messages en regroupement) avant de l'arrêter.
   * Rend vrai si un conteneur tournait.
   */
  async redemarrer() {
    if (!this.ctx.container?.running) return false;
    await this.ctx.storage.put("a_redemarrer", true);
    await this.ctx.storage.setAlarm(Date.now());
    return true;
  }

  /** Le suivi du conteneur (volumes, conversations, alertes), lu par l'atelier à travers la porte. */
  async suivre(chemin, recherche = "") {
    if (!/^(\/conversations(\/(\+?\d{6,20}|api:[a-z0-9][a-z0-9-]{0,19}:[A-Za-z0-9._-]{1,40}))?|\/alertes|\/audit|\/approbations|\/reprises|\/leads)?$/.test(chemin)) throw new Error("chemin de suivi");
    const cle = chemin + recherche;
    // Les conversations, le journal d'audit et les demandes d'accord changent vite : gardés une minute seulement.
    const duree = /^\/(conversations|audit|approbations|reprises|leads)/.test(chemin) ? CACHE_CONVERSATIONS_MS : CACHE_SUIVI_MS;
    this.cacheSuivi ??= new Map();
    const garde = this.cacheSuivi.get(cle);
    if (garde && Date.now() - garde.quand < duree) return { statut: 200, donnees: garde.donnees };
    const debut = Date.now();
    const dormait = !this.ctx.container?.running;
    try {
      await this.pret();
    } catch (e) {
      await this.noterAlerte("demarrage", e);
      throw e;
    }
    const jeton = await this.jeton();
    const r = await this.ctx.container
      .getTcpPort(PORT)
      .fetch(`http://container/interne/suivi${chemin.replace(/:/g, "%3A")}${recherche}`, { headers: { "x-megga-interne": jeton } });
    const texte = await r.text();
    let donnees = null;
    try {
      donnees = JSON.parse(texte);
    } catch {
      donnees = { erreur: texte.slice(0, 200) };
    }
    if (r.status === 200) {
      for (const [k, v] of this.cacheSuivi) if (Date.now() - v.quand >= CACHE_SUIVI_MS) this.cacheSuivi.delete(k);
      this.cacheSuivi.set(cle, { quand: Date.now(), donnees });
    }
    // Réveillé seulement pour être lu : il se rendort vite, sauf si une vraie requête est arrivée entre-temps.
    if (dormait && !((this.activite ?? 0) >= debut)) await this.ctx.container.setInactivityTimeout(SOMMEIL_SUIVI_MS).catch(() => {});
    return { statut: r.status, donnees };
  }

  /** Une décision de la console sur une demande d'accord (noyau/approbations.py) : l'action accordée est faite par le conteneur. */
  async decider(n, accord) {
    if (!/^\d{1,10}$/.test(String(n)) || typeof accord !== "boolean") throw new Error("demande");
    try {
      await this.pret();
    } catch (e) {
      await this.noterAlerte("demarrage", e);
      throw e;
    }
    const jeton = await jetonInterne(this.env.ADMIN_TOKEN ?? "", this.ctx.id.name ?? "");
    const r = await this.ctx.container.getTcpPort(PORT).fetch(`http://container/interne/approbations/${n}`, {
      method: "POST",
      headers: { "x-megga-interne": jeton, "content-type": "application/json" },
      body: JSON.stringify({ accord }),
    });
    const texte = await r.text();
    let donnees;
    try {
      donnees = JSON.parse(texte);
    } catch {
      donnees = { erreur: texte.slice(0, 200) };
    }
    this.cacheSuivi?.clear(); // la liste des demandes a changé
    return { statut: r.status, donnees };
  }

  /** Ce que la console fait d'une conversation confiée à l'équipe (lot 9.3) : {action, texte?}, transmis au conteneur. */
  async reprise(n, corps) {
    if (!/^\d{1,10}$/.test(String(n))) throw new Error("conversation");
    try {
      await this.pret();
    } catch (e) {
      await this.noterAlerte("demarrage", e);
      throw e;
    }
    const jeton = await jetonInterne(this.env.ADMIN_TOKEN ?? "", this.ctx.id.name ?? "");
    const r = await this.ctx.container.getTcpPort(PORT).fetch(`http://container/interne/reprises/${n}`, {
      method: "POST",
      headers: { "x-megga-interne": jeton, "content-type": "application/json" },
      body: JSON.stringify({ action: corps.action, texte: corps.texte ?? "" }),
    });
    const texte = await r.text();
    let donnees;
    try {
      donnees = JSON.parse(texte);
    } catch {
      donnees = { erreur: texte.slice(0, 200) };
    }
    this.cacheSuivi?.clear(); // la liste des conversations transmises a changé
    return { statut: r.status, donnees };
  }

  /** La base de connaissances du conteneur (lot 9.2) : lister, ajouter un document (le corps tel quel), en retirer un. */
  async connaissances(methode, chemin = "", corps = null) {
    if (!/^(\/\d{1,10})?$/.test(chemin)) throw new Error("chemin de document");
    try {
      await this.pret();
    } catch (e) {
      await this.noterAlerte("demarrage", e);
      throw e;
    }
    this.activite = Date.now(); // un document se calcule : le conteneur reste éveillé le temps qu'il faut
    const jeton = await jetonInterne(this.env.ADMIN_TOKEN ?? "", this.ctx.id.name ?? "");
    const options = { method: methode, headers: { "x-megga-interne": jeton } };
    if (corps !== null) {
      options.body = corps;
      options.headers["content-type"] = "application/json";
    }
    const r = await this.ctx.container.getTcpPort(PORT).fetch(`http://container/interne/connaissances${chemin}`, options);
    const texte = await r.text();
    let donnees;
    try {
      donnees = JSON.parse(texte);
    } catch {
      donnees = { erreur: texte.slice(0, 200) };
    }
    return { statut: r.status, donnees };
  }

  /** Les clés des logiciels (entrée par API), gardées en empreinte par le conteneur : lister, ajouter, retirer. */
  async cles(methode, chemin = "", corps = null) {
    if (!/^(\/[0-9a-f]{12})?$/.test(chemin)) throw new Error("chemin de clé");
    const dormait = !this.ctx.container?.running;
    try {
      await this.pret();
    } catch (e) {
      await this.noterAlerte("demarrage", e);
      throw e;
    }
    const jeton = await this.jeton();
    const options = { method: methode, headers: { "x-megga-interne": jeton } };
    if (corps !== null) {
      options.body = JSON.stringify(corps);
      options.headers["content-type"] = "application/json";
    }
    const r = await this.ctx.container.getTcpPort(PORT).fetch(`http://container/interne/cles${chemin}`, options);
    const texte = await r.text();
    let donnees;
    try {
      donnees = JSON.parse(texte);
    } catch {
      donnees = { erreur: texte.slice(0, 200) };
    }
    if (dormait) await this.ctx.container.setInactivityTimeout(SOMMEIL_SUIVI_MS).catch(() => {});
    return { statut: r.status, donnees };
  }

  /**
   * L'heure d'un rappel (ou d'une vérification, d'un redémarrage, d'un webhook à rejouer) : le conteneur envoie ce qui
   * est échu. En échec, l'alarme se repose elle-même, une minute plus tard, puis de plus en plus tard (15 minutes au
   * plus), tant qu'il le faut : rien ne s'arrête après une panne de quelques minutes.
   */
  async alarm() {
    this.activite = Date.now();
    try {
      await this.traiterAlarme();
      await this.ctx.storage.delete("echecs_alarme");
    } catch (e) {
      await this.noterAlerte("rappels", e);
      const n = ((await this.ctx.storage.get("echecs_alarme").catch(() => 0)) ?? 0) + 1;
      await this.ctx.storage.put("echecs_alarme", n).catch(() => {});
      const t = Date.now() + REESSAIS_ALARME_MS[Math.min(n, REESSAIS_ALARME_MS.length) - 1];
      const a = await this.ctx.storage.getAlarm().catch(() => null);
      if (!a || a <= Date.now() || a > t) await this.ctx.storage.setAlarm(t).catch(() => {});
    }
  }

  async traiterAlarme() {
    const jeton = await this.jeton();
    if (await this.ctx.storage.get("a_redemarrer")) {
      const c = this.ctx.container;
      if (c?.running) {
        await c
          .getTcpPort(PORT)
          .fetch("http://container/interne/vider", { method: "POST", headers: { "x-megga-interne": jeton }, signal: AbortSignal.timeout(VIDER_MS) })
          .then((r) => r.body?.cancel())
          .catch(() => {}); // un conteneur qui ne répond plus s'arrête quand même
        await c.destroy().catch(() => {});
      }
      await this.ctx.storage.delete("a_redemarrer");
    }
    // Relance (avec la nouvelle configuration s'il y a lieu), webhooks gardés, et rappels échus.
    await this.pret();
    let rejeu = null;
    try {
      await this.rejouerWebhooks(jeton);
    } catch (e) {
      rejeu = e; // les rappels passent quand même ; l'alarme se reposera
    }
    const r = await this.ctx.container.getTcpPort(PORT).fetch("http://container/interne/rappels", {
      method: "POST",
      headers: { "x-megga-interne": jeton },
    });
    if (!r.ok) throw new Error(`rappels ${r.status}`); // l'alarme est retentée par la plateforme
    const { prochain } = await r.json();
    if (prochain) await this.ctx.storage.setAlarm(Math.max(Math.round(prochain * 1000), Date.now() + 5000));
    if (rejeu) throw rejeu;
  }

  /** L'environnement du conteneur : la configuration de l'annuaire, ses secrets et ceux de MEGGA. */
  async environnement() {
    const nom = this.ctx.id.name;
    const client = await clientParId(this.env.ANNUAIRE, nom);
    if (!client) throw new Error("client inconnu ou inactif");
    const secrets = (await this.ctx.storage.get("secrets")) ?? {};
    for (const k of SECRETS_CLIENT_REQUIS) if (!secrets[k]) throw new Error(`secret du client manquant : ${k}`);
    const env = { CLIENT_CONFIG: client.config, ...secrets, INTERNE_TOKEN: await this.jeton() };
    for (const k of SECRETS_MEGGA) if (this.env[k]) env[k] = this.env[k];
    // Internet : Meta, les modèles et la base. Le resserrer hôte par hôte viendra avec les outils.
    return env;
  }
}

// Une classe par zone : chacune a son application de conteneurs, contrainte à sa juridiction.
export class AgentEurope extends AgentClient {}
export class AgentEtatsUnis extends AgentClient {}

/**
 * L'atelier de MEGGA (un seul, en zone Europe) : la même image, en service « atelier ».
 * Sa base (versions des configurations, jetons des clients) se pose comme celle d'un client,
 * de même que la clé de pilotage, qui signe les ordres des installations hors Cloudflare.
 * Il reçoit aussi les relevés de leurs pilotes (/pilotage/…), chaque minute : piloter une
 * installation le garde éveillé.
 */
export class Atelier extends Conteneur {
  /** L'atelier ne s'arrête qu'entre deux requêtes : une mise en service ou un essai en cours va au bout. */
  async fetch(requete) {
    this.enCours = (this.enCours ?? 0) + 1;
    try {
      const r = await super.fetch(requete);
      // Lue en entier avant de rendre la main : un redémarrage ne coupe pas une réponse en route.
      return new Response(await r.arrayBuffer(), r);
    } finally {
      this.enCours -= 1;
      if (this.enCours === 0 && this.aRedemarrer) {
        this.aRedemarrer = false;
        await this.ctx.container?.destroy().catch(() => {});
      }
    }
  }

  secretsPermis() {
    return SECRETS_POSES_ATELIER;
  }

  async redemarrer() {
    if (!this.ctx.container?.running) return false;
    if (this.enCours) {
      this.aRedemarrer = true; // à la fin de la dernière requête en cours
      return true;
    }
    return super.redemarrer();
  }

  async environnement() {
    const secrets = (await this.ctx.storage.get("secrets")) ?? {};
    if (!secrets.DATABASE_URL) throw new Error("secret de l'atelier manquant : DATABASE_URL");
    if (!this.env.ADMIN_TOKEN || !this.env.PORTE_URL) throw new Error("ADMIN_TOKEN et PORTE_URL attendus");
    const env = { MEGGA_SERVICE: "atelier", DATABASE_URL: secrets.DATABASE_URL, ADMIN_TOKEN: this.env.ADMIN_TOKEN, PORTE_URL: this.env.PORTE_URL };
    // Sans elle, l'atelier sert tout, sauf les ordres de pilotage (scripts/pilotage.py poser).
    if (secrets.PILOTAGE_CLE) env.PILOTAGE_CLE = secrets.PILOTAGE_CLE;
    for (const k of SECRETS_ATELIER) if (this.env[k]) env[k] = this.env[k];
    return env;
  }
}
