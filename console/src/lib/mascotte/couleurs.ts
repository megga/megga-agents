import { TETE_SVG } from "./tete-source";

// Couleurs et yeux de la maquette (Studio de création). Chaque couleur : teinte, sourcils, puis trois nuances.
export const COULEURS: readonly (readonly [string, readonly string[]])[] = [
  ["Rouge", ["#D2372D", "#871510", "#B22C27", "#E17270", "#6C1018"]],
  ["Violet", ["#7A4FD6", "#46278F", "#6440B8", "#A88BEA", "#3A1F78"]],
  ["Bleu", ["#2F6FDE", "#173E8C", "#2659B8", "#7FA6EE", "#123270"]],
  ["Vert", ["#1FA971", "#0F6B46", "#188A5C", "#6FD3A6", "#0B5236"]],
  ["Orange", ["#F08A24", "#A4520A", "#CF7316", "#F6B26F", "#7E3E06"]],
  ["Rose", ["#E85A9B", "#9C2463", "#C9447F", "#F39BC3", "#7A1A4C"]],
  ["Graphite", ["#3A3D45", "#15161A", "#2A2C32", "#6A6E78", "#101114"]],
];

export const YEUX: readonly (readonly [string, readonly string[]])[] = [
  ["Marron", ["#81562D", "#A1713D", "#915D21"]],
  ["Bleu", ["#2E5E9E", "#4A84C9", "#244E85"]],
  ["Vert", ["#2F7D4F", "#4CA36D", "#25643F"]],
  ["Gris", ["#5A6270", "#7C8594", "#4A515D"]],
  ["Ambre", ["#B5651D", "#D9903B", "#9A5418"]],
];

const IRIS0 = '<circle r="45" fill="#81562D"/><circle r="38" fill="#A1713D"/><circle r="38" fill="none" stroke="#915D21"';

function remplacer(s: string, de: readonly string[], vers: readonly string[]): string {
  de.forEach((c, i) => {
    s = s.split(c).join(vers[i]).split(c.toLowerCase()).join(vers[i]);
  });
  return s;
}

export function borner(i: number, n: number): number {
  return Number.isInteger(i) && i >= 0 && i < n ? i : 0;
}

/** Le SVG de la tête dans cette couleur et ces yeux ; en sombre, les sourcils s'éclaircissent (comme la maquette).
 * Endormie : les paupières fermées et les « z » (quand rien ne se passe, page Activité). */
export function teteSvg(couleur: number, yeux: number, sombre: boolean, endormie = false): string {
  const c = borner(couleur, COULEURS.length);
  const y = borner(yeux, YEUX.length);
  let s = remplacer(TETE_SVG, COULEURS[0][1], COULEURS[c][1]);
  const iris = YEUX[y][1];
  s = s.split(IRIS0).join(`<circle r="45" fill="${iris[0]}"/><circle r="38" fill="${iris[1]}"/><circle r="38" fill="none" stroke="${iris[2]}"`);
  if (sombre) {
    s = s.replace(/(id="sourcil[GD]" fill=")#[0-9A-Fa-f]{6}/g, `$1${c === 0 ? "#F0584A" : COULEURS[c][1][3]}`);
  }
  if (endormie) {
    // Les paupières se recouvrent (aucun filet blanc entre elles) ; le cadre s'élargit pour les « z », la tête restant au centre.
    s = s.replace(/(class="lidTop" id="haut[LR]" transform=")translate\(0 -14\)/g, "$1translate(0 158)");
    s = s.replace(/(class="lidBot" id="bas[LR]" transform=")translate\(0 30\)/g, "$1translate(0 -24)");
    s = s.replace('id="fx-zzz" opacity="0"', 'id="fx-zzz" opacity="1"');
    s = s.replace('viewBox="182 176 662 514"', 'viewBox="126 176 774 514"');
  }
  return s;
}

export function teteUrl(couleur: number, yeux: number, sombre: boolean, endormie = false): string {
  return "data:image/svg+xml;charset=utf-8," + encodeURIComponent(teteSvg(couleur, yeux, sombre, endormie));
}
