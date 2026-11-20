"use client";

import { useEffect, useMemo, useState } from "react";
import { teteUrl } from "@/lib/mascotte/couleurs";

/** Vrai quand la console est en Nuit douce (le thème peut changer sans recharger). */
export function useSombre(): boolean {
  const [sombre, setSombre] = useState(false);
  useEffect(() => {
    const d = document.documentElement;
    const lire = () => setSombre(d.getAttribute("data-theme") === "douce");
    lire();
    const o = new MutationObserver(lire);
    o.observe(d, { attributes: true, attributeFilter: ["data-theme"] });
    return () => o.disconnect();
  }, []);
  return sombre;
}

/** La tête de la mascotte dans la couleur et les yeux de l'agent. */
export function Tete({
  couleur,
  yeux,
  endormie = false,
  className,
  style,
}: {
  couleur: number;
  yeux: number;
  endormie?: boolean;
  className?: string;
  style?: React.CSSProperties;
}) {
  const sombre = useSombre();
  const src = useMemo(() => teteUrl(couleur, yeux, sombre, endormie), [couleur, yeux, sombre, endormie]);
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={src} alt="" className={"m " + (className ?? "")} style={style} draggable={false} />;
}
