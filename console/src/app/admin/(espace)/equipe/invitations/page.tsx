import { aPuDonner, peutDonnerRole, perimetreVu, roleLePlusEtroit } from "@/lib/admin/acces";
import { gardePage } from "@/lib/admin/garde";
import { invitationsEnAttente } from "@/lib/admin/invitations";
import { listerRoles } from "@/lib/admin/roles";
import { TA } from "@/lib/admin/textes";
import { base } from "@/lib/base";
import { OngletsEquipe } from "../onglets";
import { Invitations, type InvitationVue } from "./invitations";

// Les invitations : en créer une (son lien n'est montré qu'une fois), voir celles en attente, en retirer.
export default async function PageInvitations() {
  const a = await gardePage("equipe.gerer");
  const db = base();
  const roles = listerRoles(db);
  const donnables = roles.filter((r) => peutDonnerRole(a, r));
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
      <OngletsEquipe actif="/admin/equipe/invitations" />
      <Invitations
        invitations={invitations}
        roles={donnables.map((r) => ({ id: r.id, nom: r.nom }))}
        defaut={roleLePlusEtroit(donnables)}
        tousPermis={a.perimetre === "tous"}
      />
    </>
  );
}

export const instant = false;
