// Ce que la porte lit d'un webhook de Meta, sans rien garder : la signature,
// les numéros concernés, et l'abonnement du webhook. Aucun texte ni numéro de
// personne ne sort d'ici, pas même dans les journaux.

const encoder = (t) => new TextEncoder().encode(t);

// Meta signe le corps brut en HMAC-SHA256 avec la clé secrète de l'application :
// « X-Hub-Signature-256: sha256=<hex> ».
export async function signatureValide(corps, entete, secret) {
  const [algo, h] = String(entete ?? "").split("=");
  if (algo !== "sha256" || !/^[0-9a-f]{64}$/i.test(h ?? "") || !secret) return false;
  const k = await crypto.subtle.importKey("raw", encoder(secret), { name: "HMAC", hash: "SHA-256" }, false, ["verify"]);
  const octets = typeof corps === "string" ? encoder(corps) : new Uint8Array(corps);
  return crypto.subtle.verify("HMAC", k, Uint8Array.from(h.match(/../g), (x) => parseInt(x, 16)), octets);
}

/**
 * Les identifiants des numéros (phone_number_id) que touche ce webhook, seulement là où il y a quelque chose à
 * faire : un message reçu, ou un envoi que Meta a refusé après coup. Les simples accusés (envoyé, remis, lu)
 * ne réveillent pas le conteneur du client (relecture du 16.11.2026, I12).
 */
export function numerosDe(evenement) {
  const ids = new Set();
  if (evenement?.object !== "whatsapp_business_account") return [];
  for (const e of evenement.entry ?? []) {
    for (const c of e.changes ?? []) {
      const v = c?.value;
      const id = v?.metadata?.phone_number_id;
      const utile = (v?.messages ?? []).length > 0 || (v?.statuses ?? []).some((s) => s?.status === "failed");
      if (utile && typeof id === "string" && /^\d{6,30}$/.test(id)) ids.add(id);
    }
  }
  return [...ids];
}

/** L'abonnement du webhook (GET) : le défi à rendre si le jeton correspond, sinon null. */
export function defiAbonnement(url, jeton) {
  const p = new URL(url).searchParams;
  if (!jeton || p.get("hub.mode") !== "subscribe") return null;
  return egal(p.get("hub.verify_token") ?? "", jeton) ? p.get("hub.challenge") ?? "" : null;
}

/** Comparaison à temps constant de deux textes. */
export function egal(a, b) {
  const x = encoder(String(a));
  const y = encoder(String(b));
  let d = x.length ^ y.length;
  for (let i = 0; i < Math.max(x.length, y.length); i++) d |= (x[i] ?? 0) ^ (y[i] ?? 0);
  return d === 0;
}
