import { atelier } from "@/lib/admin/atelier";
import { corpsPourAtelier } from "@/lib/admin/externes";
import { garde } from "@/lib/admin/garde";
import { detailVersion } from "@/lib/admin/versions";

// Préparer un brouillon : d'après un modèle par métier ({ gabarit, nom_agent?, base? }, un membre interne seulement), ou
// d'après des changements ({ base?, changements }, filtrés pour un externe). La base part toujours nommée (corpsPourAtelier) ;
// la réponse de l'atelier, 201. Le journal garde la base réellement envoyée (preciser), les noms des réglages changés ou le
// modèle, jamais leurs valeurs ; refusé avant tout envoi, la base que le corps nomme.
export const POST = garde({ droit: "versions.preparer", client: (p: { id: string }) => p.id, action: "versions.preparer",
  detail: (corps) => detailVersion(corps) },
  async ({ acces, params, corps, preciser }) => {
    const { corps: c, base } = await corpsPourAtelier(acces, params.id, corps, atelier);
    preciser(detailVersion(corps, base));
    const v = !acces.externe && Object.hasOwn(c, "gabarit") ? await atelier.depuisGabarit(params.id, c) : await atelier.ajouterVersion(params.id, c);
    return Response.json(v, { status: 201 });
  });
