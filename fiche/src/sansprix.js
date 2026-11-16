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
// Ce que le motif ci-dessus laissait passer (relecture du 16.11.2026, I5) : « 4.5 M CHF », « 4,5 M€ », « 2.9M »,
// « 12k par mois », et un grand nombre nu, « 4’500’000 » (un million au moins : une surface n'y arrive pas).
const MONTANT_COURT = /\d\s?(?:M|Mio|Mrd|Mds?|k|K)(?![A-Za-zÀ-ÿ²³])/;
const GRAND_NOMBRE = /\d{1,3}(?:[’'., ]\d{3}){2,}(?!\d)|\d{7,}/;
const LIBELLE_ARGENT = /\b(?:prix|price|charges?|imp[oô]ts?|tax\w*|ibi|loyer|rent|fees?|frais|valeur|value|co[uû]ts?|cost)\b/i;

export const porteUnMontant = (t) => [MONTANT, MONTANT_COURT, GRAND_NOMBRE].some((m) => m.test(String(t ?? "")));

/** L'adresse d'une fiche sans prix (la fiche partenaire) : la commune seulement, jamais la rue ni le numéro. */
export function commune(adresse) {
  const derniere = String(adresse ?? "").split(",").pop().trim().replace(/^\d{4,5}\s+/, "");
  return /\d/.test(derniere) ? "" : derniere;
}

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
    // Le titre garde ses mots, sans le montant ; un équipement ou une mention qui en porte un part.
    titre: porteUnMontant(fiche.titre)
      ? String(fiche.titre).split(/\s*(?:,|\(|\)|\||\s[–-]\s)\s*/).filter((m) => m && !porteUnMontant(m)).join(", ")
      : fiche.titre,
    adresse: commune(fiche.adresse),
    confidentiel: porteUnMontant(fiche.confidentiel) ? null : fiche.confidentiel,
    equipements: (fiche.equipements || []).filter((e) => !porteUnMontant(e)),
    accroche: sansMontants(fiche.accroche),
    description: propre,
    chiffres: (fiche.chiffres || []).filter((c) => !LIBELLE_ARGENT.test(c.libelle) && !porteUnMontant(c.valeur)),
    details: (fiche.details || []).filter(([l, v]) => !LIBELLE_ARGENT.test(l) && !porteUnMontant(v)),
  };
}
