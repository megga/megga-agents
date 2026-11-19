import { garde } from "@/lib/admin/garde";
import { modifierMembre, retirerMembre } from "@/lib/admin/membres";

// Un membre de l'équipe : changer son rôle, son périmètre ou sa fin d'accès ; le retirer (204).
const cible = (p: { id: string }) => `membre:${p.id}`;

export const PATCH = garde({ droit: "equipe.gerer", action: "membres.modifier", cible }, async ({ acces, params, corps, db }) => ({
  membre: await modifierMembre(db, acces, params.id, corps),
}));

export const DELETE = garde({ droit: "equipe.gerer", action: "membres.retirer", cible }, async ({ acces, params, db }) => {
  await retirerMembre(db, acces, params.id);
});
