import { garde } from "@/lib/admin/garde";
import { creerRole } from "@/lib/admin/roles";

// Créer un rôle : un nom, une description, des droits cochés parmi les treize.
export const POST = garde({ droit: "equipe.gerer", action: "roles.creer" }, async ({ acces, corps, db }) =>
  Response.json({ role: creerRole(db, acces, corps) }, { status: 201 }),
);
