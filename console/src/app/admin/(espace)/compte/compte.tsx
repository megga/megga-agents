"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Confirmation } from "@/components/admin/confirmation";
import { envoyer, refusDe } from "@/components/admin/envoyer";
import { ErreursChamps, Fait } from "@/components/admin/erreurs";
import { cadre, champ, etiquette, titreBloc } from "@/components/admin/formulaire";
import { Avatar } from "@/components/console/avatar";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { TA } from "@/lib/admin/textes";

// Les formulaires de Mon compte : la photo (choisie, recadrée en carré au centre et réduite à 256 px ici, dans le navigateur,
// puis envoyée en base64), le nom, le mot de passe, les autres appareils. Après chaque geste, la page se relit
// (router.refresh) : le menu du compte montre aussitôt le nouveau nom ou la nouvelle photo.

const COTE = 256;
const bouton = "rounded-full bg-marque px-4 py-2 text-[14px] font-bold text-on-marque disabled:opacity-60";
const boutonDiscret = "trait rounded-full bg-bg px-3.5 py-1.5 text-[13.5px] font-semibold text-ink hover:bg-hover disabled:opacity-60";

/** L'image choisie, lue par le navigateur ; refusée si elle ne se lit pas. */
function charger(fichier: File): Promise<HTMLImageElement> {
  return new Promise((resoudre, rejeter) => {
    const url = URL.createObjectURL(fichier);
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      resoudre(img);
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      rejeter(new Error(TA.photoIllisible));
    };
    img.src = url;
  });
}

const enBlob = (c: HTMLCanvasElement, type: string) => new Promise<Blob | null>((r) => c.toBlob(r, type, 0.85));

/** Le carré du centre, réduit à 256 × 256, en WebP ; en JPEG si le navigateur ne sait pas écrire du WebP. */
async function recadrer(fichier: File): Promise<Blob> {
  const img = await charger(fichier);
  const cote = Math.min(img.naturalWidth, img.naturalHeight);
  if (!cote) throw new Error(TA.photoIllisible);
  const toile = document.createElement("canvas");
  toile.width = COTE;
  toile.height = COTE;
  const ctx = toile.getContext("2d");
  if (!ctx) throw new Error(TA.photoIllisible);
  ctx.imageSmoothingQuality = "high";
  ctx.drawImage(img, (img.naturalWidth - cote) / 2, (img.naturalHeight - cote) / 2, cote, cote, 0, 0, COTE, COTE);
  const webp = await enBlob(toile, "image/webp");
  if (webp?.type === "image/webp") return webp;
  const jpeg = await enBlob(toile, "image/jpeg");
  if (!jpeg) throw new Error(TA.photoIllisible);
  return jpeg;
}

/** Les octets d'un Blob en base64, sans l'en-tête data:. */
function base64(blob: Blob): Promise<string> {
  return new Promise((resoudre, rejeter) => {
    const lecteur = new FileReader();
    lecteur.onload = () => resoudre(String(lecteur.result).split(",", 2)[1] ?? "");
    lecteur.onerror = () => rejeter(new Error(TA.photoIllisible));
    lecteur.readAsDataURL(blob);
  });
}

export function PhotoCompte({ nom, image }: { nom: string; image: string | null }) {
  const router = useRouter();
  const choix = useRef<HTMLInputElement>(null);
  const [apercu, setApercu] = useState<{ blob: Blob; url: string } | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);
  const [fait, setFait] = useState<string | null>(null);
  const [envoi, setEnvoi] = useState(false);

  useEffect(() => () => {
    if (apercu) URL.revokeObjectURL(apercu.url);
  }, [apercu]);

  async function choisir(fichier: File | undefined) {
    setErreur(null);
    setFait(null);
    if (!fichier) return;
    try {
      const blob = await recadrer(fichier);
      setApercu({ blob, url: URL.createObjectURL(blob) });
    } catch (e) {
      setErreur(refusDe(e).erreur);
    } finally {
      if (choix.current) choix.current.value = ""; // la même image peut se choisir de nouveau
    }
  }

  async function agir(geste: () => Promise<unknown>, texte: string) {
    setEnvoi(true);
    setErreur(null);
    try {
      await geste();
      setApercu(null);
      setFait(texte);
      router.refresh();
    } catch (e) {
      setErreur(refusDe(e).erreur);
    } finally {
      setEnvoi(false);
    }
  }

  const enregistrer = () =>
    agir(async () => envoyer("/api/admin/compte/photo", "PUT", { donnees: await base64(apercu!.blob), type: apercu!.blob.type }), TA.photoEnregistree);
  const retirer = () => agir(() => envoyer("/api/admin/compte/photo", "DELETE"), TA.photoRetiree);

  return (
    <section className={cadre}>
      <h2 className={titreBloc}>{TA.photo}</h2>
      <div className="flex flex-wrap items-center gap-4">
        <Avatar nom={nom} image={apercu?.url ?? image} taille={96} />
        <div className="flex min-w-0 flex-1 flex-col gap-2">
          <input
            ref={choix}
            id="compte-photo"
            type="file"
            accept="image/webp,image/jpeg,image/png,image/*"
            className="sr-only"
            onChange={(e) => choisir(e.target.files?.[0])}
          />
          <div className="flex flex-wrap gap-2">
            {apercu ? (
              <>
                <button type="button" onClick={enregistrer} disabled={envoi} className={bouton}>
                  {TA.enregistrerPhoto}
                </button>
                <button type="button" onClick={() => setApercu(null)} disabled={envoi} className={boutonDiscret}>
                  {TA.annuler}
                </button>
              </>
            ) : (
              <>
                <label htmlFor="compte-photo" className={boutonDiscret + " cursor-pointer has-[:focus-visible]:border-trait-fort"}>
                  {image ? TA.changerPhoto : TA.choisirPhoto}
                </label>
                {image && (
                  <button type="button" onClick={retirer} disabled={envoi} className={boutonDiscret}>
                    {TA.retirerPhoto}
                  </button>
                )}
              </>
            )}
          </div>
          <span className="text-[12.5px] text-faint">{TA.photoAide}</span>
        </div>
      </div>
      <ErreursChamps erreur={erreur} />
      <Fait texte={fait} />
    </section>
  );
}

