// Après chaque essai : les bases qu'il a ouvertes se ferment (une base Postgres d'essai est supprimée).
import { afterEach } from "vitest";
import { fermerBasesOuvertes } from "./moteurs";

afterEach(fermerBasesOuvertes);
