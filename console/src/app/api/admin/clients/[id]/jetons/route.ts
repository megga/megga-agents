import { atelier } from "@/lib/admin/atelier";
import { garde } from "@/lib/admin/garde";

// Les jetons d'un client : en créer un (201, { client, jeton }), montré une fois par l'écran ; ou les retirer tous
// ({ client, retires }). Aucune route ne les liste. Le jeton n'est que dans la réponse : le journal n'en garde rien.
const regle = { droit: "acces.gerer", client: (p: { id: string }) => p.id, detail: () => null } as const;

export const POST = garde({ ...regle, action: "acces.jeton_cree" }, async ({ params }) =>
  Response.json(await atelier.creerJeton(params.id), { status: 201 }),
);

export const DELETE = garde({ ...regle, action: "acces.jetons_retires" }, async ({ params }) => atelier.retirerJetons(params.id));
