"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Confirmation } from "@/components/admin/confirmation";
import { envoyer, ErreursChamps } from "@/components/admin/erreurs";
import { Pastille } from "@/components/admin/pastille";
import { Tableau } from "@/components/admin/tableau";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SUPERADMIN } from "@/lib/admin/droits";
import { TA } from "@/lib/admin/textes";

// Les membres de l'équipe : le tableau, et pour ceux que le membre peut toucher, modifier (rôle, périmètre, fin d'accès)
// ou retirer. ChampsAcces et PerimetreVu servent aussi aux invitations.

export type Vu = "tous" | { clients: string[]; autres: number };

export type MembreVu = {
  utilisateur: string;
  nom: string;
  courriel: string;
  role: string;
  roleNom: string;
  externe: boolean;
  perimetre: Vu;
  finAcces: string | null;
  finAccesLisible: string;
  derniereConnexion: string;
  modifiable: boolean;
};

export type RoleChoix = { id: string; nom: string };

/** Le périmètre tel que le membre le voit : les clients qu'il partage, les autres comptés. */
export function PerimetreVu({ p }: { p: Vu }) {
  if (p === "tous") return <span className="whitespace-nowrap">{TA.tousLesClients}</span>;
  if (!p.clients.length) return <span className="text-muted-ink">{p.autres ? TA.nClients(p.autres) : TA.aucunClient}</span>;
  return (
    <span className="block max-w-[260px]">
      {p.clients.join(", ")}
      {p.autres > 0 && <span className="text-muted-ink"> {TA.etAutres(p.autres)}</span>}
    </span>
  );
}

/** Le corps d'un périmètre : « tous », ou les identifiants tapés, séparés par des virgules ou des espaces. */
export function perimetreDe(mode: "tous" | "liste", liste: string): "tous" | string[] {
  return mode === "tous" ? "tous" : liste.split(/[\s,;]+/).filter(Boolean);
}

export const champ = "h-10 rounded-xl bg-bg px-3 text-[14.5px] text-ink placeholder:text-faint";
export const etiquette = "text-[13px] font-semibold text-muted-ink";

/** « Tous les clients » n'est permis ni à un externe, ni par un membre limité à une liste. */
export const tousPossible = (externe: boolean, tousPermis: boolean) => tousPermis && !externe;

/**
 * Le périmètre et la fin d'accès d'un membre ou d'une invitation. tous : « tous les clients » est-il permis
 * (tousPossible) ; sinon, la liste seule, et le corps se fait avec perimetreDe("liste", …).
 */
export function ChampsAcces(p: {
  id: string;
  tous: boolean;
  mode: "tous" | "liste";
  liste: string;
  fin: string;
  onMode: (m: "tous" | "liste") => void;
  onListe: (v: string) => void;
  onFin: (v: string) => void;
}) {
  const { tous } = p;
  const mode = tous ? p.mode : "liste";
  return (
    <>
      <fieldset className="m-0 flex flex-col gap-1.5 border-0 p-0">
        <legend className={etiquette + " mb-1.5"}>{TA.perimetre}</legend>
        <div className="flex flex-wrap gap-x-4 gap-y-1.5 text-[14px]">
          <label className="flex items-center gap-2">
            <input type="radio" name={p.id + "-mode"} checked={mode === "tous"} disabled={!tous} onChange={() => p.onMode("tous")} className="accent-marque" />
            <span className={tous ? "" : "text-faint"}>{TA.tousLesClients}</span>
          </label>
          <label className="flex items-center gap-2">
            <input type="radio" name={p.id + "-mode"} checked={mode === "liste"} onChange={() => p.onMode("liste")} className="accent-marque" />
            {TA.uneListe}
          </label>
        </div>
        {mode === "liste" && (
          <>
            <Input aria-label={TA.uneListe} value={p.liste} onChange={(e) => p.onListe(e.target.value)} className={champ} />
            <span className="text-[12.5px] text-faint">{TA.perimetreAide}</span>
          </>
        )}
      </fieldset>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor={p.id + "-fin"} className={etiquette}>{TA.finAcces}</Label>
        <Input id={p.id + "-fin"} type="date" value={p.fin} onChange={(e) => p.onFin(e.target.value)} className={champ} />
        <span className="text-[12.5px] text-faint">{TA.finAccesAide}</span>
      </div>
    </>
  );
}

export function Membres({ membres, roles, tousPermis }: { membres: MembreVu[]; roles: RoleChoix[]; tousPermis: boolean }) {
  const router = useRouter();
  const [edite, setEdite] = useState<MembreVu | null>(null);

  const lignes = membres.map((m) => [
    <b key="nom" className="whitespace-nowrap">{m.nom || m.courriel}</b>,
    <span key="courriel" className="whitespace-nowrap">{m.courriel}</span>,
    <span key="role" className="whitespace-nowrap">{m.roleNom}</span>,
    <Pastille key="statut" etat={m.externe ? "warn" : "faint"} texte={m.externe ? TA.externe : TA.interne} />,
    <PerimetreVu key="perimetre" p={m.perimetre} />,
    <span key="fin" className="whitespace-nowrap">{m.finAccesLisible}</span>,
    <span key="connexion" className="whitespace-nowrap">{m.derniereConnexion}</span>,
    m.modifiable ? (
      <div key="gestes" className="flex gap-1.5">
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
        colonnes={[TA.nom, TA.courriel, TA.role, TA.statut, TA.perimetre, TA.finAcces, TA.derniereConnexion, ""]}
        lignes={lignes}
        vide={TA.videMembres}
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
      {!superadmin && (
        <ChampsAcces
          id="membre"
          tous={tous}
          mode={mode}
          liste={liste}
          fin={fin}
          onMode={setMode}
          onListe={setListe}
          onFin={setFin}
        />
      )}
      <ErreursChamps erreur={erreur} />
      <button type="submit" disabled={envoi} className="mt-1 h-10 rounded-full bg-marque text-[14.5px] font-bold text-on-marque disabled:opacity-60">
        {TA.enregistrer}
      </button>
    </form>
  );
}
