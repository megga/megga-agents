import { notFound } from "next/navigation";
import { Pastille } from "@/components/admin/pastille";
import { Tableau } from "@/components/admin/tableau";
import { Tete } from "@/components/console/tete";
import { ficheCompte, peutAgirSur } from "@/lib/admin/comptes";
import { gardePage } from "@/lib/admin/garde";
import { TA } from "@/lib/admin/textes";
import { pret } from "@/lib/base";
import { metier } from "@/lib/metiers";
import { GestesCompte } from "./compte";

// La fiche d'un compte de la console (comptes.voir) : son état, ses agents et leurs messages sur 30 jours, ses sessions
// ouvertes (l'appareil, jamais l'adresse IP). Les gestes (suspendre, réactiver, déconnecter partout) seulement avec
// comptes.gerer et la main sur ce compte (peutAgirSur) : l'écran ne propose pas un geste que la route refusera.
export default async function PageCompte({ params }: PageProps<"/admin/comptes/[id]">) {
  const { id } = await params;
  const a = await gardePage("comptes.voir");
  const db = await pret();
  const f = await ficheCompte(db, id);
  if (!f) notFound();
  const { compte: c } = f;
  const nom = c.entreprise || c.courriel;
  return (
    <>
      <header className="flex min-w-0 flex-col gap-1.5">
        <h1 className="m-0 text-[26px] font-extrabold tracking-[-0.02em] wrap-anywhere">{nom}</h1>
        <p className="m-0 flex flex-wrap gap-x-3 text-[14px] text-muted-ink">
          <span className="wrap-anywhere">{c.courriel}</span>
          <span>
            {TA.inscritLe} {TA.instant(c.inscritLe)}
          </span>
        </p>
        <span className="flex flex-wrap gap-1">
          {c.suspendu ? <Pastille etat="accent" texte={TA.suspendu} /> : <Pastille etat="ok" texte={TA.actif} />}
          {c.membre && <Pastille etat="faint" texte={TA.membreAdmin} />}
        </span>
        {c.suspendu && c.motif && <p className="m-0 text-[14px] wrap-anywhere">{TA.motifSuspension(c.motif)}</p>}
      </header>
      {(await peutAgirSur(db, a, id)) && <GestesCompte id={id} nom={nom} suspendu={c.suspendu} sessions={f.sessions.length} />}
      <h2 className="m-0 text-[17px] font-extrabold">{TA.sesAgents}</h2>
      <Tableau
        colonnes={[TA.prenom, TA.metier, TA.creeLe, TA.messages30j]}
        vide={TA.videAgentsCompte}
        replier={[1, 2, 3]}
        lignes={f.agents.map((ag) => [
          <span key="prenom" className="flex min-w-0 items-center gap-2.5">
            <Tete couleur={ag.couleur} yeux={ag.yeux} className="w-[34px] flex-none" />
            <b className="font-bold wrap-anywhere">{ag.prenom}</b>
          </span>,
          <span key="metier">{metier(ag.metier)?.nom ?? ag.metier}</span>,
          <span key="cree" className="whitespace-nowrap">{TA.instant(ag.creeLe)}</span>,
          <span key="messages" className="tabular-nums">{TA.nombre(ag.messages30j)}</span>,
        ])}
      />
      <h2 className="m-0 text-[17px] font-extrabold">{TA.sesSessions}</h2>
      <Tableau
        colonnes={[TA.ouverteLe, TA.expireLe, TA.appareil]}
        vide={TA.videSessions}
        replier={[1, 2]}
        lignes={f.sessions.map((s) => [
          <span key="ouverte" className="whitespace-nowrap">{TA.instant(s.creeLe)}</span>,
          <span key="expire" className="whitespace-nowrap">{TA.instant(s.expireLe)}</span>,
          <span key="appareil" className="text-[13px] wrap-anywhere text-muted-ink">{s.appareil ?? TA.inconnu}</span>,
        ])}
      />
    </>
  );
}

export const instant = false;
