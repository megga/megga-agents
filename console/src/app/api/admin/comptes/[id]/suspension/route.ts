import { adaptateurComptes, detailSuspension, reactiver, SessionsRestent, suspendre } from "@/lib/admin/comptes";
import { garde } from "@/lib/admin/garde";

// Suspendre un compte de la console ({ motif }) ou le réactiver. Le compte d'un membre, superadmin seulement ; ni celui d'un
// superadmin, ni le sien (peutAgirSur, dans comptes.ts). Le journal garde le motif, coupé ; une réactivation n'y note rien.
// Suspendu mais ses sessions restent : la phrase de SessionsRestent, et le journal le note à côté du motif.
const cible = (p: { id: string }) => `compte:${p.id}`;

export const POST = garde({ droit: "comptes.gerer", action: "comptes.suspendu", cible, detail: detailSuspension },
  async ({ acces, params, corps, db, preciser }) => {
    try {
      await suspendre(db, acces, params.id, corps, await adaptateurComptes());
    } catch (e) {
      if (e instanceof SessionsRestent) preciser({ ...detailSuspension(corps), sessions: "restent" });
      throw e;
    }
    return { ok: true };
  });

export const DELETE = garde({ droit: "comptes.gerer", action: "comptes.reactive", cible, detail: () => null }, async ({ acces, params, db }) => {
  await reactiver(db, acces, params.id, await adaptateurComptes());
  return { ok: true };
});
