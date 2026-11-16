// La fiche PDF d'une annonce, reprise d'Alix FSP (fiche/pdf.js) sans changer sa mise en page, sur le modèle
// « Refonte design My Properties » des fiches de Grégory (A4) :
//
//   page 1     la photo de couverture, l'adresse en petites capitales,
//              puis le titre, quatre chiffres clés et le prix
//   ensuite    l'accroche et la description, puis le tableau des détails
//              et les équipements sur trois colonnes
//   enfin      les photos, deux par page
//
// Deux versions : « marque » ajoute le logo sur la couverture, les
// coordonnées du courtier et la marque en pied de page ; « anonyme » n'a ni
// logo, ni nom d'agence, ni coordonnées, jusque dans les métadonnées.
//
// `fiche` vient de la gestion du site (gestion/fiche.mjs) ou des éléments
// donnés sur WhatsApp ; `photos` sont les octets des images, la première
// faisant la couverture. JPEG et PNG seulement ; une autre image est ignorée.
import fontkit from "@pdf-lib/fontkit";
import { PDFDocument, clip, endPath, popGraphicsState, pushGraphicsState, rectangle, rgb, setCharacterSpacing } from "pdf-lib";
import { ficheSansPrix } from "./sansprix.js";

const W = 595.28;
const H = 841.89;
const M = 42;
const HAUT = H - 56;
const BAS = 64;

// Une couleur CSS en hexadécimal (« #0c1836 »), ou « white », comme dans le logo.
const couleur = (h) => {
  const x = String(h).toLowerCase() === "white" ? "#ffffff" : String(h);
  return rgb(parseInt(x.slice(1, 3), 16) / 255, parseInt(x.slice(3, 5), 16) / 255, parseInt(x.slice(5, 7), 16) / 255);
};
const NUIT = couleur("#0c1836");
const TEXTE = couleur("#3d3d48");
const FONCE = couleur("#2a2a33");
const GRIS = couleur("#8a8a96");
const FILET = couleur("#e6e1da");
const BLANC = rgb(1, 1, 1);
const NOIR = rgb(0, 0, 0);

const MOTS = {
  fr: { equipements: "Équipements et prestations", contact: "Votre contact", tel: "Tél." },
  en: { equipements: "Amenities", contact: "Your contact", tel: "Tel." },
};

const octetsDe = (b64) => Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));

/** Le type d'une image d'après ses premiers octets. */
export function typeImage(o) {
  if (o[0] === 0xff && o[1] === 0xd8 && o[2] === 0xff) return "jpeg";
  if (o[0] === 0x89 && o[1] === 0x50 && o[2] === 0x4e && o[3] === 0x47) return "png";
  return null;
}

// L'écriture des titres, des chiffres, du prix et du contact : Instrument
// Serif, celle de l'application de gestion, choisie par Julien le 12.11.2026
// pour son cachet — plus fine, donc composée plus grand, le prix en
// italique. Gambetta, la serif du site et des fiches d'origine de Grégory,
// reste disponible (serif: "gambetta"). Le texte courant est en Poppins.
const TYPO = {
  gambetta: { titre: 25, interligne: 30, chiffre: 19, prix: 16, intertitre: 13.5, contact: 15 },
  instrument: { titre: 31, interligne: 33, chiffre: 24, prix: 21, intertitre: 17, contact: 20 },
};

/**
 * Les octets du PDF. `sansPrix` : aucun prix ni montant nulle part (sansprix.js),
 * pour la fiche partenaire. `trace`, facultatif, reçoit chaque texte posé (pour les tests).
 */
