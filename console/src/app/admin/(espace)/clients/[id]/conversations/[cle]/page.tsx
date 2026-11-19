import { notFound } from "next/navigation";
import { Bandeau } from "@/components/admin/erreurs";
import { atelier, ouRefus, RefusChamps, type Message } from "@/lib/admin/atelier";
import { gardePage } from "@/lib/admin/garde";
import { noter } from "@/lib/admin/journal";
import { CLE_PERSONNE, clePersonne } from "@/lib/admin/personnes";
import { TA } from "@/lib/admin/textes";
import { pret } from "@/lib/base";

// Le fil d'une personne (conversations.lire), en lecture seule : ses derniers messages en bulles, comme la console, reçus à
// gauche, envoyés par l'agent à droite. L'adresse porte la clé opaque de la personne (personnes.ts), jamais son numéro :
// la page la retrouve dans la liste des conversations du client. Chaque fil ouvert se note au journal, lu ou refusé, sur
// la cible du client ; noter réduit le numéro à ses quatre derniers chiffres. Le journal en panne, le fil ne s'affiche pas.

function Fil({ messages }: { messages: Message[] }) {
  if (!messages.length) return <p className="trait m-0 rounded-2xl bg-bg px-4 py-6 text-center text-[14px] text-faint">{TA.videFil}</p>;
  return (
    <ol className="m-0 flex w-full max-w-[760px] list-none flex-col gap-3 p-0">
      {messages.map((m, i) => {
        const envoye = m.sens === "envoye";
        return (
          <li key={i} className={"flex max-w-[75%] flex-col gap-1 max-[760px]:max-w-[90%] " + (envoye ? "items-end self-end" : "items-start self-start")}>
            <p className={"m-0 px-4 py-2.5 break-words whitespace-pre-wrap " + (envoye ? "rounded-[20px_20px_6px_20px] bg-soft" : "rounded-[20px_20px_20px_6px] bg-hover")}>
              <span className="sr-only">{envoye ? TA.envoye : TA.recu} </span>
              {m.texte}
            </p>
            <span className="px-1 text-[12px] text-faint">{TA.moment(typeof m.quand === "number" ? m.quand : null)}</span>
          </li>
        );
      })}
    </ol>
  );
}

/** Un refus de l'atelier, tel que la page le montre : 404 introuvable ; une installation chez le client, sa phrase en information. */
function refus(r: RefusChamps) {
  if (r.statut === 404) notFound();
  return <Bandeau etat={r.statut === 409 ? "faint" : "accent"}>{r.message}</Bandeau>;
}

export default async function PageFil({ params }: PageProps<"/admin/clients/[id]/conversations/[cle]">) {
  const { id, cle } = await params;
  const a = await gardePage("conversations.lire", id);
  if (!CLE_PERSONNE.test(cle)) notFound();
  const c = await ouRefus(atelier.client(id));
  if (c instanceof RefusChamps && c.statut === 404) notFound();
  if (!(c instanceof RefusChamps) && c.version_en_service == null) return <Bandeau etat="faint">{TA.jamaisSansConversation}</Bandeau>;
  // La personne de la clé, parmi celles que la liste montre (la même lecture, gardée un instant) ; aucune : 404, rien de noté.
  const liste = await ouRefus(atelier.conversations(id));
  if (liste instanceof RefusChamps) return refus(liste);
  const personne = liste.conversations.find((p) => clePersonne(id, p.personne) === cle)?.personne;
  if (personne === undefined) notFound();
  const r = await ouRefus(atelier.echanges(id, personne));
  await noter(await pret(), { qui: a.utilisateur, courriel: a.courriel, action: "conversations.lire", cible: `client:${id}`,
    resultat: r instanceof RefusChamps ? `refuse ${r.statut}` : "ok", detail: { personne } });
  return (
    <>
      <h2 className="m-0 text-[17px] font-extrabold break-all">{personne}</h2>
      {r instanceof RefusChamps ? refus(r) : <Fil messages={r.messages} />}
    </>
  );
}

export const instant = false;
