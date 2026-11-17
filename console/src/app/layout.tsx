import type { Metadata } from "next";
import { Figtree } from "next/font/google";
import "./globals.css";

const figtree = Figtree({ variable: "--font-figtree", subsets: ["latin"], weight: ["400", "500", "600", "700", "800"] });

export const metadata: Metadata = {
  title: "MEGGA",
  description: "Vos agents MEGGA",
};

// Avant le premier affichage : le thème (choisi, sinon celui de l'appareil), et l'anneau de focus au clavier seulement.
const DEMARRAGE = `(function(){var d=document.documentElement;function t(){var c=null;try{c=localStorage.getItem("theme")}catch(e){}
var s=c?c==="sombre":matchMedia("(prefers-color-scheme: dark)").matches;d.setAttribute("data-theme",s?"douce":"light")}
t();matchMedia("(prefers-color-scheme: dark)").addEventListener("change",t);window.__theme=t;
addEventListener("mousedown",function(){d.classList.add("souris")},true);
addEventListener("keydown",function(e){if(e.key==="Tab")d.classList.remove("souris")},true)})();`;

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="fr" className={figtree.variable} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: DEMARRAGE }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
