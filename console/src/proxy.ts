import { getSessionCookie } from "better-auth/cookies";
import { NextResponse, type NextRequest } from "next/server";

// Un premier tri, sans base : sans cookie de session, direction la connexion (puis retour à /admin pour l'admin).
// La page d'une invitation passe : on peut l'ouvrir avant d'avoir un compte.
// La vraie vérification se fait côté serveur, page par page et route par route (src/lib/admin/garde.ts).
export function proxy(requete: NextRequest) {
  const chemin = requete.nextUrl.pathname;
  if (chemin.startsWith("/admin/invitation/") || getSessionCookie(requete)) return NextResponse.next();
  return NextResponse.redirect(new URL(chemin === "/" ? "/connexion" : "/connexion?retour=/admin", requete.url));
}

export const config = { matcher: ["/", "/admin/:path*"] };
