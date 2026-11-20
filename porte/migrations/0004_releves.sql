-- Le relevé chiffré de chaque agent (20.11.2026) : ses chiffres jour par jour (UTC), jamais un texte, un nom ni un numéro,
-- et son état au dernier relevé. La porte les écrit à l'alarme ; la console de MEGGA les lit tous d'un coup.
CREATE TABLE releves (
  client TEXT NOT NULL,
  jour TEXT NOT NULL,
  chiffres TEXT NOT NULL,
  maj_le INTEGER NOT NULL,
  PRIMARY KEY (client, jour)
);
CREATE TABLE etats (
  client TEXT PRIMARY KEY,
  etat TEXT NOT NULL,
  maj_le INTEGER NOT NULL
);