export async function composerFiche(fiche, photos = [], { version = "marque", serif = "instrument", sansPrix = false, trace = null, ressources, marque: nomMarque = "" } = {}) {
  // Les polices et le logo du modèle de fiche du client (modeles/<modèle>/ressources.js), et le nom de sa marque.
  const { LOGO, POLICES } = ressources;
  if (sansPrix) fiche = ficheSansPrix(fiche);
  const instrument = serif !== "gambetta";
  const T = TYPO[instrument ? "instrument" : "gambetta"];
  const marque = version !== "anonyme";
  const mots = MOTS[fiche.langue === "en" ? "en" : "fr"];
  // Sans les métadonnées que pdf-lib pose d'office (« Producer: pdf-lib… »).
  const pdf = await PDFDocument.create({ updateMetadata: false });
  pdf.registerFontkit(fontkit);
  const f = {
    titre: await pdf.embedFont(octetsDe(instrument ? POLICES.instrument : POLICES.titre)),
    texte: await pdf.embedFont(octetsDe(POLICES.texte)),
    moyen: await pdf.embedFont(octetsDe(POLICES.texteMoyen)),
  };
  f.prix = instrument ? await pdf.embedFont(octetsDe(POLICES.instrumentItalique)) : f.titre;
  // Les métadonnées aussi : une fiche anonyme ne doit rien dire de l'agence.
  pdf.setTitle(fiche.titre || "");
  pdf.setProducer("");
  pdf.setCreator(marque ? nomMarque : "");
  if (marque && fiche.contact) pdf.setAuthor(fiche.contact.nom);

  const images = [];
  for (const o of photos) {
    const genre = typeImage(o);
    if (!genre) continue;
    try {
      images.push(genre === "jpeg" ? await pdf.embedJpg(o) : await pdf.embedPng(o));
    } catch (e) {
      console.warn("fiche : image illisible", e.message);
    }
  }

  // ── Les outils de dessin ──────────────────────────────────────
  // Chaque page a un fond blanc : sans lui, la page est transparente, et
  // certains aperçus (dont celui de WhatsApp) la montrent en noir.
  const ajouterPage = () => {
    const p = pdf.addPage([W, H]);
    p.drawRectangle({ x: 0, y: 0, width: W, height: H, color: BLANC });
    return p;
  };
  const jeux = new Map(Object.values(f).map((p) => [p, new Set(p.getCharacterSet())]));
  const nettoyer = (t) => String(t ?? "").replace(/[\u00a0\u2009\u202f\t\r\n]+/g, " ");
  // Un texte en morceaux de même police : un caractère qu'une police n'a pas
  // est pris dans une autre (Instrument Serif n'a pas « ² » : il devient un
  // « 2 » en exposant), sinon omis plutôt que dessiné en carré vide.
  const EXPOSANTS = { "²": "2", "³": "3" };
  const morceaux = (t, police, taille) => {
    const liste = [];
    const ajouter = (texte, p, tl, monte = 0) => {
      const d = liste[liste.length - 1];
      if (d && d.p === p && d.tl === tl && d.monte === monte) d.texte += texte;
      else liste.push({ texte, p, tl, monte });
    };
    for (const c of nettoyer(t)) {
      const cp = c.codePointAt(0);
      if (jeux.get(police).has(cp)) ajouter(c, police, taille);
      else if (EXPOSANTS[c] && jeux.get(police).has(EXPOSANTS[c].codePointAt(0))) ajouter(EXPOSANTS[c], police, taille * 0.6, taille * 0.36);
      else {
        const secours = [f.texte, f.titre].find((p) => jeux.get(p).has(cp));
        if (secours) ajouter(c, secours, taille);
      }
    }
    return liste;
  };
  // Ce qui se lit : le texte tel qu'il paraît, exposants compris.
  const visible = (t, police) => {
    const jeu = jeux.get(police);
    return [...nettoyer(t)].filter((c) => jeu.has(c.codePointAt(0)) || EXPOSANTS[c] || jeux.get(f.texte).has(c.codePointAt(0)) || jeux.get(f.titre).has(c.codePointAt(0))).join("");
  };
  const largeur = (t, police, taille, espace = 0) =>
    morceaux(t, police, taille).reduce((l, m) => l + m.p.widthOfTextAtSize(m.texte, m.tl) + espace * [...m.texte].length, 0) - (espace ? espace : 0);
  const ecrire = (page, t, { x, y, police = f.texte, taille = 9, teinte = TEXTE, espace = 0, opacite = 1 }) => {
    const liste = morceaux(t, police, taille);
    if (!liste.length) return;
    trace?.push(visible(t, police));
    if (espace) page.pushOperators(setCharacterSpacing(espace));
    for (const m of liste) {
      page.drawText(m.texte, { x, y: y + m.monte, font: m.p, size: m.tl, color: teinte, opacity: opacite });
      x += m.p.widthOfTextAtSize(m.texte, m.tl) + espace * [...m.texte].length;
    }
    if (espace) page.pushOperators(setCharacterSpacing(0));
  };
  const couper = (t, police, taille, max) => {
    const lignes = [];
    let ligne = "";
    // Un mot dont aucun caractère ne s'écrit disparaît, sans laisser d'espace double.
    for (const mot of nettoyer(t).split(" ").filter((m) => visible(m, police))) {
      const essai = ligne ? `${ligne} ${mot}` : mot;
      if (ligne && largeur(essai, police, taille) > max) {
        lignes.push(ligne);
        ligne = mot;
      } else ligne = essai;
    }
    if (ligne) lignes.push(ligne);
    return lignes;
  };
  const filet = (page, x1, y1, x2, y2, epaisseur = 0.6) => page.drawLine({ start: { x: x1, y: y1 }, end: { x: x2, y: y2 }, thickness: epaisseur, color: FILET });
  // Une image qui remplit son cadre, recadrée au centre, comme « object-fit: cover ».
  const couvrir = (page, image, x, y, l, h) => {
    const echelle = Math.max(l / image.width, h / image.height);
    const dl = image.width * echelle;
    const dh = image.height * echelle;
    page.pushOperators(pushGraphicsState(), rectangle(x, y, l, h), clip(), endPath());
    page.drawImage(image, { x: x + (l - dl) / 2, y: y + (h - dh) / 2, width: dl, height: dh });
    page.pushOperators(popGraphicsState());
  };
  // Le logo à une hauteur donnée : sa largeur suit le dessin du wordmark.
  const largeurLogo = (h) => (h * LOGO.largeur) / LOGO.hauteur;
  const logo = (page, formes, x, haut, h) => {
    const e = h / LOGO.hauteur;
    for (const forme of formes) {
      if (forme.d) page.drawSvgPath(forme.d, { x, y: haut, scale: e, color: couleur(forme.fill), borderWidth: 0 });
      else {
        const [rx, ry, rl, rh] = forme.rect;
        page.drawRectangle({ x: x + rx * e, y: haut - (ry + rh) * e, width: rl * e, height: rh * e, color: couleur(forme.fill) });
      }
    }
    trace?.push("[logo]");
  };
  const capitales = (t) => String(t ?? "").toLocaleUpperCase(fiche.langue === "en" ? "en" : "fr");

  // ── La couverture ─────────────────────────────────────────────
  const couverture = ajouterPage();
  const lignesTitre = couper(fiche.titre, f.titre, T.titre, W - 2 * M).slice(0, 3);
  const chiffres = (fiche.chiffres || []).slice(0, 4);
  const hauteurPanneau = 40 + lignesTitre.length * T.interligne + (chiffres.length ? 62 + (T.chiffre - 19) : 0) + 18 + 22 + (T.prix - 16) + 34;
  const hPhoto = H - hauteurPanneau;
  if (images[0]) couvrir(couverture, images[0], 0, H - hPhoto, W, hPhoto);
  else couverture.drawRectangle({ x: 0, y: H - hPhoto, width: W, height: hPhoto, color: NUIT });
  // Un voile sombre en bas de la photo, où se lit l'adresse ; en haut aussi, sous le logo.
  for (let i = 0; i < 16; i++) {
    couverture.drawRectangle({ x: 0, y: H - hPhoto + i * 10, width: W, height: 10, color: NOIR, opacity: 0.03 * (16 - i) });
  }
  if (marque) {
    for (let i = 0; i < 12; i++) couverture.drawRectangle({ x: 0, y: H - (i + 1) * 10, width: W, height: 10, color: NOIR, opacity: 0.04 * (12 - i) });
    logo(couverture, LOGO.surPhoto, M, H - 36, 15);
  }
  let y = H - hPhoto + 26;
  ecrire(couverture, capitales(fiche.adresse), { x: M, y, police: f.moyen, taille: 6.6, teinte: BLANC, espace: 1.4 });
  if (fiche.confidentiel) ecrire(couverture, capitales(fiche.confidentiel), { x: M, y: y + 14, police: f.moyen, taille: 6.6, teinte: BLANC, espace: 1.4, opacite: 0.85 });

  y = H - hPhoto - 40 - 20;
  for (const l of lignesTitre) {
    ecrire(couverture, l, { x: M, y, police: f.titre, taille: T.titre, teinte: NUIT });
    y -= T.interligne;
  }
  if (chiffres.length) {
    const colonne = (W - 2 * M) / chiffres.length;
    const haut = y + 6;
    chiffres.forEach((c, i) => {
      const x = M + i * colonne + (i ? 14 : 0);
      if (i) filet(couverture, M + i * colonne, haut, M + i * colonne, haut - 44 - (T.chiffre - 19));
      ecrire(couverture, capitales(c.libelle), { x, y: haut - 8, police: f.moyen, taille: 5.4, teinte: GRIS, espace: 0.8 });
      // « 960 m² » : le nombre en grand, l'unité en petit, comme sur le modèle.
      const [, nombre, unite] = /^(\d(?:[\d’',. ]*\d)?)\s*(.*)$/.exec(String(c.valeur)) || [null, String(c.valeur), ""];
      const base = haut - 34 - (T.chiffre - 19);
      ecrire(couverture, nombre.trim(), { x, y: base, police: f.titre, taille: T.chiffre, teinte: NUIT });
      if (unite) ecrire(couverture, unite, { x: x + largeur(nombre.trim(), f.titre, T.chiffre) + 3, y: base, police: f.texte, taille: 7.5, teinte: NUIT });
    });
    y = haut - 62 - (T.chiffre - 19);
  }
  filet(couverture, M, y + 8, W - M, y + 8);
  ecrire(couverture, fiche.prix, { x: W - M - largeur(fiche.prix, f.prix, T.prix), y: y - T.prix, police: f.prix, taille: T.prix, teinte: NUIT });

  // ── Le texte, qui coule de page en page ───────────────────────
  let page = null;
  const nouvellePage = () => {
    page = ajouterPage();
    y = HAUT;
  };
  const place = (h) => {
    if (!page || y - h < BAS) nouvellePage();
  };
  const paragraphe = (t, { retrait = 0, puce = false } = {}) => {
    const lignes = couper(t, f.texte, 9.4, W - 2 * M - retrait);
    lignes.forEach((l, i) => {
      place(15);
      if (puce && i === 0) page.drawRectangle({ x: M + 2, y: y + 2.4, width: 2.6, height: 2.6, color: NUIT });
      ecrire(page, l, { x: M + retrait, y, taille: 9.4, teinte: TEXTE });
      y -= 15;
    });
  };

  const description = Array.isArray(fiche.description) ? fiche.description : [];
  const accroche = String(fiche.accroche || "").trim();
  const premier = typeof description[0] === "string" ? description[0] : "";
  // L'accroche ouvre le texte, sauf si la description commence déjà par elle.
  if (accroche && !premier.startsWith(accroche.replace(/[.…]+$/, ""))) {
    paragraphe(accroche);
    y -= 9;
  }
  for (const b of description) {
    if (typeof b === "string") {
      paragraphe(b);
      y -= 9;
    } else if (b[0] === "titre") {
      place(34);
      y -= 8;
      ecrire(page, b[1], { x: M, y, police: f.titre, taille: T.intertitre, teinte: NUIT });
      y -= T.intertitre + 6.5;
    } else if (b[0] === "liste") {
      for (const element of b[1]) paragraphe(element, { retrait: 12, puce: true });
      y -= 9;
    }
  }

  // ── Les détails, sur une page à eux, comme sur le modèle ──────
  const details = fiche.details || [];
  if (details.length) {
    nouvellePage();
    for (const [libelle, valeur] of details) {
      const lignes = couper(valeur, f.texte, 8.8, (W - 2 * M) * 0.58);
      place(10 + lignes.length * 13);
      ecrire(page, libelle, { x: M, y, taille: 8.8, teinte: GRIS });
      lignes.forEach((l, i) => ecrire(page, l, { x: W - M - largeur(l, f.texte, 8.8), y: y - i * 13, taille: 8.8, teinte: FONCE }));
      y -= (lignes.length - 1) * 13;
      filet(page, M, y - 9, W - M, y - 9, 0.5);
      y -= 23;
    }
  }

  const equipements = fiche.equipements || [];
  if (equipements.length) {
    place(60);
    y -= 14;
    ecrire(page, capitales(mots.equipements), { x: M, y, police: f.moyen, taille: 5.6, teinte: GRIS, espace: 1.6 });
    y -= 12;
    const ecart = 18;
    const colonne = (W - 2 * M - 2 * ecart) / 3;
    for (let i = 0; i < equipements.length; i += 3) {
      place(24);
      equipements.slice(i, i + 3).forEach((e, j) => {
        const x = M + j * (colonne + ecart);
        filet(page, x, y, x + colonne, y, 0.5);
        page.drawRectangle({ x, y: y - 13.4, width: 2.6, height: 2.6, color: NUIT });
        ecrire(page, couper(e, f.texte, 8.8, colonne - 10)[0] || "", { x: x + 9, y: y - 15, taille: 8.8, teinte: FONCE });
      });
      y -= 22;
    }
  }

  // ── Les coordonnées du courtier (version de marque) ───────────
  const c = fiche.contact;
  if (marque && c) {
    place(130);
    y -= 26;
    filet(page, M, y, W - M, y);
    y -= 24;
    ecrire(page, capitales(mots.contact), { x: M, y, police: f.moyen, taille: 5.6, teinte: GRIS, espace: 1.6 });
    logo(page, LOGO.surBlanc, W - M - largeurLogo(13), y + 6, 13);
    y -= 9 + T.contact;
    ecrire(page, c.nom, { x: M, y, police: f.titre, taille: T.contact, teinte: NUIT });
    y -= 1 + T.contact;
    if (c.fonction) {
      ecrire(page, c.fonction, { x: M, y, taille: 8.8, teinte: GRIS });
      y -= 18;
    }
    for (const l of [c.email, c.telephone && `${mots.tel} ${c.telephone}`, c.site].filter(Boolean)) {
      ecrire(page, l, { x: M, y, taille: 9, teinte: TEXTE });
      y -= 14;
    }
  }

  // ── Les photos, deux par page ─────────────────────────────────
  const reste = images.slice(1);
  const hCadre = (H - 2 * M - 12 - 22) / 2;
  for (let i = 0; i < reste.length; i += 2) {
    const p = ajouterPage();
    couvrir(p, reste[i], M, H - M - hCadre, W - 2 * M, hCadre);
    if (reste[i + 1]) couvrir(p, reste[i + 1], M, H - M - 2 * hCadre - 12, W - 2 * M, hCadre);
  }

  // ── Pieds de page, hors couverture ────────────────────────────
  pdf.getPages().forEach((p, i) => {
    if (!i) return;
    const n = String(i + 1).padStart(2, "0");
    ecrire(p, n, { x: W - M - largeur(n, f.moyen, 6.5), y: 30, police: f.moyen, taille: 6.5, teinte: GRIS });
    if (marque && nomMarque) ecrire(p, nomMarque.toUpperCase(), { x: M, y: 30, police: f.moyen, taille: 6, teinte: GRIS, espace: 1.6 });
  });

  return pdf.save();
}
