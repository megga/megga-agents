import { atelier } from "@/lib/admin/atelier";
import { corpsPourAtelier } from "@/lib/admin/externes";
import { garde } from "@/lib/admin/garde";
import { detailVersion } from "@/lib/admin/versions";

// Valider des changements : la configuration qui en résulterait ({ base, config, manques }), sans rien garder, ni à l'atelier
// ni au journal (aucune action) ; detail dit tout de même ce qui en serait noté, pour que le corps entier ne le soit jamais.
// Le corps d'un externe est filtré comme pour préparer (réglages simples seulement, d'après la version en service).
export const POST = garde({ droit: "versions.preparer", client: (p: { id: string }) => p.id, detail: (corps) => detailVersion(corps) },
  async ({ acces, params, corps, preciser }) => {
    const { corps: c, base } = await corpsPourAtelier(acces, params.id, corps, atelier);
    preciser(detailVersion(corps, base));
    return atelier.valider(params.id, c);
  });
