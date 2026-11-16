-- Lot 6.6 : un client branché seulement par API n'a pas de numéro WhatsApp. SQLite ne retire pas
-- un NOT NULL : la table est refaite, à l'identique sinon. UNIQUE laisse passer plusieurs NULL.
CREATE TABLE clients_nouvelle (
  id TEXT PRIMARY KEY,
  numero_id TEXT UNIQUE,
  zone TEXT NOT NULL CHECK (zone IN ('europe', 'etats-unis')),
  config TEXT NOT NULL,
  actif INTEGER NOT NULL DEFAULT 1,
  cree_le TEXT NOT NULL DEFAULT (datetime('now')),
  version INTEGER,
  maj_le TEXT
);
INSERT INTO clients_nouvelle (id, numero_id, zone, config, actif, cree_le, version, maj_le)
  SELECT id, numero_id, zone, config, actif, cree_le, version, maj_le FROM clients;
DROP TABLE clients;
ALTER TABLE clients_nouvelle RENAME TO clients;
