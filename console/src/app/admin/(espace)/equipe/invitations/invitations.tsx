"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Confirmation } from "@/components/admin/confirmation";
import { envoyer, ErreursChamps } from "@/components/admin/erreurs";
import { Pastille } from "@/components/admin/pastille";
import { SecretUnique } from "@/components/admin/secret";
import { Tableau } from "@/components/admin/tableau";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SUPERADMIN } from "@/lib/admin/droits";
import { TA } from "@/lib/admin/textes";
import { champ, ChampsAcces, etiquette, perimetreDe, PerimetreVu, tousPossible, type RoleChoix, type Vu } from "../membres";

// Inviter (courriel, rôle, externe, périmètre, fin d'accès) : le lien complet n'est montré qu'une fois, puis oublié.
// Les invitations en attente, et le retrait de celles que le membre aurait pu faire.

export type InvitationVue = {
  id: string;
  courriel: string;
  roleNom: string;
  externe: boolean;
  perimetre: Vu;
  finAccesLisible: string;
  valableJusqua: string;
  retirable: boolean;
};

export function Invitations({ invitations, roles, tousPermis, droitsExterne }: {
  invitations: InvitationVue[];
  roles: RoleChoix[];
  tousPermis: boolean;
  droitsExterne: string[];
}) {
  const router = useRouter();
  const [lien, setLien] = useState<string | null>(null);

  const lignes = invitations.map((i) => [
    <span key="courriel" className="whitespace-nowrap">{i.courriel}</span>,
    <span key="role" className="whitespace-nowrap">{i.roleNom}</span>,
    <Pastille key="statut" etat={i.externe ? "warn" : "faint"} texte={i.externe ? TA.externe : TA.interne} />,
    <PerimetreVu key="perimetre" p={i.perimetre} />,
    <span key="fin" className="whitespace-nowrap">{i.finAccesLisible}</span>,
    <span key="valable" className="whitespace-nowrap">{i.valableJusqua}</span>,
    i.retirable ? (
      <Confirmation
        key="retirer"
        titre={TA.retirerInvitationTitre}
        effet={TA.retirerInvitationEffet(i.courriel)}
        bouton={TA.retirer}
        onConfirmer={async () => {
          await envoyer(`/api/admin/equipe/invitations/${encodeURIComponent(i.id)}`, "DELETE");
          router.refresh();
        }}
      >
        {TA.retirer}
      </Confirmation>
    ) : null,
  ]);

  return (
    <>
      {roles.length > 0 && (
        <NouvelleInvitation
          roles={roles}
          tousPermis={tousPermis}
          droitsExterne={droitsExterne}
          onCreee={(chemin) => {
            setLien(window.location.origin + chemin);
            router.refresh();
          }}
        />
      )}
      <h2 className="m-0 mt-2 text-[18px] font-extrabold">{TA.enAttente}</h2>
      <Tableau
        colonnes={[TA.courriel, TA.role, TA.statut, TA.perimetre, TA.finAcces, TA.valableJusqua, ""]}
        lignes={lignes}
        vide={TA.videInvitations}
      />
      <SecretUnique valeur={lien} onFermer={() => setLien(null)} />
    </>
  );
}

function NouvelleInvitation({ roles, tousPermis, droitsExterne, onCreee }: {
  roles: RoleChoix[];
  tousPermis: boolean;
  droitsExterne: string[];
  onCreee: (lien: string) => void;
}) {
  const [courriel, setCourriel] = useState("");
  const [externe, setExterne] = useState(false);
  const proposes = externe ? roles.filter((r) => r.id !== SUPERADMIN) : roles;
  const [role, setRole] = useState(roles.find((r) => r.id !== SUPERADMIN)?.id ?? roles[0].id);
  const [mode, setMode] = useState<"tous" | "liste">("tous");
  const [liste, setListe] = useState("");
  const [fin, setFin] = useState("");
  const [erreur, setErreur] = useState<string | null>(null);
  const [envoi, setEnvoi] = useState(false);
  const roleChoisi = proposes.some((r) => r.id === role) ? role : (proposes[0]?.id ?? "");
  const superadmin = roleChoisi === SUPERADMIN;
  const tous = tousPossible(externe, tousPermis);

  async function inviter(e: React.FormEvent) {
    e.preventDefault();
    setEnvoi(true);
    setErreur(null);
    try {
      const corps = superadmin
        ? { courriel, role: roleChoisi, externe: false }
        : { courriel, role: roleChoisi, externe, perimetre: perimetreDe(tous ? mode : "liste", liste), finAcces: fin || null };
      const r = await envoyer<{ lien: string }>("/api/admin/equipe/invitations", "POST", corps);
      setCourriel("");
      setExterne(false);
      setMode("tous");
      setListe("");
      setFin("");
      onCreee(r!.lien);
    } catch (e) {
      setErreur(e instanceof Error ? e.message : TA.erreurInterne);
    } finally {
      setEnvoi(false);
    }
  }

  return (
    <form onSubmit={inviter} className="trait flex flex-col gap-3.5 rounded-2xl bg-bg px-5 pt-4 pb-5">
      <h2 className="m-0 text-[18px] font-extrabold">{TA.nouvelleInvitation}</h2>
      <div className="grid gap-3.5 min-[761px]:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="invitation-courriel" className={etiquette}>{TA.courriel}</Label>
          <Input id="invitation-courriel" type="email" required autoComplete="off" value={courriel} onChange={(e) => setCourriel(e.target.value)} className={champ} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="invitation-role" className={etiquette}>{TA.role}</Label>
          <select id="invitation-role" value={roleChoisi} onChange={(e) => setRole(e.target.value)} className={"trait " + champ}>
            {proposes.map((r) => (
              <option key={r.id} value={r.id}>
                {r.nom}
              </option>
            ))}
          </select>
        </div>
      </div>
      <label className="flex items-center gap-2 text-[14px] font-semibold">
        <input type="checkbox" checked={externe} onChange={(e) => setExterne(e.target.checked)} className="size-4 accent-marque" />
        {TA.externeCase}
      </label>
      {externe && (
        <div className="rounded-xl bg-side px-3.5 py-2.5 text-[13.5px] text-muted-ink">
          <p className="m-0">{TA.externeGarde}</p>
          <ul className="m-0 mt-1 pl-5">
            {droitsExterne.map((d) => (
              <li key={d}>{d}</li>
            ))}
          </ul>
        </div>
      )}
      {!superadmin && (
        <div className="grid gap-3.5 min-[761px]:grid-cols-2">
          <ChampsAcces id="invitation" tous={tous} mode={mode} liste={liste} fin={fin} onMode={setMode} onListe={setListe} onFin={setFin} />
        </div>
      )}
      <ErreursChamps erreur={erreur} />
      <button type="submit" disabled={envoi} className="h-10 self-start rounded-full bg-marque px-5 text-[14.5px] font-bold text-on-marque disabled:opacity-60">
        {TA.inviter}
      </button>
    </form>
  );
}
