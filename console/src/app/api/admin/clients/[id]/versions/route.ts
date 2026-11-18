import { atelier } from "@/lib/admin/atelier";
import { corpsPourAtelier } from "@/lib/admin/externes";
import { garde } from "@/lib/admin/garde";
import { numeroVersion } from "@/lib/admin/versions";

// Préparer un brouillon : d'après un modèle par métier ({ gabarit, nom_agent?, base? }, un membre interne seulement), ou
// d'après des changements ({ base?, changements }, filtrés pour un externe). La réponse de l'atelier, 201.
const estObjet = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);

/** Ce que le journal garde : la base, les noms des réglages changés ou le modèle demandé ; jamais leurs valeurs. */
function detail(corps: unknown) {
  if (!estObjet(corps)) return null;
  return {
    base: typeof corps.base === "number" ? numeroVersion(corps.base) : null,
    ...(typeof corps.gabarit === "string" ? { gabarit: corps.gabarit } : {}),
    ...(estObjet(corps.changements) ? { changements: Object.keys(corps.changements).sort() } : {}),
  };
}

export const POST = garde({ droit: "versions.preparer", client: (p: { id: string }) => p.id, action: "versions.preparer", detail },
  async ({ acces, params, corps }) => {
    const c = await corpsPourAtelier(acces, params.id, corps, atelier);
    const v = !acces.externe && Object.hasOwn(c, "gabarit") ? await atelier.depuisGabarit(params.id, c) : await atelier.ajouterVersion(params.id, c);
    return Response.json(v, { status: 201 });
  });
