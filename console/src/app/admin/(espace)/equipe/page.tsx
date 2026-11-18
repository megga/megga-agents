import { Onglets } from "@/components/admin/onglets";
import { aPuDonner, peutDonnerRole, peutToucherMembre, perimetreVu } from "@/lib/admin/acces";
import { gardePage } from "@/lib/admin/garde";
import { listerMembres } from "@/lib/admin/membres";
import { listerRoles } from "@/lib/admin/roles";
import { TA } from "@/lib/admin/textes";
import { base } from "@/lib/base";
import { Membres, type MembreVu } from "./membres";

// L'équipe, ses membres : tout se lit ici, côté serveur, après la garde. Le navigateur ne reçoit du périmètre d'un autre
// que ce que le membre en voit (perimetreVu), et ne propose que les gestes que la bibliothèque laissera passer.
export default async function PageMembres() {
  const a = await gardePage("equipe.gerer");
  const db = base();
  const roles = listerRoles(db);
  const membres: MembreVu[] = listerMembres(db).map((m) => {
    const role = roles.find((r) => r.id === m.role);
    return {
      utilisateur: m.utilisateur,
      nom: m.nom,
      courriel: m.courriel,
      role: m.role,
      roleNom: role?.nom ?? m.role,
      externe: m.externe,
      perimetre: perimetreVu(a, m.perimetre),
      finAcces: m.finAcces,
      finAccesLisible: m.finAcces ? TA.jour(m.finAcces) : TA.sansFin,
      derniereConnexion: m.derniereConnexion ? TA.instant(m.derniereConnexion) : TA.pasEncoreNotee,
      modifiable: peutToucherMembre(a, m) && aPuDonner(a, role, m.perimetre),
    };
  });
  return (
    <>
      <h1 className="m-0 text-[26px] font-extrabold tracking-[-0.02em]">{TA.equipe}</h1>
      <Onglets
        actif="/admin/equipe"
        onglets={[
          { href: "/admin/equipe", texte: TA.membres },
          { href: "/admin/equipe/invitations", texte: TA.invitations },
          { href: "/admin/equipe/roles", texte: TA.roles },
        ]}
      />
      <Membres
        membres={membres}
        roles={roles.filter((r) => peutDonnerRole(a, r)).map((r) => ({ id: r.id, nom: r.nom }))}
        tousPermis={a.perimetre === "tous"}
      />
    </>
  );
}

export const instant = false;
