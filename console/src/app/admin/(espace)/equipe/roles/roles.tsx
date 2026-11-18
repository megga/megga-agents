"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Confirmation } from "@/components/admin/confirmation";
import { envoyer, ErreursChamps } from "@/components/admin/erreurs";
import { Pastille } from "@/components/admin/pastille";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { DROITS, GROUPES_DE_DROITS, type Droit } from "@/lib/admin/droits";
import { TA } from "@/lib/admin/textes";
import { champ, etiquette } from "../membres";

// Les rôles : chacun avec ses droits par groupe et son nombre de membres. Créer, modifier, retirer : seulement ce que la
// non-escalade laisse passer (peutEcrireRole, côté serveur), et seulement les droits que le membre a lui-même.

export type RoleVu = {
  id: string;
  nom: string;
  description: string;
  droits: Droit[];
  systeme: boolean;
  membres: number;
  modifiable: boolean;
  retirable: boolean;
};

export function Roles({ roles, peutCreer, permis }: { roles: RoleVu[]; peutCreer: boolean; permis: Droit[] }) {
  const router = useRouter();
  const [edite, setEdite] = useState<RoleVu | "nouveau" | null>(null);

  return (
    <>
      {peutCreer && (
        <button type="button" onClick={() => setEdite("nouveau")} className="self-start rounded-full bg-marque px-5 py-2 text-[14.5px] font-bold text-on-marque">
          {TA.nouveauRole}
        </button>
      )}
      <div className="grid gap-3 min-[1000px]:grid-cols-2">
        {roles.map((r) => (
          <article key={r.id} className="trait flex min-w-0 flex-col gap-2.5 rounded-2xl bg-bg px-5 pt-4 pb-4.5">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="m-0 mr-auto text-[17px] font-extrabold">{r.nom}</h2>
              {r.systeme && <Pastille etat="accent" texte={TA.roleFixeMarque} />}
              <Pastille etat={r.membres ? "ok" : "faint"} texte={TA.nombreMembres(r.membres)} />
            </div>
            {r.description && <p className="m-0 text-[14px] text-muted-ink">{r.description}</p>}
            <DroitsParGroupe droits={r.droits} />
            {(r.modifiable || r.retirable) && (
              <div className="mt-1 flex gap-1.5">
                {r.modifiable && (
                  <button type="button" onClick={() => setEdite(r)} className="trait rounded-full bg-bg px-3 py-1 text-[13px] font-semibold text-ink hover:bg-hover">
                    {TA.modifier}
                  </button>
                )}
                {r.retirable && (
                  <Confirmation
                    titre={TA.retirerRoleTitre}
                    effet={TA.retirerRoleEffet(r.nom)}
                    bouton={TA.retirer}
                    onConfirmer={async () => {
                      await envoyer(`/api/admin/equipe/roles/${encodeURIComponent(r.id)}`, "DELETE");
                      router.refresh();
                    }}
                  >
                    {TA.retirer}
                  </Confirmation>
                )}
              </div>
            )}
          </article>
        ))}
      </div>
      <Dialog open={edite !== null} onOpenChange={(o) => !o && setEdite(null)}>
        <DialogContent className="max-h-[calc(100dvh-2rem)] gap-4 overflow-y-auto rounded-[22px] bg-bg p-5 shadow-doux sm:max-w-[520px]">
          {edite && (
            <FormRole
              key={edite === "nouveau" ? "nouveau" : edite.id}
              role={edite === "nouveau" ? null : edite}
              permis={permis}
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

/** Les droits d'un rôle, rangés par groupe ; un groupe sans droit coché ne s'affiche pas. */
function DroitsParGroupe({ droits }: { droits: Droit[] }) {
  const groupes = GROUPES_DE_DROITS.map((g) => ({ titre: g.titre, droits: g.droits.filter((d) => droits.includes(d)) })).filter((g) => g.droits.length);
  if (!groupes.length) return <p className="m-0 text-[13.5px] text-faint">{TA.aucunDroit}</p>;
  return (
    <dl className="m-0 flex flex-col gap-1.5">
      {groupes.map((g) => (
        <div key={g.titre} className="flex flex-col gap-1">
          <dt className="text-[11.5px] font-bold tracking-[.06em] text-faint uppercase">{g.titre}</dt>
          <dd className="m-0 flex flex-wrap gap-1">
            {g.droits.map((d) => (
              <span key={d} className="trait rounded-full px-2.5 py-0.5 text-[12.5px] font-semibold text-ink">
                {TA.nomsDroits[d]}
              </span>
            ))}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function FormRole({ role, permis, onFini }: { role: RoleVu | null; permis: Droit[]; onFini: () => void }) {
  const [nom, setNom] = useState(role?.nom ?? "");
  const [description, setDescription] = useState(role?.description ?? "");
  const [droits, setDroits] = useState<Droit[]>(role?.droits ?? []);
  const [erreur, setErreur] = useState<string | null>(null);
  const [envoi, setEnvoi] = useState(false);

  function cocher(d: Droit, oui: boolean) {
    setDroits((l) => DROITS.filter((x) => (x === d ? oui : l.includes(x))));
  }

  async function enregistrer(e: React.FormEvent) {
    e.preventDefault();
    setEnvoi(true);
    setErreur(null);
    try {
      const corps = { nom, description, droits };
      if (role) await envoyer(`/api/admin/equipe/roles/${encodeURIComponent(role.id)}`, "PATCH", corps);
      else await envoyer("/api/admin/equipe/roles", "POST", corps);
      onFini();
    } catch (e) {
      setErreur(e instanceof Error ? e.message : TA.erreurInterne);
      setEnvoi(false);
    }
  }

  return (
    <form onSubmit={enregistrer} className="flex flex-col gap-3.5">
      <DialogTitle className="text-[17px] font-extrabold">{role ? TA.titreModifier(role.nom) : TA.nouveauRole}</DialogTitle>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="role-nom" className={etiquette}>{TA.nomDuRole}</Label>
        <Input id="role-nom" required maxLength={60} value={nom} onChange={(e) => setNom(e.target.value)} className={champ} />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="role-description" className={etiquette}>{TA.description}</Label>
        <Input id="role-description" maxLength={200} value={description} onChange={(e) => setDescription(e.target.value)} className={champ} />
      </div>
      <fieldset className="m-0 flex flex-col gap-3 border-0 p-0">
        <legend className={etiquette + " mb-1.5"}>{TA.droits}</legend>
        {GROUPES_DE_DROITS.map((g) => (
          <div key={g.titre} className="flex flex-col gap-1.5">
            <span className="text-[11.5px] font-bold tracking-[.06em] text-faint uppercase">{g.titre}</span>
            {g.droits.map((d) => {
              const libre = permis.includes(d);
              return (
                <label key={d} className={"flex items-center gap-2 text-[14px] " + (libre ? "text-ink" : "text-faint")}>
                  <input type="checkbox" checked={droits.includes(d)} disabled={!libre} onChange={(e) => cocher(d, e.target.checked)} className="size-4 accent-marque" />
                  {TA.nomsDroits[d]}
                </label>
              );
            })}
          </div>
        ))}
      </fieldset>
      <ErreursChamps erreur={erreur} />
      <button type="submit" disabled={envoi} className="h-10 rounded-full bg-marque text-[14.5px] font-bold text-on-marque disabled:opacity-60">
        {role ? TA.enregistrer : TA.creer}
      </button>
    </form>
  );
}