export function NomCompte({ nom: initial, courriel }: { nom: string; courriel: string }) {
  const router = useRouter();
  const [nom, setNom] = useState(initial);
  const [erreur, setErreur] = useState<string | null>(null);
  const [fait, setFait] = useState<string | null>(null);
  const [envoi, setEnvoi] = useState(false);

  async function enregistrer(e: React.FormEvent) {
    e.preventDefault();
    setEnvoi(true);
    setErreur(null);
    setFait(null);
    try {
      const r = await envoyer<{ nom: string }>("/api/admin/compte", "PATCH", { nom });
      if (r) setNom(r.nom);
      setFait(TA.nomEnregistre);
      router.refresh();
    } catch (x) {
      setErreur(refusDe(x).erreur);
    } finally {
      setEnvoi(false);
    }
  }

  return (
    <form onSubmit={enregistrer} className={cadre}>
      <h2 className={titreBloc}>{TA.nomAffiche}</h2>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="compte-nom" className={etiquette}>{TA.nomAffiche}</Label>
        <Input id="compte-nom" value={nom} maxLength={80} autoComplete="name" onChange={(e) => setNom(e.target.value)} className={champ} />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="compte-courriel" className={etiquette}>{TA.courriel}</Label>
        <Input id="compte-courriel" value={courriel} readOnly className={champ + " text-muted-ink"} />
        <span className="text-[12.5px] text-faint">{TA.courrielFixe}</span>
      </div>
      <ErreursChamps erreur={erreur} />
      <Fait texte={fait} />
      <div>
        <button type="submit" disabled={envoi || !nom.trim() || nom.trim() === initial} className={bouton}>
          {TA.enregistrer}
        </button>
      </div>
    </form>
  );
}

export function MotDePasseCompte() {
  const [actuel, setActuel] = useState("");
  const [nouveau, setNouveau] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [erreur, setErreur] = useState<string | null>(null);
  const [fait, setFait] = useState<string | null>(null);
  const [envoi, setEnvoi] = useState(false);

  async function changer(e: React.FormEvent) {
    e.preventDefault();
    setErreur(null);
    setFait(null);
    if (nouveau !== confirmation) {
      setErreur(TA.confirmationDifferente);
      return;
    }
    setEnvoi(true);
    try {
      await envoyer("/api/admin/compte/mot-de-passe", "POST", { actuel, nouveau });
      setActuel("");
      setNouveau("");
      setConfirmation("");
      setFait(TA.motDePasseChange);
    } catch (x) {
      setErreur(refusDe(x).erreur);
    } finally {
      setEnvoi(false);
    }
  }

  const champMotDePasse = (id: string, titre: string, valeur: string, changer: (v: string) => void, auto: string) => (
    <div className="flex min-w-0 flex-col gap-1.5">
      <Label htmlFor={id} className={etiquette}>{titre}</Label>
      <Input id={id} type="password" value={valeur} autoComplete={auto} onChange={(e) => changer(e.target.value)} className={champ} />
    </div>
  );

  return (
    <form onSubmit={changer} className={cadre}>
      <h2 className={titreBloc}>{TA.motDePasse}</h2>
      <div className="grid gap-3 min-[1000px]:grid-cols-3">
        {champMotDePasse("compte-actuel", TA.motDePasseActuel, actuel, setActuel, "current-password")}
        {champMotDePasse("compte-nouveau", TA.nouveauMotDePasse, nouveau, setNouveau, "new-password")}
        {champMotDePasse("compte-confirmation", TA.confirmerMotDePasse, confirmation, setConfirmation, "new-password")}
      </div>
      <span className="text-[12.5px] text-faint">{TA.motDePasseCourt}</span>
      <ErreursChamps erreur={erreur} />
      <Fait texte={fait} />
      <div>
        <button type="submit" disabled={envoi || !actuel || !nouveau || !confirmation} className={bouton}>
          {TA.changerMotDePasse}
        </button>
      </div>
    </form>
  );
}

export function AutresAppareils() {
  const router = useRouter();
  return (
    <Confirmation
      titre={TA.deconnecterAutresTitre}
      effet={TA.effetDeconnecterAutres}
      bouton={TA.deconnecterAutres}
      onConfirmer={async () => {
        await envoyer("/api/admin/compte/sessions", "DELETE");
        router.refresh();
      }}
    >
      {TA.deconnecterAutres}
    </Confirmation>
  );
}
