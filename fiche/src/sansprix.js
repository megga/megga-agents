// La fiche « sans prix » : celle que Greg accorde à un partenaire (avec la
// version anonyme, c'est la fiche partenaire). Pas seulement le prix de la
// couverture : tout montant, où qu'il soit. Les lignes du tableau des
// détails qui parlent d'argent (prix au m², charges, impôt foncier, taxe des
// ordures, prix d'une place de parc) partent, et dans l'accroche et la
// description, chaque phrase qui porte un montant (« proposée à la vente à
// EUR 4 millions », « caution : EUR 1’000 »). Le reste ne bouge pas.

// Un montant : une devise près d'un nombre, « 4’500’000.- », « 1,3 million d'euros ».
const MONTANT = new RegExp(
  [
    String.raw`\b(?:CHF|EUR|AED|USD|GBP|Fr\.|SFr\.?)\s?\d`,
    String.raw`\d[\d’'., ]*\s?(?:CHF|EUR|AED|USD|GBP|€|\$|£)`,
    String.raw`\d[\d’'., ]*\s?(?:francs?|euros?|dirhams?|dollars?)\b`,
    String.raw`\d[\d’']*\.-`,
    String.raw`\bmillions?\s+(?:d[’']|de\s+)(?:euros|francs|dirhams|dollars)`,
    String.raw`\bmillions?\s+(?:of\s+)?(?:euros|francs|dirhams|dollars)\b`,
    String.raw`\d\s?(?:mio|mios|millions?)\b`,
  ].join("|"),
  "i"
);
const LIBELLE_ARGENT = /\b(?:prix|price|charges?|imp[oô]ts?|tax\w*|ibi|loyer|rent|fees?|frais|valeur|value|co[uû]ts?|cost)\b/i;

export const porteUnMontant = (t) => MONTANT.test(String(t ?? ""));

/** Les phrases d'un texte, sans celles qui portent un montant. */
export function sansMontants(texte) {
  const t = String(texte ?? "");
  if (!porteUnMontant(t)) return t;
  // Une phrase finit sur un point (ou ! ? …) suivi d'une espace : « 100’000.- » n'en finit pas une.
  return t.split(/(?<=[.!?…])\s+/).filter((p) => !porteUnMontant(p)).join(" ").trim();
}

/** La fiche sans aucun prix ni montant. */
export function ficheSansPrix(fiche) {
  const description = [];
  for (const b of fiche.description || []) {
    if (typeof b === "string") {
      const p = sansMontants(b);
      if (p) description.push(p);
    } else if (b[0] === "liste") {
      const items = b[1].map(sansMontants).filter(Boolean);
      if (items.length) description.push(["liste", items]);
    } else description.push(b);
  }
  // Un intertitre resté sans rien après lui part aussi.
  const propre = description.filter((b, i) => !(Array.isArray(b) && b[0] === "titre" && (i === description.length - 1 || (Array.isArray(description[i + 1]) && description[i + 1][0] === "titre"))));
  return {
    ...fiche,
    prix: "",
    accroche: sansMontants(fiche.accroche),
    description: propre,
    chiffres: (fiche.chiffres || []).filter((c) => !LIBELLE_ARGENT.test(c.libelle) && !porteUnMontant(c.valeur)),
    details: (fiche.details || []).filter(([l, v]) => !LIBELLE_ARGENT.test(l) && !porteUnMontant(v)),
  };
}
