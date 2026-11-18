import { notFound } from "next/navigation";
import { Bandeau } from "@/components/admin/erreurs";
import { titreBloc } from "@/components/admin/formulaire";
import { EcartInstallation, etatInstallation, Pastille } from "@/components/admin/pastille";
import { Tableau } from "@/components/admin/tableau";
import { peut } from "@/lib/admin/acces";
import { atelier, ouRefus, RefusChamps } from "@/lib/admin/atelier";
import { estObjet } from "@/lib/admin/champs";
import { gardePage } from "@/lib/admin/garde";
import { TA } from "@/lib/admin/textes";
import { GestesInstallation } from "./installation";

// L'onglet Installation d'un client hors Cloudflare (clients.voir) : son dernier relevé, le pilotage, l'écart, les vingt
// derniers ordres et le journal du pilotage ; avec installations.gerer, enregistrer ou révoquer sa clé, proposer une image.
// Un client servi par la porte n'a pas d'installation : la phrase de l'atelier (409).

type Objet = Record<string, unknown>;
const liste = (v: unknown): Objet[] => (Array.isArray(v) ? v.filter(estObjet) : []);
const moment = (v: unknown) => (typeof v === "number" ? TA.moment(v) : TA.inconnu);
const texte = (v: unknown) => (typeof v === "string" && v ? v : TA.inconnu);
const ouiNon = (v: unknown) => (v === true ? TA.oui : v === false ? TA.non : TA.inconnu);
const etatPilotage = (v: unknown) => (typeof v === "string" ? (TA.etatsPilotage[v] ?? v) : TA.inconnu);

function agent(a: unknown): string {
  if (!estObjet(a) || a.ok === undefined) return TA.inconnu;
  return a.ok ? TA.agentRepond(texte(a.version)) : TA.agentEnPanne(texte(a.erreur));
}

function licence(a: unknown): string {
  const l = estObjet(a) && estObjet(a.licence) ? a.licence : null;
  if (!l) return TA.inconnu;
  const etat = typeof l.etat === "string" ? (TA.etatsLicence[l.etat] ?? l.etat) : TA.inconnu;
  return typeof l.jusqu_au === "string" ? TA.licenceJusqua(etat, TA.jour(l.jusqu_au)) : etat;
}

function versionServie(c: unknown): string {
  if (!estObjet(c)) return TA.inconnu;
  return c.source === "pilotage" && typeof c.version === "number" ? TA.versionNumero(c.version) : TA.sonFichier;
}

/** L'installation d'après son dernier relevé, en une liste de définitions. */
function EtatInstallation({ i }: { i: Objet }) {
  const e = etatInstallation(i);
  const lignes: [string, React.ReactNode][] = [
    [TA.dernierReleve, <span key="r" className="flex flex-wrap items-center gap-2">{typeof i.releve === "number" ? TA.moment(i.releve) : TA.jamais}
      <Pastille etat={e.etat} texte={e.texte} /></span>],
    [TA.pilotage, typeof i.pilotage === "string" ? (TA.modesPilotage[i.pilotage] ?? i.pilotage) : TA.inconnu],
    [TA.accordClient, ouiNon(i.accord)],
    [TA.misesAJour, i.mises_a_jour === true ? TA.misesAJourPilote : i.mises_a_jour === false ? TA.misesAJourClient : TA.inconnu],
    [TA.agentInstallation, agent(i.agent)],
    [TA.versionServie, versionServie(i.configuration)],
    [TA.ecart, <EcartInstallation key="e" ecart={i.ecart} />],
    [TA.licence, licence(i.agent)],
    [TA.empreinteCle, texte(i.cle)],
    [TA.enregistreeLe, moment(i.enregistree)],
    ...(i.revoquee != null ? [[TA.revoqueeLe, moment(i.revoquee)] as [string, React.ReactNode]] : []),
  ];
  return (
    <dl className="trait m-0 grid grid-cols-1 gap-x-6 gap-y-2.5 rounded-2xl bg-bg px-5 py-4 min-[900px]:grid-cols-2">
      {lignes.map(([titre, valeur]) => (
        <div key={titre} className="flex min-w-0 flex-col gap-0.5">
          <dt className="text-[11.5px] font-bold tracking-[.06em] text-faint uppercase">{titre}</dt>
          <dd className="m-0 text-[14px] wrap-anywhere">{valeur}</dd>
        </div>
      ))}
    </dl>
  );
}

export default async function PageInstallation({ params }: PageProps<"/admin/clients/[id]/installation">) {
  const { id } = await params;
  const a = await gardePage("clients.voir", id);
  const r = await ouRefus(atelier.installation(id));
  if (r instanceof RefusChamps) {
    if (r.statut === 404) notFound();
    return <Bandeau etat={r.statut === 409 ? "faint" : "accent"}>{r.message}</Bandeau>;
  }
  const i = estObjet(r.installation) ? r.installation : null;
  return (
    <>
      <h2 className={titreBloc}>{TA.lInstallation}</h2>
      {i ? <EtatInstallation i={i} /> : <Bandeau etat="faint">{TA.aucuneInstallation}</Bandeau>}
      {peut(a, "installations.gerer") && <GestesInstallation id={id} revocable={!!i && i.revoquee == null} />}
      <h2 className={titreBloc}>{TA.ordres}</h2>
      <Tableau
        colonnes={[TA.ordre, TA.genre, TA.version, TA.etat, TA.detail, TA.deposeLe, TA.majLe, TA.expireLe]}
        vide={TA.videOrdres}
        replier={[1, 2, 3, 4, 5, 6, 7]}
        lignes={liste(r.ordres).map((o) => [
          <b key="numero" className="font-bold tabular-nums">{texte(String(o.numero ?? ""))}</b>,
          <span key="genre">{typeof o.genre === "string" ? (TA.genresOrdre[o.genre] ?? o.genre) : TA.inconnu}</span>,
          <span key="version" className="wrap-anywhere">{o.version != null ? String(o.version) : TA.inconnu}</span>,
          <span key="etat">{etatPilotage(o.etat)}</span>,
          <span key="detail" className="text-[13px] wrap-anywhere text-muted-ink">{typeof o.detail === "string" ? o.detail : ""}</span>,
          <span key="cree" className="whitespace-nowrap">{moment(o.cree)}</span>,
          <span key="maj" className="whitespace-nowrap">{moment(o.maj)}</span>,
          <span key="expire" className="whitespace-nowrap">{moment(o.expire)}</span>,
        ])}
      />
      <h2 className={titreBloc}>{TA.journalPilotage}</h2>
      <Tableau
        colonnes={[TA.quand, TA.evenement, TA.ordre, TA.detail]}
        vide={TA.videJournalPilotage}
        replier={[2, 3]}
        lignes={liste(r.journal).map((l) => [
          <span key="quand" className="whitespace-nowrap">{moment(l.quand)}</span>,
          <b key="evenement" className="font-bold">{etatPilotage(l.evenement)}</b>,
          <span key="ordre" className="tabular-nums">{typeof l.numero === "number" ? l.numero : TA.inconnu}</span>,
          <span key="detail" className="text-[13px] wrap-anywhere text-muted-ink">{typeof l.detail === "string" ? l.detail : ""}</span>,
        ])}
      />
    </>
  );
}

export const instant = false;
