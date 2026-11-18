import { Onglets } from "@/components/admin/onglets";
import { aPuDonner, peutDonnerRole, perimetreVu } from "@/lib/admin/acces";
import { DROITS_EXTERNE } from "@/lib/admin/droits";
import { gardePage } from "@/lib/admin/garde";
import { invitationsEnAttente } from "@/lib/admin/invitations";
import { listerRoles } from "@/lib/admin/roles";
import { TA } from "@/lib/admin/textes";
import { base } from "@/lib/base";
import { Invitations, type InvitationVue } from "./invitations";

// Les invitations : en créer une (son lien n'est montré qu'une fois), voir celles en attente, en retirer.
export default async function PageInvitations() {
  const a = await gardePage("equipe.gerer");
  const db = base();
  const roles = listerRoles(db);
  const invitations: InvitationVue[] = invitationsEnAttente(db).map((i) => {
    const role = roles.find((r) => r.id === i.role);
    return {
      id: i.id,
      courriel: i.courriel,
      roleNom: role?.nom ?? i.role,
      externe: i.externe,
      perimetre: perimetreVu(a, i.perimetre),
      finAccesLisible: i.finAcces ? TA.jour(i.finAcces) : TA.sansFin,
      valableJusqua: TA.instant(i.valableJusqua),
      retirable: aPuDonner(a, role, i.perimetre),
    };
  });
  return (
    <>
      <h1 className="m-0 text-[26px] font-extrabold tracking-[-0.02em]">{TA.equipe}</h1>
      <Onglets
        actif="/admin/equipe/invitations"
        onglets={[
          { href: "/admin/equipe", texte: TA.membres },
          { href: "/admin/equipe/invitations", texte: TA.invitations },
          { href: "/admin/equipe/roles", texte: TA.roles },
        ]}
      />
      <Invitations
        invitations={invitations}
        roles={roles.filter((r) => peutDonnerRole(a, r)).map((r) => ({ id: r.id, nom: r.nom }))}
        tousPermis={a.perimetre === "tous"}
        droitsExterne={DROITS_EXTERNE.map((d) => TA.nomsDroits[d])}
      />
    </>
  );
}

export const instant = false;
