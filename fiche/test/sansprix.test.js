// La fiche « sans prix » (la fiche partenaire) : aucun montant, nulle part, et la commune seulement.
import assert from "node:assert/strict";
import { test } from "node:test";
import { commune, ficheSansPrix, porteUnMontant } from "../src/sansprix.js";

test("les montants courts et les grands nombres nus sont des montants ; une surface, non (relecture du 16.11.2026, I5)", () => {
  for (const t of ["4.5 M CHF", "4,5 M€", "2.9M", "4’500’000", "12k par mois", "EUR 4 millions", "CHF 9’500’000.-"]) assert.ok(porteUnMontant(t), t);
  for (const t of ["Surface 420 m²", "Terrain 3’000 m²", "5 chambres", "Construite en 2019", "Vue à 180°", "Lot 12, 1er étage"]) assert.ok(!porteUnMontant(t), t);
});

test("le titre, les équipements, la mention et l'adresse d'une fiche sans prix", () => {
  const f = ficheSansPrix({
    titre: "Villa à Cologny, 9.5 M CHF", adresse: "Chemin du Lac 12, 1223 Cologny", confidentiel: "Off-market, 12 M",
    equipements: ["Piscine", "Charges 2k par mois"], accroche: "Face au lac. Proposée à 4’500’000.", description: [], chiffres: [], details: [], prix: "CHF 9’500’000",
  });
  assert.equal(f.titre, "Villa à Cologny");
  assert.equal(f.adresse, "Cologny");
  assert.equal(f.confidentiel, null);
  assert.deepEqual(f.equipements, ["Piscine"]);
  assert.equal(f.accroche, "Face au lac.");
  assert.equal(f.prix, "");
  assert.equal(commune("Chemin du Lac 12"), "");
  assert.equal(commune("Marbella"), "Marbella");
});
