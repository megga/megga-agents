import Link from "next/link";
import { notFound } from "next/navigation";
import { Bandeau } from "@/components/admin/erreurs";
import { Tableau } from "@/components/admin/tableau";
import { atelier, ouRefus, RefusChamps } from "@/lib/admin/atelier";
import { gardePage } from "@/lib/admin/garde";
import { clePersonne } from "@/lib/admin/personnes";
import { TA } from "@/lib/admin/textes";

// L'onglet Conversations d'un client (conversations.lire) : les personnes qui ont écrit, la plus récente d'abord (l'ordre de
// l'atelier), avec leur nombre de messages. Chacune ouvre son fil, en lecture seule, par une adresse qui porte sa clé opaque
// (personnes.ts), jamais son numéro. Une installation chez le client : la phrase de l'atelier (les conversations ne la
// quittent jamais). Jamais mis en service : il n'en a pas.
export default async function PageConversations({ params }: PageProps<"/admin/clients/[id]/conversations">) {
  const { id } = await params;
  await gardePage("conversations.lire", id);
  const c = await ouRefus(atelier.client(id));
  if (c instanceof RefusChamps && c.statut === 404) notFound();
  if (!(c instanceof RefusChamps) && c.version_en_service == null) return <Bandeau etat="faint">{TA.jamaisSansConversation}</Bandeau>;
  const r = await ouRefus(atelier.conversations(id));
  if (r instanceof RefusChamps) {
    if (r.statut === 404) notFound();
    return <Bandeau etat={r.statut === 409 ? "faint" : "accent"}>{r.message}</Bandeau>;
  }
  const fil = (personne: string) => `/admin/clients/${encodeURIComponent(id)}/conversations/${clePersonne(id, personne)}`;
  return (
    <Tableau
      colonnes={[TA.personne, TA.messages, TA.dernierMessage]}
      vide={TA.videConversations}
      replier={[1, 2]}
      lignes={r.conversations.map((p) => [
        <Link key="personne" href={fil(p.personne)} className="font-bold break-all text-ink hover:underline">
          {p.personne}
        </Link>,
        <span key="messages" className="tabular-nums">{TA.nombre(p.messages)}</span>,
        <span key="derniere" className="whitespace-nowrap">{TA.moment(typeof p.derniere === "number" ? p.derniere : null)}</span>,
      ])}
    />
  );
}

export const instant = false;
