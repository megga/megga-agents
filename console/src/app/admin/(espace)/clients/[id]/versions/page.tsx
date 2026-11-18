import Link from "next/link";
import { notFound } from "next/navigation";
import { Bandeau } from "@/components/admin/erreurs";
import { Pastille } from "@/components/admin/pastille";
import { Tableau } from "@/components/admin/tableau";
import { peut, type Acces } from "@/lib/admin/acces";
import { atelier, ouRefus, RefusChamps, type ClientAtelier, type Version } from "@/lib/admin/atelier";
import { gardePage } from "@/lib/admin/garde";
import { horsCloudflare, zoneClient } from "@/lib/admin/suivi";
import { TA } from "@/lib/admin/textes";
import { differences, lisible, numeroVersion } from "@/lib/admin/versions";
import { Essai, GestesVersion, Preparer, TableauDifferences } from "./versions";

// L'onglet Versions d'un client (clients.voir) : l'historique (brouillon ou publiée, en service, préparée par MEGGA ou par le
// client : l'atelier ne garde que ce rôle, le membre se lit au journal) ; ?v= ouvre une version : ce qui change par rapport à
// celle en service, sa configuration lisible ; avec versions.preparer, l'essayer (un brouillon) et préparer un brouillon ;
// avec clients.piloter, la mettre en service, y revenir ou forcer. Un client jamais mis en service a ses brouillons.

type Client = ClientAtelier & { config: Record<string, unknown> | null };

const estObjet = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);

function creeLe(v: Version["cree_le"]): string {
  if (typeof v === "number") return TA.moment(v);
  return typeof v === "string" ? TA.instant(v) : TA.inconnu;
}

const auteur = (a: Version["auteur"]) => (a === "megga" ? TA.parMegga : a === "client" ? TA.parLeClient : TA.inconnu);

/** Les rôles réglés d'une configuration, à proposer à l'essai ; sans rôles, tout le monde parle au même agent. */
function rolesDe(config: Record<string, unknown>): string[] {
  const roles = config.roles;
  return estObjet(roles) ? ["gestionnaire", "partenaire", "visiteur"].filter((r) => roles[r] != null) : [];
}

function PastillesVersion({ v, enService }: { v: Version; enService: number | null }) {
  return (
    <span className="flex flex-wrap gap-1">
      {v.version === enService && <Pastille etat="ok" texte={TA.enService} />}
      <Pastille etat={v.etat === "brouillon" ? "warn" : "faint"} texte={v.etat === "brouillon" ? TA.brouillon : TA.publiee} />
    </span>
  );
}

function Historique({ id, versions, enService, choisie }: { id: string; versions: Version[]; enService: number | null; choisie: number | null }) {
  const lien = (n: number) => `/admin/clients/${encodeURIComponent(id)}/versions?v=${n}`;
  return (
    <Tableau
      colonnes={[TA.version, TA.etat, TA.prepareePar, TA.base, TA.essais, TA.creeeLe]}
      vide={TA.videVersions}
      replier={[2, 3, 4, 5]}
      lignes={versions.map((v) => [
        <Link key="version" href={lien(v.version)} aria-current={v.version === choisie ? "page" : undefined}
          className="font-bold whitespace-nowrap text-ink hover:underline aria-[current=page]:underline">
          {TA.versionNumero(v.version)}
        </Link>,
        <PastillesVersion key="etat" v={v} enService={enService} />,
        <span key="auteur">{auteur(v.auteur)}</span>,
        <span key="base" className="tabular-nums">{v.base ?? TA.inconnu}</span>,
        <span key="essais" className="tabular-nums">{TA.nombre(v.essais)}</span>,
        <span key="cree" className="whitespace-nowrap">{creeLe(v.cree_le)}</span>,
      ])}
    />
  );
}

