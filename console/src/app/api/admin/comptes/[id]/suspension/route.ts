import { adaptateurComptes, detailSuspension, reactiver, suspendre } from "@/lib/admin/comptes";
import { garde } from "@/lib/admin/garde";

// Suspendre un compte de la console ({ motif }) ou le réactiver. Le compte d'un membre, superadmin seulement ; ni celui d'un
// superadmin, ni le sien (peutAgirSur, dans comptes.ts). Le journal garde le motif, coupé ; une réactivation n'y note rien.
const cible = (p: { id: string }) => `compte:${p.id}`;

export const POST = garde({ droit: "comptes.gerer", action: "comptes.suspendu", cible, detail: detailSuspension },
  async ({ acces, params, corps, db }) => {
    await suspendre(db, acces, params.id, corps); // le bannissement et ses sessions effacées, ensemble
    return { ok: true };
  });

export const DELETE = garde({ droit: "comptes.gerer", action: "comptes.reactive", cible, detail: () => null }, async ({ acces, params, db }) => {
  await reactiver(db, acces, params.id, await adaptateurComptes());
  return { ok: true };
});
