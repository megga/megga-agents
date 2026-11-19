import { garde } from "@/lib/admin/garde";
import { modifierRole, retirerRole } from "@/lib/admin/roles";

// Un rôle : le modifier ; le retirer (204) s'il n'est ni porté ni nommé par une invitation en attente.
const cible = (p: { id: string }) => `role:${p.id}`;

export const PATCH = garde({ droit: "equipe.gerer", action: "roles.modifier", cible }, async ({ acces, params, corps, db }) => ({
  role: await modifierRole(db, acces, params.id, corps),
}));

export const DELETE = garde({ droit: "equipe.gerer", action: "roles.retirer", cible }, async ({ acces, params, db }) => {
  await retirerRole(db, acces, params.id);
});