/** Une version ouverte : ses gestes, l'essai d'un brouillon, ce qui change par rapport à celle en service, sa configuration. */
function DetailVersion({ a, c, v, ordre }: { a: Acces; c: Client; v: Version; ordre: boolean }) {
  const config = v.config ?? {};
  const enService = c.version_en_service;
  return (
    <section className="trait flex min-w-0 flex-col gap-4 rounded-2xl bg-bg px-5 pt-4 pb-5">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="m-0 text-[18px] font-extrabold">{TA.versionNumero(v.version)}</h2>
        <PastillesVersion v={v} enService={enService} />
      </div>
      {peut(a, "clients.piloter") && (
        <GestesVersion key={`gestes-${v.version}`} id={c.id} version={{ numero: v.version, etat: v.etat, essais: v.essais }} enService={enService}
          ecart={c.ecart === true} ordre={ordre} />
      )}
      {peut(a, "versions.preparer") && v.etat === "brouillon" && <Essai key={`essai-${v.version}`} id={c.id} numero={v.version} roles={rolesDe(config)} />}
      {enService === null ? (
        <p className="m-0 text-[13.5px] text-muted-ink">{TA.aucuneEnService}</p>
      ) : (
        v.version !== enService && (
          <>
            <h3 className="m-0 text-[16px] font-extrabold">{TA.changeParRapport(enService)}</h3>
            <TableauDifferences liste={differences(c.config, config)} />
          </>
        )
      )}
      <details className="flex flex-col gap-2">
        <summary className="cursor-pointer text-[16px] font-extrabold">{TA.laConfiguration}</summary>
        <div className="mt-2">
          <Tableau
            colonnes={[TA.reglage, TA.valeur]}
            vide={TA.rienNeChange}
            replier={[1]}
            lignes={lisible(config).map((l) => [
              <b key="champ" className="font-bold wrap-anywhere">{l.champ}</b>,
              <span key="valeur" className="whitespace-pre-wrap wrap-anywhere">{l.valeur}</span>,
            ])}
          />
        </div>
      </details>
    </section>
  );
}

export default async function PageVersions({ params, searchParams }: PageProps<"/admin/clients/[id]/versions">) {
  const { id } = await params;
  const a = await gardePage("clients.voir", id);
  const v = (await searchParams).v;
  const choisie = numeroVersion(Array.isArray(v) ? v[0] : v);
  const preparer = peut(a, "versions.preparer");
  const [c, h, catalogue] = await Promise.all([ouRefus(atelier.client(id)), ouRefus(atelier.versions(id)), ouRefus(atelier.catalogue())]);
  if (c instanceof RefusChamps) {
    if (c.statut === 404) notFound();
    return <Bandeau>{c.message}</Bandeau>;
  }
  if (h instanceof RefusChamps) return <Bandeau>{h.message}</Bandeau>;
  const [derniere, vue, gabarits] = await Promise.all([
    c.derniere_version != null ? ouRefus(atelier.version(id, c.derniere_version)) : null,
    choisie !== null ? ouRefus(atelier.version(id, choisie)) : null,
    preparer && !a.externe ? ouRefus(atelier.gabarits()) : null,
  ]);
  const lue = derniere instanceof RefusChamps ? null : derniere;
  const cat = catalogue instanceof RefusChamps ? null : catalogue;
  // Hors Cloudflare (la zone de la version en service, sinon de la dernière) : un ordre part à l'installation.
  const ordre = horsCloudflare(zoneClient(c.config, lue?.config), cat?.zones_porte ?? null);
  return (
    <>
      {vue instanceof RefusChamps ? <Bandeau>{vue.message}</Bandeau> : vue && <DetailVersion a={a} c={c} v={vue} ordre={ordre} />}
      <h2 className="m-0 text-[18px] font-extrabold">{TA.versions}</h2>
      <Historique id={id} versions={h.versions} enService={c.version_en_service} choisie={choisie} />
      {preparer && (
        <Preparer
          id={id}
          externe={a.externe}
          gabarits={gabarits && !(gabarits instanceof RefusChamps) ? gabarits.gabarits.map((g) => ({ id: g.id, titre: g.titre, description: g.description })) : []}
          champsSimples={cat?.champs_client ?? null}
          derniere={lue?.config ? { numero: lue.version, config: lue.config } : null}
        />
      )}
    </>
  );
}

export const instant = false;
