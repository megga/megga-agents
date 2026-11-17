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
export const Mallette = (p: P) => (
  <svg {...base} {...p}><rect x="3.5" y="7.5" width="17" height="12" rx="2.5" strokeWidth="1.8" /><path d="M9 7.5V6a2 2 0 012-2h2a2 2 0 012 2v1.5M3.5 12.5h17" strokeWidth="1.8" /></svg>
);
