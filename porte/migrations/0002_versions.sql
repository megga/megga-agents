-- Lot 5 : la version de configuration en service (numéro de l'atelier) et l'heure du changement.
ALTER TABLE clients ADD COLUMN version INTEGER;
ALTER TABLE clients ADD COLUMN maj_le TEXT;
