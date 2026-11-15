// L'annuaire des clients (D1) : numéro WhatsApp vers client, zone, configuration.
// Rien de secret ici : les secrets d'un client sont dans le stockage de son objet.

const ID = /^[a-z0-9][a-z0-9-]{1,62}$/;

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
