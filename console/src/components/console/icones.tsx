// Les icônes de la maquette, reprises telles quelles (24 × 24, trait courant).
import type { SVGProps } from "react";

type P = SVGProps<SVGSVGElement>;
const base = { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "aria-hidden": true } as const;

export const Loupe = (p: P) => (
  <svg {...base} {...p}><circle cx="11" cy="11" r="6.5" strokeWidth="1.9" /><path d="M16 16l4.5 4.5" strokeWidth="1.9" strokeLinecap="round" /></svg>
);
export const Plus = (p: P) => (
  <svg {...base} {...p}><path d="M12 5v14M5 12h14" strokeWidth="2" strokeLinecap="round" /></svg>
);
export const Fleche = (p: P) => (
  <svg {...base} {...p}><path d="M12 19V5M6 11l6-6 6 6" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" /></svg>
);
export const HautBas = (p: P) => (
  <svg {...base} {...p}><path d="M8 9.5l4-4 4 4M8 14.5l4 4 4-4" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" /></svg>
);
export const Epingle = (p: P) => (
  <svg {...base} {...p}><path d="M9 4h6l-1 5 3 3v2H7v-2l3-3-1-5zM12 14v6" strokeWidth="1.8" strokeLinejoin="round" strokeLinecap="round" /></svg>
);
export const Palette = (p: P) => (
  <svg {...base} {...p}>
    <path d="M12 3a9 9 0 100 18c1.1 0 1.6-.8 1.6-1.6 0-.9-.7-1.3-.7-2.1 0-1 .8-1.7 1.8-1.7h2.1A4.2 4.2 0 0021 11.4C21 6.8 17 3 12 3z" strokeWidth="1.8" strokeLinejoin="round" />
    <circle cx="7.5" cy="11" r="1.3" fill="currentColor" stroke="none" /><circle cx="10.5" cy="7.3" r="1.3" fill="currentColor" stroke="none" /><circle cx="15" cy="7.6" r="1.3" fill="currentColor" stroke="none" />
  </svg>
);
export const Oeil = (p: P) => (
  <svg {...base} {...p}><path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z" strokeWidth="1.8" strokeLinejoin="round" /><circle cx="12" cy="12" r="3" strokeWidth="1.8" /></svg>
);
// Activité : l'icône Phosphor deux tons de la maquette (pulse).
export const Activite = (p: P) => (
  <svg viewBox="0 0 256 256" fill="currentColor" aria-hidden {...p}>
    <path d="m96 40l33.52 88H56Zm104 88h-70.48L160 208Z" opacity=".2" />
    <path d="M240 128a8 8 0 0 1-8 8h-27.06l-37.78 75.58A8 8 0 0 1 160 216h-.4a8 8 0 0 1-7.08-5.14L95.35 60.76l-32.07 70.55A8 8 0 0 1 56 136H24a8 8 0 0 1 0-16h26.85l37.87-83.31a8 8 0 0 1 14.76.46l57.51 151l31.85-63.71A8 8 0 0 1 200 120h32a8 8 0 0 1 8 8" />
  </svg>
);
export const Chevron = (p: P) => (
  <svg {...base} {...p}><path d="M9 6l6 6-6 6" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
);
export const Triangle = (p: P) => (
  <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden {...p}><path d="M10.3 3.9a2 2 0 013.4 0l8.1 14a2 2 0 01-1.7 3H3.9a2 2 0 01-1.7-3z" /><path d="M12 9v4.5M12 17h.01" stroke="#fff" strokeWidth="2" strokeLinecap="round" /></svg>
);
export const Mallette = (p: P) => (
  <svg {...base} {...p}><rect x="3.5" y="7.5" width="17" height="12" rx="2.5" strokeWidth="1.8" /><path d="M9 7.5V6a2 2 0 012-2h2a2 2 0 012 2v1.5M3.5 12.5h17" strokeWidth="1.8" /></svg>
);
