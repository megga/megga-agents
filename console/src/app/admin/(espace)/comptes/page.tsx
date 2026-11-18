import Link from "next/link";
import { Pastille } from "@/components/admin/pastille";
import { Tableau } from "@/components/admin/tableau";
import { listerComptes } from "@/lib/admin/comptes";
import { gardePage } from "@/lib/admin/garde";
import { TA } from "@/lib/admin/textes";
import { base } from "@/lib/base";

// Les comptes de la console (comptes.voir, jamais un externe) : entreprise et courriel, inscription, dernière connexion, agents,
// messages sur 30 jours, état, membre de l'admin ou non. Lu ici, côté serveur ; rien ne part au navigateur que ce tableau.
// Dans un cadre étroit, les colonnes secondaires se replient sous le compte.
export default async function PageComptes() {
  await gardePage("comptes.voir");
  const comptes = listerComptes(base());
  return (
    <>
      <h1 className="m-0 text-[26px] font-extrabold tracking-[-0.02em]">{TA.comptes}</h1>
      <Tableau
        colonnes={[TA.compte, TA.inscritLe, TA.derniereConnexion, TA.agents, TA.messages30j, TA.etat, TA.membreAdmin]}
        vide={TA.videComptes}
        replier={[1, 2, 3, 4, 5, 6]}
        lignes={comptes.map((c) => [
          <div key="compte" className="flex min-w-0 flex-col">
            <Link href={`/admin/comptes/${encodeURIComponent(c.id)}`} className="font-bold wrap-anywhere text-ink hover:underline">
              {c.entreprise || c.courriel}
            </Link>
            <span className="text-[13px] wrap-anywhere text-muted-ink">{c.courriel}</span>
          </div>,
          <span key="inscrit" className="whitespace-nowrap">{TA.instant(c.inscritLe)}</span>,
          <span key="connexion" className="whitespace-nowrap">{c.derniereConnexion ? TA.instant(c.derniereConnexion) : TA.pasEncoreNotee}</span>,
          <span key="agents" className="tabular-nums">{TA.nombre(c.agents)}</span>,
          <span key="messages" className="tabular-nums">{TA.nombre(c.messages30j)}</span>,
          c.suspendu ? <Pastille key="etat" etat="accent" texte={TA.suspendu} /> : <Pastille key="etat" etat="ok" texte={TA.actif} />,
          <span key="membre">{c.membre ? TA.oui : TA.non}</span>,
        ])}
      />
    </>
  );
}

export const instant = false;
