import { Onglets } from "@/components/admin/onglets";
import { TA } from "@/lib/admin/textes";

// Les onglets de l'Équipe, partagés par ses trois pages.
export function OngletsEquipe({ actif }: { actif: "/admin/equipe" | "/admin/equipe/invitations" | "/admin/equipe/roles" }) {
  return (
    <Onglets
      actif={actif}
      onglets={[
        { href: "/admin/equipe", texte: TA.membres },
        { href: "/admin/equipe/invitations", texte: TA.invitations },
        { href: "/admin/equipe/roles", texte: TA.roles },
      ]}
    />
  );
}
