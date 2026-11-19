import { lirePhoto } from "@/lib/admin/photo";
import { TA } from "@/lib/admin/textes";
import { sessionDe } from "@/lib/auth";
import { pret } from "@/lib/base";
import { T } from "@/lib/textes";

// La photo d'un compte, pour qui est connecté à la console (comme son nom) ; jamais sans session. L'adresse porte la version
// (?v=), qui change avec la photo : elle se garde en cache, privée. Ni devinée par le navigateur, ni capable de rien exécuter.
export async function GET(requete: Request, { params }: { params: Promise<{ utilisateur: string }> }) {
  const s = await sessionDe(requete);
  if (!s) return Response.json({ erreur: T.connectezVous }, { status: 401 });
  const { utilisateur } = await params;
  const photo = await lirePhoto(await pret(), utilisateur);
  if (!photo) return Response.json({ erreur: TA.introuvable }, { status: 404 });
  return new Response(Buffer.from(photo.octets), {
    headers: {
      "Content-Type": photo.type,
      "Cache-Control": "private, max-age=31536000, immutable",
      "X-Content-Type-Options": "nosniff",
      "Content-Security-Policy": "default-src 'none'",
    },
  });
}
