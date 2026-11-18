import Link from "next/link";
import { Tete } from "@/components/console/tete";
import { buttonVariants } from "@/components/ui/button";
import { T } from "@/lib/textes";

// La page de tout notFound(), à la racine seulement : jamais sous admin/, où elle s'afficherait dans la coquille pour un
// membre et différerait d'une adresse inconnue pour les autres (l'admin s'efface comme s'il n'existait pas).
export default function PageIntrouvable() {
  return (
    <main className="flex min-h-dvh items-center justify-center bg-side px-4 py-10">
      <div className="trait w-full max-w-[400px] rounded-[28px] bg-bg px-7 pt-6 pb-7 shadow-doux">
        <Tete couleur={0} yeux={0} className="flotte mx-auto w-[120px]" />
        <h1 className="mt-3 mb-5 text-center text-[24px] font-extrabold tracking-[-0.02em]">{T.pageIntrouvable}</h1>
        <Link href="/" className={buttonVariants({ variant: "outline", className: "h-11 w-full rounded-full text-[14.5px] font-semibold" })}>
          {T.retourAccueil}
        </Link>
      </div>
    </main>
  );
}
