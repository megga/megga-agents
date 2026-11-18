import Link from "next/link";

// Des onglets en liens : chacun est une adresse, l'actif est marqué pour les lecteurs d'écran. Trop nombreux pour la largeur
// (les six d'un client à 800 px), ils passent à la ligne : aucun ne se cache hors du cadre, sans barre pour le dire.

/** Les onglets qui portent une période (periode) la gardent : ?jours=1, 7 ou 30 de l'adresse ; autre chose n'est pas repris. */
export function avecPeriode(onglets: { href: string; texte: string; periode?: boolean }[], jours: string | null): { href: string; texte: string }[] {
  const garde = jours === "1" || jours === "7" || jours === "30";
  return onglets.map((o) => ({ href: o.periode && garde ? `${o.href}?jours=${jours}` : o.href, texte: o.texte }));
}

export function Onglets({ onglets, actif }: { onglets: { href: string; texte: string }[]; actif: string }) {
  return (
    <nav className="flex max-w-full flex-wrap gap-1 pb-1">
      {onglets.map((o) => (
        <Link
          key={o.href}
          href={o.href}
          aria-current={o.href === actif ? "page" : undefined}
          className="flex-none rounded-full px-3.5 py-1.5 text-[14px] font-semibold whitespace-nowrap text-muted-ink hover:bg-hover hover:text-ink aria-[current=page]:bg-ink aria-[current=page]:text-bg"
        >
          {o.texte}
        </Link>
      ))}
    </nav>
  );
}
