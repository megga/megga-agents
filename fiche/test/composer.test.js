// Le service de fiche : une demande JSON en entrée, un PDF en sortie.
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { test } from "node:test";

// Une photo JPEG de 1 × 1 pixel.
const JPEG = "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAMCAgICAgMCAgIDAwMDBAYEBAQEBAgGBgUGCQgKCgkICQkKDA8MCgsOCwkJDRENDg8QEBEQCgwSExIQEw8QEBD/yQALCAABAAEBAREA/8wABgAQEAX/2gAIAQEAAD8A0s8g/9k=";
const FICHE = {
  langue: "fr", titre: "Villa contemporaine avec vue sur le lac", adresse: "1223 Cologny", confidentiel: null, prix: "CHF 9’500’000",
  accroche: "Face au lac, une villa lumineuse.", description: ["Une villa.", ["liste", ["Piscine", "Jardin"]]],
  chiffres: [{ libelle: "Chambres", valeur: "5" }, { libelle: "Surface habitable", valeur: "420 m²" }],
  details: [["Étage", "Rez"]], equipements: ["Piscine"], reference: null, photos: [],
  contact: { nom: "Agent", fonction: "Courtier", email: "agent@exemple.ch", telephone: "+41 22 000 00 00", site: "exemple.ch" },
};

const composer = (demande) => spawnSync("node", [new URL("../src/composer.mjs", import.meta.url).pathname], { input: JSON.stringify(demande) });

test("une fiche de marque, puis anonyme et sans prix", () => {
  const marque = composer({ modele: "four-seasons-properties", fiche: FICHE, photos: [JPEG, JPEG], version: "marque", marque: "Agence Exemple" });
  assert.equal(marque.status, 0, String(marque.stderr));
  assert.equal(marque.stdout.subarray(0, 5).toString(), "%PDF-");
  assert.ok(marque.stdout.includes(Buffer.from("Agence Exemple")) || marque.stdout.length > 10000);
  const anonyme = composer({ modele: "four-seasons-properties", fiche: { ...FICHE, contact: null }, photos: [JPEG], version: "anonyme", sans_prix: true, marque: "Agence Exemple" });
  assert.equal(anonyme.status, 0, String(anonyme.stderr));
  assert.ok(!anonyme.stdout.includes(Buffer.from("Agence Exemple")));
});

test("un modèle inconnu ou mal nommé est refusé", () => {
  for (const modele of ["inconnu", "../src", ""]) {
    const r = composer({ modele, fiche: FICHE, photos: [] });
    assert.equal(r.status, 1);
    assert.equal(r.stdout.length, 0);
  }
});
