// L'annuaire des clients (D1) : numéro WhatsApp vers client, zone, configuration.
// Rien de secret ici : les secrets d'un client sont dans le stockage de son objet.

const ID = /^[a-z0-9][a-z0-9-]{1,62}$/;
const NUMERO = /^\d{6,30}$/;

export async function clientParNumero(db, numeroId) {
  const l = await db.prepare("SELECT id, zone, config FROM clients WHERE numero_id = ? AND actif = 1").bind(numeroId).first();
  return l ? { id: l.id, zone: l.zone } : null;
}

export async function clientParId(db, id) {
  if (!ID.test(String(id))) return null;
  const l = await db.prepare("SELECT id, zone, config FROM clients WHERE id = ? AND actif = 1").bind(id).first();
  return l ? { id: l.id, zone: l.zone, config: l.config } : null;
}

export const idValide = (id) => ID.test(String(id ?? ""));

/** Tous les clients de l'annuaire et leur état, sans leur configuration. */
export async function lister(db) {
  const { results } = await db.prepare("SELECT id, numero_id, zone, actif, version, maj_le FROM clients ORDER BY id").all();
  return results ?? [];
}

export class RefusAnnuaire extends Error {
  constructor(statut, message) {
    super(message);
    this.statut = statut;
  }
}

/**
 * Inscrit (ou remplace) la configuration en service d'un client, venue de l'atelier.
 * La porte ne vérifie que ce qu'elle lit elle-même ; le reste a été validé par le noyau.
 */
export async function inscrire(db, id, { version, config } = {}) {
  if (!ID.test(String(id))) throw new RefusAnnuaire(400, "identifiant");
  if (!config || typeof config !== "object" || Array.isArray(config)) throw new RefusAnnuaire(400, "configuration : un objet");
  if (config.id !== id) throw new RefusAnnuaire(400, "configuration d'un autre client");
  if (!Number.isInteger(version) || version < 1) throw new RefusAnnuaire(400, "version");
  const numero = config.whatsapp?.numero_id;
  if (!NUMERO.test(String(numero ?? ""))) throw new RefusAnnuaire(400, "numéro WhatsApp");
  const avant = await db.prepare("SELECT zone FROM clients WHERE id = ?").bind(id).first();
  // L'objet d'un client vit dans la juridiction de sa zone : changer de zone, c'est le déménager.
  if (avant && avant.zone !== config.zone) throw new RefusAnnuaire(409, "changement de zone : déménagement, pas un réglage");
  const pris = await db.prepare("SELECT id FROM clients WHERE numero_id = ? AND id != ?").bind(numero, id).first();
  if (pris) throw new RefusAnnuaire(409, "numéro déjà servi par un autre client");
  await db
    .prepare(
      "INSERT INTO clients (id, numero_id, zone, config, actif, version, maj_le) VALUES (?, ?, ?, ?, 1, ?, datetime('now')) " +
        "ON CONFLICT(id) DO UPDATE SET numero_id = excluded.numero_id, zone = excluded.zone, config = excluded.config, " +
        "actif = 1, version = excluded.version, maj_le = excluded.maj_le",
    )
    .bind(id, numero, config.zone, JSON.stringify(config), version)
    .run();
}
