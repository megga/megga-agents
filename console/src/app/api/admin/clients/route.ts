import { Refus } from "@/lib/agents";
import { ID_CLIENT, peutCreerClient } from "@/lib/admin/acces";
import { atelier } from "@/lib/admin/atelier";
import { garde } from "@/lib/admin/garde";
import { TA } from "@/lib/admin/textes";

// Créer un client : d'après un modèle par métier ({ gabarit, client: { id, entreprise, zone, numero_id? }, nom_agent }), ou
// d'une configuration entière ({ config }). clients.creer, et le périmètre de tous les clients : limité à une liste, le client
// naîtrait hors du sien. La réponse de l'atelier, 201 ; le journal ne garde que son identité, jamais la configuration collée.
const estObjet = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);
const texte = (v: unknown) => (typeof v === "string" ? v : null);

/** L'identité du client à créer : celle du modèle par métier (client), sinon celle de la configuration collée. */
function identite(corps: unknown) {
  if (!estObjet(corps)) return { id: null, entreprise: null, zone: null, gabarit: null };
  const source = corps.gabarit != null ? corps.client : corps.config;
  const s = estObjet(source) ? source : {};
  return { id: texte(s.id), entreprise: texte(s.entreprise), zone: texte(s.zone), gabarit: texte(corps.gabarit) };
}

export const POST = garde(
  {
    droit: "clients.creer",
    action: "clients.creer",
    cible: (_, corps) => {
      const id = identite(corps).id;
      return id !== null && ID_CLIENT.test(id) ? `client:${id}` : null;
    },
    detail: identite,
  },
  async ({ acces, corps }) => {
    if (!peutCreerClient(acces)) throw new Refus(403, TA.creationPerimetre);
    if (!estObjet(corps)) throw new Refus(400, TA.corpsObjet);
    const c = corps.gabarit != null ? { gabarit: corps.gabarit, client: corps.client, nom_agent: corps.nom_agent } : { config: corps.config };
    return Response.json(await atelier.creerClient(c), { status: 201 });
  },
);
