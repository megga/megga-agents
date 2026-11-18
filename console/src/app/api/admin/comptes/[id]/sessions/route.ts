import { adaptateurComptes, deconnecter } from "@/lib/admin/comptes";
import { garde } from "@/lib/admin/garde";

// Déconnecter partout un compte de la console : toutes ses sessions se ferment, il peut se reconnecter. Mêmes règles que la
// suspension (peutAgirSur) ; rien du corps au journal.
export const DELETE = garde(
  { droit: "comptes.gerer", action: "comptes.deconnecte", cible: (p: { id: string }) => `compte:${p.id}`, detail: () => null },
  async ({ acces, params, db }) => {
    await deconnecter(db, acces, params.id, await adaptateurComptes());
    return { ok: true };
  },
);
