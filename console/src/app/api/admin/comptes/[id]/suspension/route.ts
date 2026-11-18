import { adaptateurComptes, detailSuspension, reactiver, suspendre } from "@/lib/admin/comptes";
import { garde } from "@/lib/admin/garde";
import { TA } from "@/lib/admin/textes";

// Suspendre un compte de la console ({ motif }) ou le réactiver. Le compte d'un membre, superadmin seulement ; ni celui d'un
// superadmin, ni le sien (peutAgirSur, dans comptes.ts). Le journal garde le motif, coupé ; une réactivation n'y note rien.
// Suspendu mais ses sessions restent : c'est fait (200, noté ok), avec un avertissement, et le journal le note à côté du motif.
const cible = (p: { id: string }) => `compte:${p.id}`;

export const POST = garde({ droit: "comptes.gerer", action: "comptes.suspendu", cible, detail: detailSuspension },
  async ({ acces, params, corps, db, preciser }) => {
    const { sessionsRestent } = await suspendre(db, acces, params.id, corps, await adaptateurComptes());
    if (!sessionsRestent) return { ok: true };
    preciser({ ...detailSuspension(corps), sessions: "restent" });
    return { sessionsRestent: true, avertissement: TA.sessionsRestent };
  });

export const DELETE = garde({ droit: "comptes.gerer", action: "comptes.reactive", cible, detail: () => null }, async ({ acces, params, db }) => {
  await reactiver(db, acces, params.id, await adaptateurComptes());
  return { ok: true };
});
