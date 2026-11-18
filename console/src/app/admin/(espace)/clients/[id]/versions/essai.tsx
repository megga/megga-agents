"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { envoyer, refusDe } from "@/components/admin/envoyer";
import { ErreursChamps } from "@/components/admin/erreurs";
import { champ, etiquette } from "@/components/admin/formulaire";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { TA } from "@/lib/admin/textes";

// Essayer un brouillon (versions.preparer) : une petite conversation avec l'agent de cette version, hors WhatsApp, dans le rôle
// choisi parmi ceux que sa configuration règle ; changer de rôle en commence une autre. Un essai consomme des jetons.

const nouvelleConversation = () => "admin-" + Math.random().toString(36).slice(2, 10);

export function Essai({ id, numero, roles }: { id: string; numero: number; roles: string[] }) {
  const router = useRouter();
  const [role, setRole] = useState<string | null>(roles.includes("visiteur") ? "visiteur" : (roles[0] ?? null));
  const [conversation, setConversation] = useState(nouvelleConversation);
  const [echanges, setEchanges] = useState<{ message: string; reponse: string }[]>([]);
  const [message, setMessage] = useState("");
  const [erreur, setErreur] = useState<string | null>(null);
  const [envoi, setEnvoi] = useState(false);

  function changerRole(r: string) {
    setRole(r);
    setConversation(nouvelleConversation());
    setEchanges([]);
  }

  async function essayer(e: React.FormEvent) {
    e.preventDefault();
    const texte = message.trim();
    if (!texte) return;
    setEnvoi(true);
    setErreur(null);
    try {
      const r = await envoyer<{ reponse: string }>(`/api/admin/clients/${encodeURIComponent(id)}/versions/${numero}/essai`, "POST",
        { message: texte, conversation, ...(role ? { role } : {}) });
      setEchanges((l) => [...l, { message: texte, reponse: r?.reponse ?? "" }]);
      setMessage("");
      router.refresh(); // le nombre d'essais : « Forcer » devient « Mettre en service »
    } catch (e) {
      setErreur(refusDe(e).erreur);
    } finally {
      setEnvoi(false);
    }
  }

  return (
    <form onSubmit={essayer} className="flex flex-col gap-3">
      <h3 className="m-0 text-[16px] font-extrabold">{TA.essaiTitre(numero)}</h3>
      <p className="m-0 text-[13.5px] text-warn">{TA.essaiConsomme}</p>
      {roles.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={`essai-${numero}-role`} className={etiquette}>{TA.roleEssai}</Label>
          <select id={`essai-${numero}-role`} value={role ?? ""} onChange={(e) => changerRole(e.target.value)} className={"trait w-fit " + champ}>
            {roles.map((r) => (
              <option key={r} value={r}>
                {TA.rolesEssai[r] ?? r}
              </option>
            ))}
          </select>
        </div>
      )}
      {echanges.length > 0 && (
        <ol className="m-0 flex list-none flex-col gap-2 p-0">
          {echanges.flatMap((x, i) => [
            <li key={`${i}-m`} className="max-w-[90%] self-start rounded-[20px_20px_20px_6px] bg-hover px-4 py-2.5 whitespace-pre-wrap wrap-anywhere">
              <span className="sr-only">{TA.recu} </span>
              {x.message}
            </li>,
            <li key={`${i}-r`} className="max-w-[90%] self-end rounded-[20px_20px_6px_20px] bg-soft px-4 py-2.5 whitespace-pre-wrap wrap-anywhere">
              <span className="sr-only">{TA.envoye} </span>
              {x.reponse}
            </li>,
          ])}
        </ol>
      )}
      <div className="flex flex-wrap items-end gap-2">
        <div className="flex min-w-0 flex-1 flex-col gap-1.5">
          <Label htmlFor={`essai-${numero}-message`} className={etiquette}>{TA.votreMessage}</Label>
          <Input id={`essai-${numero}-message`} value={message} maxLength={4000} autoComplete="off" onChange={(e) => setMessage(e.target.value)} className={champ} />
        </div>
        <button type="submit" disabled={envoi || !message.trim()} className="h-10 rounded-full bg-marque px-5 text-[14.5px] font-bold text-on-marque disabled:opacity-60">
          {TA.envoyer}
        </button>
      </div>
      <ErreursChamps erreur={erreur} />
    </form>
  );
}
