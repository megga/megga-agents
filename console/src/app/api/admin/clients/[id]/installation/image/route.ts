import { atelier } from "@/lib/admin/atelier";
import { garde } from "@/lib/admin/garde";

// Proposer une image à l'installation ({ version, image }) : un ordre signé part à son prochain relevé. La console ne juge pas
// leur forme : l'atelier le fait, et sa phrase s'affiche. Seuls ces deux champs partent ; la réponse de l'atelier, 201.
const lu = (corps: unknown) => {
  const c = (corps && typeof corps === "object" ? corps : {}) as { version?: unknown; image?: unknown };
  return { version: c.version, image: c.image };
};
const texte = (v: unknown) => (typeof v === "string" ? v : null);

export const POST = garde(
  {
    droit: "installations.gerer",
    client: (p: { id: string }) => p.id,
    action: "installation.image",
    detail: (corps) => ({ version: texte(lu(corps).version), image: texte(lu(corps).image) }),
  },
  async ({ params, corps }) => Response.json(await atelier.proposerImage(params.id, lu(corps)), { status: 201 }),
);
