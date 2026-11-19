"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Confirmation } from "@/components/admin/confirmation";
import { envoyer } from "@/components/admin/envoyer";
import { ErreursChamps } from "@/components/admin/erreurs";
import { champ, ChampsAcces, etiquette, ExterneGarde, perimetreDe, PerimetreVu, tousPossible, type RoleChoix, type Vu } from "@/components/admin/formulaire";
import { Pastille } from "@/components/admin/pastille";
import { Tableau } from "@/components/admin/tableau";
import { Avatar } from "@/components/console/avatar";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { SUPERADMIN } from "@/lib/admin/droits";
import { TA } from "@/lib/admin/textes";

// Les membres de l'équipe : le tableau, et pour ceux que le membre peut toucher, modifier (rôle, périmètre, fin d'accès)
// ou retirer. Dans un cadre étroit, les colonnes secondaires se replient sous le nom.

export type MembreVu = {
  utilisateur: string;
  nom: string;
  courriel: string;
  image: string | null;
  role: string;
  roleNom: string;
  externe: boolean;
  perimetre: Vu;
  finAcces: string | null;
  finAccesLisible: string;
  derniereConnexion: string;
  modifiable: boolean;
};

export function Membres({ membres, roles, tousPermis }: { membres: MembreVu[]; roles: RoleChoix[]; tousPermis: boolean }) {
  const router = useRouter();
  const [edite, setEdite] = useState<MembreVu | null>(null);

  const lignes = membres.map((m) => [
    <div key="membre" className="flex items-center gap-2.5">
      <Avatar nom={m.nom || m.courriel} image={m.image} taille={32} />
      <div className="flex min-w-0 flex-col">
        <b>{m.nom || m.courriel}</b>
        <span className="text-[13px] whitespace-nowrap text-muted-ink">{m.courriel}</span>
      </div>
    </div>,
    <span key="role" className="whitespace-nowrap">{m.roleNom}</span>,
    <Pastille key="statut" etat={m.externe ? "warn" : "faint"} texte={m.externe ? TA.externe : TA.interne} />,
    <PerimetreVu key="perimetre" p={m.perimetre} />,
    <span key="fin" className="whitespace-nowrap">{m.finAccesLisible}</span>,
    <span key="connexion" className="whitespace-nowrap">{m.derniereConnexion}</span>,
    m.modifiable ? (
      <div key="gestes" className="flex flex-wrap gap-1.5">
        <button type="button" onClick={() => setEdite(m)} className="trait rounded-full bg-bg px-3 py-1 text-[13px] font-semibold whitespace-nowrap text-ink hover:bg-hover">
          {TA.modifier}
        </button>
        <Confirmation
          titre={TA.retirerMembreTitre}
          effet={TA.retirerMembreEffet(m.nom || m.courriel)}
          bouton={TA.retirer}
          onConfirmer={async () => {
            await envoyer(`/api/admin/equipe/membres/${encodeURIComponent(m.utilisateur)}`, "DELETE");
            router.refresh();
          }}
        >
          {TA.retirer}
        </Confirmation>
      </div>
    ) : null,
  ]);

  return (
    <>
      <Tableau
        colonnes={[TA.membre, TA.role, TA.statut, TA.perimetre, TA.finAcces, TA.derniereConnexion, ""]}
        lignes={lignes}
        vide={TA.videMembres}
        replier={[1, 2, 3, 4, 5]}
      />
      <Dialog open={edite !== null} onOpenChange={(o) => !o && setEdite(null)}>
        <DialogContent className="gap-4 rounded-[22px] bg-bg p-5 shadow-doux sm:max-w-[460px]">
          {edite && (
            <FormMembre
              key={edite.utilisateur}
              membre={edite}
              roles={edite.externe ? roles.filter((r) => r.id !== SUPERADMIN) : roles}
              tousPermis={tousPermis}
              onFini={() => {
                setEdite(null);
                router.refresh();
              }}
            />
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}

function FormMembre({ membre: m, roles, tousPermis, onFini }: { membre: MembreVu; roles: RoleChoix[]; tousPermis: boolean; onFini: () => void }) {
  const [role, setRole] = useState(m.role);
  const [mode, setMode] = useState<"tous" | "liste">(m.perimetre === "tous" ? "tous" : "liste");
  const [liste, setListe] = useState(m.perimetre === "tous" ? "" : m.perimetre.clients.join(", "));
  const [fin, setFin] = useState(m.finAcces ?? "");
  const [erreur, setErreur] = useState<string | null>(null);
  const [envoi, setEnvoi] = useState(false);
  const superadmin = role === SUPERADMIN;
  const tous = tousPossible(m.externe, tousPermis);

  async function enregistrer(e: React.FormEvent) {
    e.preventDefault();
    setEnvoi(true);
    setErreur(null);
    try {
      const corps = superadmin ? { role } : { role, perimetre: perimetreDe(tous ? mode : "liste", liste), finAcces: fin || null };
      await envoyer(`/api/admin/equipe/membres/${encodeURIComponent(m.utilisateur)}`, "PATCH", corps);
      onFini();
    } catch (e) {
      setErreur(e instanceof Error ? e.message : TA.erreurInterne);
      setEnvoi(false);
    }
  }

  return (
    <form onSubmit={enregistrer} className="flex flex-col gap-3.5">
      <DialogTitle className="text-[17px] font-extrabold">{TA.titreModifier(m.nom || m.courriel)}</DialogTitle>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="membre-role" className={etiquette}>{TA.role}</Label>
        <select id="membre-role" value={role} onChange={(e) => setRole(e.target.value)} className={"trait " + champ}>
          {roles.map((r) => (
            <option key={r.id} value={r.id}>
              {r.nom}
            </option>
          ))}
        </select>
      </div>
      {m.externe && <ExterneGarde />}
      {!superadmin && (
        <ChampsAcces id="membre" tous={tous} mode={mode} liste={liste} fin={fin} onMode={setMode} onListe={setListe} onFin={setFin} />
      )}
      <ErreursChamps erreur={erreur} />
      <button type="submit" disabled={envoi} className="mt-1 h-10 rounded-full bg-marque text-[14.5px] font-bold text-on-marque disabled:opacity-60">
        {TA.enregistrer}
      </button>
    </form>
  );
}
