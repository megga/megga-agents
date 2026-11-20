import { Bandeau } from "@/components/admin/erreurs";
import { Onglets } from "@/components/admin/onglets";
import { Tableau } from "@/components/admin/tableau";
import { filtrerClients, peut, peutReglerForfaits } from "@/lib/admin/acces";
import { atelier, ouRefus, RefusChamps } from "@/lib/admin/atelier";
import { gardePage } from "@/lib/admin/garde";
import { ONGLETS_PAYANTS } from "@/lib/admin/payants";
import { TA } from "@/lib/admin/textes";
import { FormAbonnement, FormRecharge } from "./abonnement";
import { FormCatalogue } from "./catalogue";

// Les forfaits (couts.voir pour les lire) : le catalogue se règle avec tarifs.regler sur un périmètre complet ; l'abonnement
// d'un client et ses recharges hors Stripe, avec tarifs.regler, pour les clients du périmètre.

export default async function PageForfaits() {
  const a = await gardePage("couts.voir");
  const titre = <h1 className="m-0 text-[26px] font-extrabold tracking-[-0.02em]">{TA.clientsPayants}</h1>;
  const [v, liste] = await Promise.all([ouRefus(atelier.payants()), ouRefus(atelier.clients())]);
  const tete = (
    <>
      {titre}
      <Onglets onglets={ONGLETS_PAYANTS} actif="/admin/payants/forfaits" />
    </>
  );
  if (v instanceof RefusChamps) {
    return (
      <>
        {tete}
        <Bandeau>{v.message}</Bandeau>
      </>
    );
  }
  const c = v.catalogue;
  const regle = peut(a, "tarifs.regler");
  const abonnements = new Map(v.clients.map((l) => [l.client, l.abonnement]));
  const clients = liste instanceof RefusChamps ? [] : filtrerClients(a, liste.clients).map((x) => ({
    id: x.id, nom: x.entreprise || x.id, abonnement: abonnements.get(x.id) ?? null,
  }));
  return (
    <>
      {tete}
      {peutReglerForfaits(a) ? (
        <FormCatalogue catalogue={c} />
      ) : (
        <Tableau
          colonnes={[TA.forfait, TA.prixMensuel, TA.conversationsParMois, TA.remiseAnnuelle, TA.rechargeConversations, TA.rechargePrix]}
          vide={TA.aucunForfait}
          replier={[3, 4, 5]}
          lignes={c.forfaits.map((f) => [
            <b key="nom" className="font-bold">{f.nom}</b>,
            <span key="prix" className="whitespace-nowrap tabular-nums">{TA.montantEn(f.prix_mensuel, c.devise)}</span>,
            <span key="conversations" className="tabular-nums">{TA.nombre(f.conversations)}</span>,
            <span key="remise" className="tabular-nums">{TA.nombre(f.remise_annuelle)}</span>,
            <span key="rc" className="tabular-nums">{f.recharge ? TA.nombre(f.recharge.conversations) : TA.inconnu}</span>,
            <span key="rp" className="whitespace-nowrap tabular-nums">{f.recharge ? TA.montantEn(f.recharge.prix, c.devise) : TA.inconnu}</span>,
          ])}
        />
      )}
      {regle && liste instanceof RefusChamps && <Bandeau etat="warn">{liste.message}</Bandeau>}
      {regle && !c.forfaits.length && <Bandeau etat="faint">{TA.aucunForfait}</Bandeau>}
      {regle && c.forfaits.length > 0 && clients.length > 0 && (
        <>
          <FormAbonnement clients={clients} forfaits={c.forfaits} />
          <FormRecharge clients={clients} />
        </>
      )}
    </>
  );
}

export const instant = false;
