import Link from "next/link";

// Des onglets en liens : chacun est une adresse, l'actif est marqué pour les lecteurs d'écran.

export function Onglets({ onglets, actif }: { onglets: { href: string; texte: string }[]; actif: string }) {
  return (
    <nav className="flex max-w-full gap-1 overflow-x-auto pb-1 [scrollbar-width:none]">
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
