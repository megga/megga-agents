-- L'annuaire des clients servis par Cloudflare. Pas de secret, pas de donnée de personne.
CREATE TABLE clients (
  id TEXT PRIMARY KEY,
  numero_id TEXT NOT NULL UNIQUE,
  zone TEXT NOT NULL CHECK (zone IN ('europe', 'etats-unis')),
  config TEXT NOT NULL,
  actif INTEGER NOT NULL DEFAULT 1,
  cree_le TEXT NOT NULL DEFAULT (datetime('now'))
);
