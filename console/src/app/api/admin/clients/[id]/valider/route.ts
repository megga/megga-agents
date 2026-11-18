import { atelier } from "@/lib/admin/atelier";
import { corpsPourAtelier } from "@/lib/admin/externes";
import { garde } from "@/lib/admin/garde";

// Valider des changements : la configuration qui en résulterait ({ base, config, manques }), sans rien garder, ni à l'atelier
// ni au journal. Le corps d'un externe est filtré comme pour préparer (réglages simples seulement).
export const POST = garde({ droit: "versions.preparer", client: (p: { id: string }) => p.id }, async ({ acces, params, corps }) =>
  atelier.valider(params.id, await corpsPourAtelier(acces, params.id, corps, atelier)),
);
