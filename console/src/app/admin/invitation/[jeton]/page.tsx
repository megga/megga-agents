import { connection } from "next/server";
import { etatInvitation, lireInvitation } from "@/lib/admin/invitations";
import { session } from "@/lib/auth";
import { pret } from "@/lib/base";
import { Rejoindre } from "./rejoindre";

// La page d'un lien d'invitation, ouverte à qui n'est pas encore membre (hors de la coquille et de sa garde).
// Ce qu'elle montre suit etatInvitation ; l'acceptation elle-même passe par POST /api/admin/invitation.
export default async function PageInvitation({ params }: PageProps<"/admin/invitation/[jeton]">) {
  await connection(); // à la requête seulement : une invitation expire à l'heure du moment
  const { jeton } = await params;
  const s = await session();
  const invitation = await lireInvitation(await pret(), jeton);
  const etat = etatInvitation(invitation, s?.user.email ?? null);
  return <Rejoindre etat={etat} jeton={jeton} courriel={invitation?.courriel ?? ""} />;
}

export const instant = false;
