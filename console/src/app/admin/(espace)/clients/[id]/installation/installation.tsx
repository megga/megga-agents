"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Confirmation } from "@/components/admin/confirmation";
import { envoyer, RefusEnvoi } from "@/components/admin/envoyer";
import { ErreursChamps } from "@/components/admin/erreurs";
import { champ, etiquette, zoneTexte } from "@/components/admin/formulaire";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { ChampErreur } from "@/lib/admin/champs";
import { TA } from "@/lib/admin/textes";

// Les gestes d'une installation hors Cloudflare (installations.gerer) : enregistrer la clé publique qu'elle a remise, la
// révoquer, proposer une image. Chacun derrière une confirmation ; un refus s'affiche sous ses champs, champ par champ.

type Refus = { erreur: string; champs: ChampErreur[] } | null;

const adresse = (id: string) => `/api/admin/clients/${encodeURIComponent(id)}/installation`;
const section = "trait flex min-w-0 flex-col gap-3 rounded-2xl bg-bg px-5 pt-4 pb-5";
const titre2 = "m-0 text-[18px] font-extrabold";
const refusDe = (e: unknown): Refus => ({ erreur: e instanceof Error ? e.message : TA.erreurInterne, champs: e instanceof RefusEnvoi ? e.champs : [] });

function Fait({ texte }: { texte: string | null }) {
  if (!texte) return null;
  return (
    <p role="status" className="m-0 text-[13.5px] font-semibold text-ok">
      {texte}
    </p>
  );
}

/** revocable : une clé est enregistrée, et pas encore révoquée. */
export function GestesInstallation({ id, revocable }: { id: string; revocable: boolean }) {
  const router = useRouter();
  const [cle, setCle] = useState("");
  const [refusCle, setRefusCle] = useState<Refus>(null);
  const [version, setVersion] = useState("");
  const [image, setImage] = useState("");
  const [refusImage, setRefusImage] = useState<Refus>(null);
  const [faitCle, setFaitCle] = useState<string | null>(null);
  const [faitImage, setFaitImage] = useState<string | null>(null);

  /** Un geste : sa réussite, ou sa phrase et ses champs, sous son formulaire ; la confirmation se ferme. */
  const geste = (faire: () => Promise<string>, refus: (r: Refus) => void, fait: (t: string | null) => void) => async () => {
    refus(null);
    fait(null);
    try {
      fait(await faire());
      router.refresh();
    } catch (e) {
      refus(refusDe(e));
    }
  };

  const enregistrer = geste(async () => {
    const r = await envoyer<{ cle: string }>(adresse(id), "PUT", { cle_publique: cle.trim() });
    setCle("");
    return TA.cleEnregistree(r?.cle ?? TA.inconnu);
  }, setRefusCle, setFaitCle);

  const revoquer = geste(async () => {
    await envoyer(adresse(id), "DELETE");
    return TA.cleRevoquee;
  }, setRefusCle, setFaitCle);

  const proposer = geste(async () => {
    const r = await envoyer<{ ordre: number }>(`${adresse(id)}/image`, "POST", { version: version.trim(), image: image.trim() });
    setVersion("");
    setImage("");
    return TA.ordreParti(r?.ordre ?? 0);
  }, setRefusImage, setFaitImage);

  return (
    <>
      <section className={section}>
        <h2 className={titre2}>{TA.clePublique}</h2>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="installation-cle" className="sr-only">{TA.clePublique}</Label>
          <textarea id="installation-cle" value={cle} spellCheck={false} onChange={(e) => setCle(e.target.value)} className={zoneTexte + " min-h-20"} />
          <span className="text-[12.5px] text-faint">{TA.clePubliqueAide}</span>
        </div>
        <ErreursChamps erreur={refusCle?.erreur ?? null} champs={refusCle?.champs} />
        <Fait texte={faitCle} />
        <div className="flex flex-wrap gap-2">
          <Confirmation titre={TA.enregistrerCleTitre} effet={TA.enregistrerCleEffet} bouton={TA.enregistrerCle} onConfirmer={enregistrer}>
            {TA.enregistrerCle}
          </Confirmation>
          {revocable && (
            <Confirmation titre={TA.revoquerCleTitre} effet={TA.revoquerCleEffet} bouton={TA.revoquerCle} onConfirmer={revoquer}>
              {TA.revoquerCle}
            </Confirmation>
          )}
        </div>
      </section>
      <section className={section}>
        <h2 className={titre2}>{TA.proposerImage}</h2>
        <div className="grid gap-3.5 min-[761px]:grid-cols-[minmax(0,1fr)_minmax(0,3fr)]">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="image-version" className={etiquette}>{TA.versionImage}</Label>
            <Input id="image-version" value={version} autoComplete="off" onChange={(e) => setVersion(e.target.value)} className={champ} />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="image-image" className={etiquette}>{TA.imageSignee}</Label>
            <Input id="image-image" value={image} autoComplete="off" spellCheck={false} onChange={(e) => setImage(e.target.value)} className={champ} />
          </div>
        </div>
        <span className="text-[12.5px] text-faint">{TA.imageAttendue}</span>
        <ErreursChamps erreur={refusImage?.erreur ?? null} champs={refusImage?.champs} />
        <Fait texte={faitImage} />
        <div>
          <Confirmation titre={TA.proposerImageTitre(version.trim())} effet={TA.proposerImageEffet} bouton={TA.proposerImage} onConfirmer={proposer}>
            {TA.proposerImage}
          </Confirmation>
        </div>
      </section>
    </>
  );
}
