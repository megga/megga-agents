import { Refus } from "@/lib/agents";
import { atelier } from "@/lib/admin/atelier";
import { estObjet } from "@/lib/admin/champs";
import { garde } from "@/lib/admin/garde";
import { TA } from "@/lib/admin/textes";
import { numeroVersion } from "@/lib/admin/versions";

// Mettre une version en service, revenir à une version publiée, ou forcer un brouillon jamais essayé ({ forcer? }) :
// clients.piloter, qu'un externe n'a jamais. La réponse de l'atelier telle quelle ; le journal note la version et forcer.
type P = { id: string; numero: string };

export const POST = garde(
  {
    droit: "clients.piloter",
    client: (p: P) => p.id,
    action: "clients.activer",
    detail: (corps, p) => ({ version: numeroVersion(p.numero), forcer: estObjet(corps) && corps.forcer === true }),
  },
  async ({ params, corps }) => {
    const n = numeroVersion(params.numero);
    if (n === null) throw new Refus(400, TA.numeroInvalide);
    return atelier.activer(params.id, n, estObjet(corps) && Object.hasOwn(corps, "forcer") ? { forcer: corps.forcer } : {});
  },
);
