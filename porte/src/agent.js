// L'objet d'un client : il démarre son conteneur, lui remet sa configuration et
// ses secrets, et lui transmet les webhooks. Un objet par client, dans la zone du
// client (juridiction UE ou États-Unis) ; son conteneur, contraint à la même zone.
//
// Les secrets propres au client (l'adresse de sa base) sont rangés dans le stockage
// de cet objet par la route d'administration, jamais relus vers l'extérieur.
// Ceux de MEGGA (clés des modèles, jeton et clé de l'app Meta) sont des secrets du Worker.
import { DurableObject } from "cloudflare:workers";
import { clientParId } from "./annuaire.js";

const PORT = 8080;
const INACTIVITE_MS = 15 * 60 * 1000; // le conteneur s'endort après 15 minutes sans message
// Après un message, la porte demande au conteneur s'il a un rappel à venir (le tour a pu en créer un).
const VERIFICATION_MS = 90 * 1000;

/** Le jeton des routes internes d'un client : HMAC du jeton d'administration et de son nom. */
export async function jetonInterne(admin, nom) {
  const enc = new TextEncoder();
  const k = await crypto.subtle.importKey("raw", enc.encode(admin), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = new Uint8Array(await crypto.subtle.sign("HMAC", k, enc.encode(`interne:${nom}`)));
  return [...sig].map((b) => b.toString(16).padStart(2, "0")).join("");
}
export const SECRETS_CLIENT = ["DATABASE_URL"];
const SECRETS_MEGGA = ["META_TOKEN", "META_APP_SECRET", "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY", "ELEVENLABS_API_KEY"];

class AgentClient extends DurableObject {
  constructor(ctx, env) {
    super(ctx, env);
    const c = ctx.container;
    if (c?.running) void ctx.blockConcurrencyWhile(() => c.setInactivityTimeout(INACTIVITE_MS));
  }

  /** Range les secrets du client ; ne rend que leurs noms. */
  async poserSecrets(secrets) {
    const gardes = {};
    for (const k of SECRETS_CLIENT) if (typeof secrets?.[k] === "string" && secrets[k]) gardes[k] = secrets[k];
    if (!Object.keys(gardes).length) throw new Error("aucun secret reconnu");
    const avant = (await this.ctx.storage.get("secrets")) ?? {};
    await this.ctx.storage.put("secrets", { ...avant, ...gardes });
    // Les nouveaux secrets s'appliquent au prochain démarrage du conteneur.
    if (this.ctx.container?.running) await this.ctx.container.destroy().catch(() => {});
    return Object.keys(gardes);
  }

  async fetch(requete) {
    await this.pret();
    const url = new URL(requete.url);
    url.protocol = "http:";
    url.host = "container";
    const transmise = new Request(url, requete);
    transmise.headers.delete("host");
    const reponse = await this.ctx.container.getTcpPort(PORT).fetch(transmise);
    if (url.pathname === "/whatsapp") await this.verifierBientot();
    return reponse;
  }

  pret() {
    this.demarrage ??= this.demarrer().finally(() => (this.demarrage = undefined));
    return this.demarrage;
  }

  /** Une vérification des rappels sous peu, sauf si une alarme plus proche est déjà posée. */
  async verifierBientot(maintenant = Date.now()) {
    const t = maintenant + VERIFICATION_MS;
    const a = await this.ctx.storage.getAlarm();
    if (!a || a > t) await this.ctx.storage.setAlarm(t);
  }

  /** L'heure d'un rappel (ou d'une vérification) : le conteneur envoie ce qui est échu. */
  async alarm() {
    await this.pret();
    const jeton = await jetonInterne(this.env.ADMIN_TOKEN ?? "", this.ctx.id.name ?? "");
    const r = await this.ctx.container.getTcpPort(PORT).fetch("http://container/interne/rappels", {
      method: "POST",
      headers: { "x-megga-interne": jeton },
    });
    if (!r.ok) throw new Error(`rappels ${r.status}`); // l'alarme est retentée par la plateforme
    const { prochain } = await r.json();
    if (prochain) await this.ctx.storage.setAlarm(Math.max(Math.round(prochain * 1000), Date.now() + 5000));
  }

  async demarrer() {
    const c = this.ctx.container;
    if (!c.running) {
      const nom = this.ctx.id.name;
      const client = await clientParId(this.env.ANNUAIRE, nom);
      if (!client) throw new Error("client inconnu ou inactif");
      const secrets = (await this.ctx.storage.get("secrets")) ?? {};
      for (const k of SECRETS_CLIENT) if (!secrets[k]) throw new Error(`secret du client manquant : ${k}`);
      const env = { CLIENT_CONFIG: client.config, ...secrets, INTERNE_TOKEN: await jetonInterne(this.env.ADMIN_TOKEN ?? "", nom) };
      for (const k of SECRETS_MEGGA) if (this.env[k]) env[k] = this.env[k];
      // Internet : Meta, les modèles et la base. Le resserrer hôte par hôte viendra avec les outils.
      c.start({ enableInternet: true, env });
    }
    await c.setInactivityTimeout(INACTIVITE_MS);
    const port = c.getTcpPort(PORT);
    let derniere;
    for (let i = 0; i < 100; i++) {
      try {
        const r = await port.fetch("http://container/sante", { signal: AbortSignal.timeout(1000) });
        await r.body?.cancel();
        if (r.ok) return;
        derniere = new Error(`santé ${r.status}`);
      } catch (e) {
        derniere = e;
      }
      await scheduler.wait(200);
    }
    throw new Error("le conteneur ne répond pas", { cause: derniere });
  }
}

// Une classe par zone : chacune a son application de conteneurs, contrainte à sa juridiction.
export class AgentEurope extends AgentClient {}
export class AgentEtatsUnis extends AgentClient {}
