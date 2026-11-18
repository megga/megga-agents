"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Confirmation } from "@/components/admin/confirmation";
import { envoyer } from "@/components/admin/envoyer";
import { Fait } from "@/components/admin/erreurs";
import { cadre, champ, etiquette, titreBloc, zoneTexte } from "@/components/admin/formulaire";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { TA } from "@/lib/admin/textes";

// Les gestes d'une installation hors Cloudflare (installations.gerer) : enregistrer la clé publique qu'elle a remise, la
// révoquer, proposer une image. Chacun derrière une confirmation ; comme ailleurs, un refus (la phrase de l'atelier) s'y
// affiche et la laisse ouverte ; une réussite se dit sous son bloc.

const adresse = (id: string) => `/api/admin/clients/${encodeURIComponent(id)}/installation`;

/** revocable : une clé est enregistrée, et pas encore révoquée. */
export function GestesInstallation({ id, revocable }: { id: string; revocable: boolean }) {
  const router = useRouter();
  const [cle, setCle] = useState("");
  const [version, setVersion] = useState("");
  const [image, setImage] = useState("");
  const [faitCle, setFaitCle] = useState<string | null>(null);
  const [faitImage, setFaitImage] = useState<string | null>(null);

  /** Un geste : sa réussite sous son bloc, puis l'écran relu ; un refus remonte à la confirmation, qui reste ouverte. */
  const geste = (faire: () => Promise<string>, fait: (t: string | null) => void) => async () => {
    fait(null);
    fait(await faire());
    router.refresh();
  };

  const enregistrer = geste(async () => {
    const r = await envoyer<{ cle: string }>(adresse(id), "PUT", { cle_publique: cle.trim() });
    setCle("");
    return TA.cleEnregistree(r?.cle ?? TA.inconnu);
  }, setFaitCle);

  const revoquer = geste(async () => {
    await envoyer(adresse(id), "DELETE");
    return TA.cleRevoquee;
  }, setFaitCle);

  const proposer = geste(async () => {
    const r = await envoyer<{ ordre?: number }>(`${adresse(id)}/image`, "POST", { version: version.trim(), image: image.trim() });
    setVersion("");
    setImage("");
    return typeof r?.ordre === "number" ? TA.ordreParti(r.ordre) : TA.ordrePartiSansNumero;
  }, setFaitImage);

  return (
    <>
      <section className={cadre}>
        <h2 className={titreBloc}>{TA.clePublique}</h2>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="installation-cle" className="sr-only">{TA.clePublique}</Label>
          <textarea id="installation-cle" value={cle} spellCheck={false} onChange={(e) => setCle(e.target.value)} className={zoneTexte + " min-h-20"} />
          <span className="text-[12.5px] text-faint">{TA.clePubliqueAide}</span>
        </div>
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
        <Fait texte={faitCle} />
      </section>
      <section className={cadre}>
        <h2 className={titreBloc}>{TA.proposerImage}</h2>
        <div className="grid gap-3.5 min-[761px]:grid-cols-[minmax(0,1fr)_minmax(0,3fr)]">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="image-version" className={etiquette}>{TA.versionImage}</Label>
            <Input id="image-version" value={version} autoComplete="off" onChange={(e) => setVersion(e.target.value)} className={champ} />
            <span className="text-[12.5px] text-faint">{TA.versionImageAttendue}</span>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="image-image" className={etiquette}>{TA.imageSignee}</Label>
            <Input id="image-image" value={image} autoComplete="off" spellCheck={false} onChange={(e) => setImage(e.target.value)} className={champ} />
            <span className="text-[12.5px] text-faint">{TA.imageAttendue}</span>
          </div>
        </div>
        <div>
          <Confirmation titre={TA.proposerImageTitre(version.trim())} effet={TA.proposerImageEffet} bouton={TA.proposerImage} onConfirmer={proposer}>
            {TA.proposerImage}
          </Confirmation>
        </div>
        <Fait texte={faitImage} />
      </section>
    </>
  );
}
