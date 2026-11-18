import { atelier } from "@/lib/admin/atelier";
import { garde } from "@/lib/admin/garde";

// L'installation d'un client hors Cloudflare : enregistrer la clé publique qu'elle a remise ({ cle_publique }), ce qui la met
// en service, ou révoquer sa clé (plus aucun relevé accepté). Les réponses de l'atelier ; le journal ne garde pas la clé.
const regle = { droit: "installations.gerer", client: (p: { id: string }) => p.id, detail: () => null } as const;

export const PUT = garde({ ...regle, action: "installation.enregistree" }, async ({ params, corps }) =>
  atelier.enregistrerInstallation(params.id, { cle_publique: (corps as { cle_publique?: unknown } | null)?.cle_publique }),
);

export const DELETE = garde({ ...regle, action: "installation.revoquee" }, async ({ params }) => atelier.revoquerInstallation(params.id));
