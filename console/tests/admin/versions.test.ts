import { describe, expect, it } from "vitest";
import { differences, enTexte, lisible, numeroVersion } from "@/lib/admin/versions";
import { TA } from "@/lib/admin/textes";

// L'écart entre deux configurations et leur lecture à plat : des chemins pointés, une liste comparée entière.

describe("l'écart entre deux configurations", () => {
  it("donne les chemins pointés qui changent, triés ; une liste se compare entière", () => {
    expect(differences({ ton: "a", voix: { voix: "v1", s: 1 }, outils: ["x"] }, { ton: "b", voix: { voix: "v2", s: 1 }, outils: ["x", "y"] })).toEqual([
      { champ: "outils", avant: ["x"], apres: ["x", "y"] },
      { champ: "ton", avant: "a", apres: "b" },
      { champ: "voix.voix", avant: "v1", apres: "v2" },
    ]);
  });

  it("sans configuration d'avant, chaque champ ; un champ ajouté ou retiré a l'autre côté vide", () => {
    expect(differences(null, { ton: "b", voix: { voix: "v1" } })).toEqual([
      { champ: "ton", avant: undefined, apres: "b" },
      { champ: "voix.voix", avant: undefined, apres: "v1" },
    ]);
    expect(differences({ a: 1, b: { c: null } }, { a: 1, d: true })).toEqual([
      { champ: "b.c", avant: null, apres: undefined },
      { champ: "d", avant: undefined, apres: true },
    ]);
    expect(differences({ a: 1 }, { a: 1 })).toEqual([]);
  });

  it("un objet vide est une valeur ; une liste d'objets aussi", () => {
    expect(differences({ modeles_meta: { rappel: { nom: "r" } } }, { modeles_meta: {} })).toEqual([
      { champ: "modeles_meta", avant: undefined, apres: {} },
      { champ: "modeles_meta.rappel.nom", avant: "r", apres: undefined },
    ]);
    expect(differences({ r: [{ a: 1 }] }, { r: [{ a: 2 }] })).toEqual([{ champ: "r", avant: [{ a: 1 }], apres: [{ a: 2 }] }]);
  });
});

describe("une configuration lisible", () => {
  it("se met à plat avec les mêmes chemins, dans son ordre", () => {
    expect(lisible({ ton: "b", voix: { voix: "v2", s: 1 }, outils: ["x", "y"], whatsapp: null, reactions: true, modeles_meta: {} })).toEqual([
      { champ: "ton", valeur: "b" },
      { champ: "voix.voix", valeur: "v2" },
      { champ: "voix.s", valeur: "1" },
      { champ: "outils", valeur: '["x","y"]' },
      { champ: "whatsapp", valeur: "null" },
      { champ: "reactions", valeur: "true" },
      { champ: "modeles_meta", valeur: "{}" },
    ]);
  });

  it("une valeur absente s'écrit d'un tiret court", () => {
    expect([enTexte(undefined), enTexte("texte"), enTexte(0.5), enTexte([])]).toEqual([TA.inconnu, "texte", "0.5", "[]"]);
  });
});

describe("le numéro d'une version", () => {
  it("un entier positif écrit en chiffres, sinon rien", () => {
    expect([numeroVersion("2"), numeroVersion("17"), numeroVersion(3)]).toEqual([2, 17, 3]);
    for (const v of ["abc", "0", "-1", "1.5", "02", " 2", "2 ", "", "1e3", "99999999999", 0, -2, 1.5, true, null, undefined, [2]]) {
      expect(numeroVersion(v), String(v)).toBeNull();
    }
  });
});
