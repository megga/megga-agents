import { T } from "@/lib/textes";
import { epingler, Refus } from "@/lib/agents";
import { sessionDe } from "@/lib/auth";
import { pret } from "@/lib/base";

export async function PATCH(requete: Request, { params }: { params: Promise<{ id: string }> }) {
  const s = await sessionDe(requete);
  if (!s) return Response.json({ erreur: T.connectezVous }, { status: 401 });
  const { id } = await params;
  const corps = (await requete.json().catch(() => ({}))) as { epingle?: unknown };
  try {
    return Response.json({ agent: await epingler(await pret(), s.user.id, id, corps.epingle === true) });
  } catch (e) {
    if (e instanceof Refus) return Response.json({ erreur: e.message }, { status: e.statut });
    throw e;
  }
}
