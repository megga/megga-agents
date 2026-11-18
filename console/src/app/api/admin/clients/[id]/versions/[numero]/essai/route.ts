import { Refus } from "@/lib/agents";
import { atelier } from "@/lib/admin/atelier";
import { estObjet } from "@/lib/admin/champs";
import { garde } from "@/lib/admin/garde";
import { TA } from "@/lib/admin/textes";
import { numeroVersion } from "@/lib/admin/versions";

// Essayer une version : { message, conversation?, role? } part à l'atelier, qui fait répondre l'agent de cette version, hors
// WhatsApp ; la réponse est la sienne. Le journal ne garde que la version et le rôle, jamais le message ni la réponse.
type P = { id: string; numero: string };

export const POST = garde(
  {
    droit: "versions.preparer",
    client: (p: P) => p.id,
    action: "versions.essayer",
    detail: (corps, p) => ({ version: numeroVersion(p.numero), role: estObjet(corps) && typeof corps.role === "string" ? corps.role : null }),
  },
  async ({ params, corps }) => {
    const n = numeroVersion(params.numero);
    if (n === null) throw new Refus(400, TA.numeroInvalide);
    if (!estObjet(corps)) throw new Refus(400, TA.corpsObjet);
    const { message, conversation, role } = corps;
    return atelier.essai(params.id, n, { message, conversation, role });
  },
);
