import { Bandeau } from "@/components/admin/erreurs";
import type { Etat } from "@/components/admin/pastille";
import { filtrerClients } from "@/lib/admin/acces";
import { atelier, ouRefus, RefusChamps, type ClientAtelier } from "@/lib/admin/atelier";
import { gardePage } from "@/lib/admin/garde";
import { etatClient } from "@/lib/admin/suivi";
import { TA } from "@/lib/admin/textes";
import { Clients, type LigneClient } from "./clients";

// Les clients du moteur : la liste de l'atelier, bornée au périmètre ici, côté serveur, avant d'arriver au navigateur.

/** L'installation d'un client hors Cloudflare, d'après son dernier relevé ; aucune pour les autres. */
function installationDe(c: ClientAtelier): { etat: Etat; texte: string } {
  const i = c.installation;
  if (!i) return { etat: "faint", texte: TA.sansInstallation };
  if (i.revoquee != null) return { etat: "accent", texte: TA.installationRevoquee };
  if (i.silencieuse) return { etat: "warn", texte: TA.installationSilencieuse };
  return { etat: "ok", texte: TA.installationRelevee };
}

export default async function PageClients() {
  const a = await gardePage("clients.voir");
  const r = await ouRefus(atelier.clients());
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
    installation: installationDe(c),
  }));
  return (
    <>
      {titre}
      {!r.porte && <Bandeau etat="warn">{TA.porteMuette}</Bandeau>}
      <Clients lignes={lignes} />
    </>
  );
}

export const instant = false;
