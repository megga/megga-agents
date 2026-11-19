import { estAdressePhoto } from "@/lib/photo-adresse";

// L'avatar d'un compte, partout où l'écran le nomme (le menu du compte, l'équipe, les comptes, le journal) : sa photo
// (/api/compte/photo/..., servie à qui est connecté), sinon l'initiale de son nom. Une image qui n'a pas exactement la forme
// d'une photo de la console (une adresse d'ailleurs, une data: URI) donne l'initiale : rien ne se charge hors de la console.
// apercu : l'aperçu local (blob:) d'une photo pas encore envoyée, sur la page Mon compte. Les coins suivent la taille, comme
// l'initiale du menu du compte (36 px, 11 px de rayon). La photo est décorative : le nom est toujours écrit à côté.

export function initiale(nom: string): string {
  return ([...nom.trim()][0] ?? "M").toUpperCase();
}

export function Avatar({ nom, image, apercu, taille }: { nom: string; image?: string | null; apercu?: string | null; taille: number }) {
  const forme = { width: taille, height: taille, borderRadius: Math.round(taille * 0.3) };
  const source = apercu?.startsWith("blob:") ? apercu : estAdressePhoto(image) ? image : null;
  if (source) {
    // Une photo de la console, déjà réduite à 256 px : next/image n'apporterait rien et passerait sans le cookie de session.
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={source} alt="" width={taille} height={taille} style={forme} className="flex-none bg-side object-cover" />;
  }
  return (
    <span aria-hidden style={{ ...forme, fontSize: Math.round(taille * 0.4) }} className="grid flex-none place-items-center bg-ink font-extrabold text-bg">
      {initiale(nom)}
    </span>
  );
}
