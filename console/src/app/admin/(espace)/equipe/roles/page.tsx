import { Onglets } from "@/components/admin/onglets";
import { peutEcrireRole } from "@/lib/admin/acces";
import { DROITS } from "@/lib/admin/droits";
import { gardePage } from "@/lib/admin/garde";
import { invitationsEnAttente } from "@/lib/admin/invitations";
import { listerRoles } from "@/lib/admin/roles";
import { TA } from "@/lib/admin/textes";
import { base } from "@/lib/base";
import { Roles, type RoleVu } from "./roles";

// Les rôles : les droits cochés par groupe, le nombre de membres ; créer, modifier, retirer ce que la non-escalade permet.
export default async function PageRoles() {
  const a = await gardePage("equipe.gerer");
  const db = base();
  const nommes = new Set(invitationsEnAttente(db).map((i) => i.role));
  const roles: RoleVu[] = listerRoles(db).map((r) => {
    const modifiable = !r.systeme && peutEcrireRole(a, r.droits, r.id);
    return {
      id: r.id,
      nom: r.nom,
      description: r.description,
      droits: r.droits,
      systeme: r.systeme,
      membres: r.membres,
      modifiable,
      retirable: modifiable && r.membres === 0 && !nommes.has(r.id),
    };
  });
  return (
    <>
      <h1 className="m-0 text-[26px] font-extrabold tracking-[-0.02em]">{TA.equipe}</h1>
      <Onglets
        actif="/admin/equipe/roles"
        onglets={[
          { href: "/admin/equipe", texte: TA.membres },
          { href: "/admin/equipe/invitations", texte: TA.invitations },
          { href: "/admin/equipe/roles", texte: TA.roles },
        ]}
      />
      <Roles roles={roles} peutCreer={peutEcrireRole(a, [], null)} permis={DROITS.filter((d) => a.droits.has(d))} />
    </>
  );
}

export const instant = false;
