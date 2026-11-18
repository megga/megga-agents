import { Bandeau } from "@/components/admin/erreurs";
import { etatInstallation } from "@/components/admin/pastille";
import { filtrerClients, peutCreerClient } from "@/lib/admin/acces";
import { atelier, ouRefus, RefusChamps } from "@/lib/admin/atelier";
import { gardePage } from "@/lib/admin/garde";
import { etatClient } from "@/lib/admin/suivi";
import { TA } from "@/lib/admin/textes";
import { Clients, type Creation, type LigneClient } from "./clients";

// Les clients du moteur : la liste de l'atelier, bornée au périmètre ici, côté serveur, avant d'arriver au navigateur.
// « Nouveau client » pour qui peut créer (clients.creer et le périmètre de tous les clients) : les modèles et les zones.

/**
 * Ce que le formulaire du nouveau client propose ; rien si le membre ne crée pas. Les modèles ou les zones illisibles : seule
 * la configuration collée est offerte, avec un avertissement qui dit pourquoi.
 */
async function creation(peut: boolean): Promise<Creation | null> {
  if (!peut) return null;
  const [g, c] = await Promise.all([ouRefus(atelier.gabarits()), ouRefus(atelier.catalogue())]);
  if (g instanceof RefusChamps || c instanceof RefusChamps) return { gabarits: [], zones: [], avertissement: TA.modelesIllisibles };
  return { gabarits: g.gabarits.map((x) => ({ id: x.id, titre: x.titre })), zones: c.zones, avertissement: null };
}

export default async function PageClients() {
  const a = await gardePage("clients.voir");
  const [r, nouveau] = await Promise.all([ouRefus(atelier.clients()), creation(peutCreerClient(a))]);
  const titre = <h1 className="m-0 text-[26px] font-extrabold tracking-[-0.02em]">{TA.clients}</h1>;
  if (r instanceof RefusChamps) {
    return (
      <>
        {titre}
        <Bandeau>{r.message}</Bandeau>
      </>
    );
  }
  const lignes: LigneClient[] = filtrerClients(a, r.clients).map((c) => ({
    id: c.id,
    entreprise: c.entreprise,
    agent: c.nom_agent,
    version: TA.versionsClient(c.version_en_service, c.derniere_version),
    etat: etatClient(c),
    installation: etatInstallation(c.installation),
  }));
  return (
    <>
      {titre}
      {!r.porte && <Bandeau etat="warn">{TA.porteMuette}</Bandeau>}
      <Clients lignes={lignes} creation={nouveau} />
    </>
  );
}

export const instant = false;
