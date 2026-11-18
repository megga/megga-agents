import { atelier } from "@/lib/admin/atelier";
import { garde } from "@/lib/admin/garde";

// Une clé pour un logiciel du client ({ logiciel, par_minute? }) : l'atelier la tire et la rend une fois (201), l'écran la
// montre une fois. Seuls le logiciel et le débit partent, et le journal ne garde qu'eux, jamais la clé. L'atelier refuse
// (409) un client hors Cloudflare ou jamais mis en service : sa phrase est rendue telle quelle.
const lu = (corps: unknown) => {
  const c = (corps && typeof corps === "object" ? corps : {}) as { logiciel?: unknown; par_minute?: unknown };
  return { logiciel: c.logiciel, par_minute: c.par_minute };
};

export const POST = garde(
  {
    droit: "acces.gerer",
    client: (p: { id: string }) => p.id,
    action: "acces.cle_creee",
    detail: (corps) => {
      const { logiciel, par_minute } = lu(corps);
      return { logiciel: typeof logiciel === "string" ? logiciel : null, par_minute: typeof par_minute === "number" ? par_minute : null };
    },
  },
  async ({ params, corps }) => Response.json(await atelier.creerCle(params.id, lu(corps)), { status: 201 }),
);
