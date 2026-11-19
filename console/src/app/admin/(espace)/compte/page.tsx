import { cadre, titreBloc } from "@/components/admin/formulaire";
import { Pastille } from "@/components/admin/pastille";
import { Tableau } from "@/components/admin/tableau";
import { appareilsDe } from "@/lib/admin/compte";
import { gardePage } from "@/lib/admin/garde";
import { TA } from "@/lib/admin/textes";
import { session } from "@/lib/auth";
import { pret } from "@/lib/base";
import { navigateurDe } from "@/lib/navigateur";
import { T } from "@/lib/textes";
import { AutresAppareils, MotDePasseCompte, NomCompte, PhotoCompte } from "./compte";

// Mon compte : ouvert à tout membre en cours, sans droit particulier. Sa photo, son nom, son mot de passe, ses appareils
// connectés ; le courriel se lit sans se changer. Chaque geste passe par une route de /api/admin/compte, notée au journal.
export default async function PageMonCompte() {
  const a = await gardePage();
  const s = await session();
  const db = await pret();
  const u = await db.un<{ name: string | null; email: string; image: string | null }>('SELECT name, email, image FROM "user" WHERE id = ?', a.utilisateur);
  const nom = u?.name ?? a.nom;
  const courriel = u?.email ?? a.courriel;
  const appareils = await appareilsDe(db, a.utilisateur, s?.session.id ?? null);
  return (
    <>
      <header className="flex min-w-0 flex-col gap-1.5">
        <h1 className="m-0 text-[26px] font-extrabold tracking-[-0.02em]">{T.monCompte}</h1>
        <p className="m-0 text-[14px] text-muted-ink">{TA.monCompteSousTitre}</p>
      </header>
      <div className="grid gap-5 min-[1000px]:grid-cols-2">
        <PhotoCompte nom={nom || courriel} image={u?.image ?? null} />
        <NomCompte nom={nom} courriel={courriel} />
      </div>
      <MotDePasseCompte />
      <section className={cadre}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className={titreBloc}>{TA.appareilsConnectes}</h2>
          {appareils.some((x) => !x.courant) && <AutresAppareils />}
        </div>
        <Tableau
          colonnes={[TA.navigateur, TA.ouverteLe, TA.derniereActivite]}
          vide={TA.videSessions}
          replier={[1, 2]}
          lignes={appareils.map((x) => [
            <span key="navigateur" className="flex flex-wrap items-center gap-2">
              <b className="font-bold">{navigateurDe(x.agent)}</b>
              {x.courant && <Pastille etat="ok" texte={TA.cetAppareil} />}
            </span>,
            <span key="ouverte" className="whitespace-nowrap">{TA.instant(x.ouverteLe)}</span>,
            <span key="vue" className="whitespace-nowrap">{TA.instant(x.vueLe)}</span>,
          ])}
        />
      </section>
    </>
  );
}

// Propre à chaque membre : rendue à la demande, après la vérification de la session.
export const instant = false;
