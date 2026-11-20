// Le fond de la carte du monde de la vue d'ensemble (src/lib/admin/carte-monde.json), produit une fois et versionné : la
// console n'emporte aucune bibliothèque de carte. Les frontières viennent de Natural Earth (domaine public) par world-atlas
// (ISC), projetées par d3-geo (ISC) ; les codes ISO à deux lettres par i18n-iso-countries (MIT). L'Antarctique est laissé.
//
//   npm i --no-save d3-geo@3.1.1 topojson-client@3.1.0 world-atlas@2.0.2 i18n-iso-countries@7.14.0
//   node scripts/carte-monde.cjs
//
// Il écrit aussi la liste des codes que l'atelier accepte (src/lib/admin/pays-codes.json, à recopier dans atelier/pays.py
// du moteur).
const fs = require("node:fs");
const path = require("node:path");
const { geoEqualEarth, geoPath } = require("d3-geo");
const { feature } = require("topojson-client");
const pays = require("i18n-iso-countries");
const monde = require("world-atlas/countries-110m.json");

const LARGEUR = 1000;
const formes = feature(monde, monde.objects.countries).features;
const projection = geoEqualEarth().fitWidth(LARGEUR, { type: "Sphere" });
const trace = geoPath(projection).digits(1);
const sortie = {};
for (const f of formes) {
  const code = f.id && pays.numericToAlpha2(f.id);
  if (!code || code === "AQ") continue;
  const d = trace(f);
  if (d) sortie[code] = (sortie[code] ?? "") + d;
}
const gardees = formes.filter((f) => f.id && pays.numericToAlpha2(f.id) && pays.numericToAlpha2(f.id) !== "AQ");
const [[x0, y0], [x1, y1]] = trace.bounds({ type: "FeatureCollection", features: gardees });
const codes = Object.keys(pays.getAlpha2Codes()).sort();
const fichier = path.join(__dirname, "..", "src", "lib", "admin", "carte-monde.json");
fs.writeFileSync(fichier, JSON.stringify({ vue: [x0, y0, x1 - x0, y1 - y0].map((n) => Math.round(n)).join(" "), pays: sortie }) + "\n");
fs.writeFileSync(path.join(path.dirname(fichier), "pays-codes.json"), JSON.stringify(codes) + "\n");
console.log(`${Object.keys(sortie).length} pays tracés, ${codes.length} codes, ${fs.statSync(fichier).size} octets`);
