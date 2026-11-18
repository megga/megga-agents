import Link from "next/link";
import { Bandeau } from "@/components/admin/erreurs";
import { EcartInstallation, etatInstallation, Pastille } from "@/components/admin/pastille";
import { Tableau } from "@/components/admin/tableau";
import { filtrerClients } from "@/lib/admin/acces";
import { atelier, ouRefus, RefusChamps } from "@/lib/admin/atelier";
import { gardePage } from "@/lib/admin/garde";
import { TA } from "@/lib/admin/textes";

// Les installations hors Cloudflare (clients.voir) : celles des clients du périmètre, bornées ici avant tout affichage. Pour
// chacune : le dernier relevé (silencieuse au-delà de 5 minutes), le pilotage, les mises à jour, l'écart. Un bandeau quand
// l'atelier n'a pas sa clé de pilotage (aucun ordre ne peut partir).

type Installation = Record<string, unknown> & { client: string };

export default async function PageInstallations() {
  const a = await gardePage("clients.voir");
  const titre = <h1 className="m-0 text-[26px] font-extrabold tracking-[-0.02em]">{TA.installations}</h1>;
  const [r, clients] = await Promise.all([ouRefus(atelier.installations()), ouRefus(atelier.clients())]);
  if (r instanceof RefusChamps) {
    return (
      <>
        {titre}
        <Bandeau>{r.message}</Bandeau>
      </>
    );
  }
  const noms = new Map(clients instanceof RefusChamps ? [] : clients.clients.map((c) => [c.id, c.entreprise]));
  const visibles = filtrerClients(a, r.installations.map((i): Installation & { id: string } => ({ ...i, id: i.client })));
  const pilotage = (p: unknown) => (typeof p === "string" ? (TA.modesPilotage[p] ?? p) : TA.inconnu);
  const misesAJour = (m: unknown) => (m === true ? TA.misesAJourPilote : m === false ? TA.misesAJourClient : TA.inconnu);
  return (
    <>
      {titre}
      {!r.cle_pilotage && <Bandeau etat="warn">{TA.sansClePilotage}</Bandeau>}
      <Tableau
        colonnes={[TA.client, TA.dernierReleve, TA.etat, TA.pilotage, TA.misesAJour, TA.ecart]}
        vide={TA.videInstallations}
        replier={[1, 2, 3, 4, 5]}
        lignes={visibles.map((i) => {
          const e = etatInstallation(i);
          return [
            <Link key="client" href={`/admin/clients/${encodeURIComponent(i.id)}/installation`} className="font-bold text-ink hover:underline">
              {noms.get(i.id) || i.id}
            </Link>,
            <span key="releve" className="whitespace-nowrap">{typeof i.releve === "number" ? TA.moment(i.releve) : TA.jamais}</span>,
            <Pastille key="etat" etat={e.etat} texte={e.texte} />,
            <span key="pilotage">{pilotage(i.pilotage)}</span>,
            <span key="maj">{misesAJour(i.mises_a_jour)}</span>,
            <EcartInstallation key="ecart" ecart={i.ecart} />,
          ];
        })}
      />
    </>
  );
}

export const instant = false;
