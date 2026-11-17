import { getSessionCookie } from "better-auth/cookies";
import { NextResponse, type NextRequest } from "next/server";

// Un premier tri, sans base : sans cookie de session, direction la connexion.
// La vraie vérification se fait côté serveur, page par page et route par route.
export function proxy(requete: NextRequest) {
  if (!getSessionCookie(requete)) return NextResponse.redirect(new URL("/connexion", requete.url));
  return NextResponse.next();
}

export const config = { matcher: ["/"] };
