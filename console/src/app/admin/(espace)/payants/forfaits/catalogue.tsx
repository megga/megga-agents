"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useDemande } from "@/components/admin/demande";
import { envoyer, refusDe } from "@/components/admin/envoyer";
import { ErreursChamps, Fait } from "@/components/admin/erreurs";
import { cadre, champ, etiquette } from "@/components/admin/formulaire";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { CatalogueForfaits, Forfait } from "@/lib/admin/atelier";
import type { ChampErreur } from "@/lib/admin/champs";
import { TA } from "@/lib/admin/textes";

// Le catalogue des forfaits (tarifs.regler, périmètre complet) : la devise, le multiple visé sur notre coût, puis chaque
// forfait. L'envoi remplace le catalogue entier ; l'atelier le valide, champ par champ, et refuse de retirer un forfait pris.

type Ligne = { id: string; nom: string; prix_mensuel: string; conversations: string; remise_annuelle: string; recharge_conversations: string; recharge_prix: string };

const texte = (n: number | null | undefined) => (n == null ? "" : String(n));
const nombre = (s: string) => (s.trim() === "" ? undefined : Number(s));

const ligneDe = (f: Forfait): Ligne => ({
  id: f.id, nom: f.nom, prix_mensuel: texte(f.prix_mensuel), conversations: texte(f.conversations), remise_annuelle: texte(f.remise_annuelle),
  recharge_conversations: texte(f.recharge?.conversations), recharge_prix: texte(f.recharge?.prix),
});

function corpsDe(devise: string, multiplicateur: string, retour: string, lignes: Ligne[]) {
  return {
    devise: devise.trim(),
    multiplicateur: nombre(multiplicateur),
    ...(retour.trim() ? { retour_paiement: retour.trim() } : {}),
    forfaits: lignes.map((l) => ({
      id: l.id.trim(), nom: l.nom.trim(), prix_mensuel: nombre(l.prix_mensuel), conversations: nombre(l.conversations),
      remise_annuelle: nombre(l.remise_annuelle) ?? 0,
      recharge: l.recharge_conversations.trim() || l.recharge_prix.trim()
        ? { conversations: nombre(l.recharge_conversations), prix: nombre(l.recharge_prix) } : null,
    })),
  };
}

const CHAMPS: { cle: keyof Ligne; titre: string; nombre: boolean }[] = [
  { cle: "id", titre: TA.identifiant, nombre: false },
  { cle: "nom", titre: TA.nomForfait, nombre: false },
  { cle: "prix_mensuel", titre: TA.prixMensuel, nombre: true },
  { cle: "conversations", titre: TA.conversationsParMois, nombre: true },
  { cle: "remise_annuelle", titre: TA.remiseAnnuelle, nombre: true },
  { cle: "recharge_conversations", titre: TA.rechargeConversations, nombre: true },
  { cle: "recharge_prix", titre: TA.rechargePrix, nombre: true },
];

export function FormCatalogue({ catalogue }: { catalogue: CatalogueForfaits }) {
  const { avant, fenetre } = useDemande();
  const router = useRouter();
  const [devise, setDevise] = useState(catalogue.devise);
  const [multiplicateur, setMultiplicateur] = useState(texte(catalogue.multiplicateur));
  const [retour, setRetour] = useState(catalogue.retour_paiement ?? "");
  const [lignes, setLignes] = useState(() => catalogue.forfaits.map(ligneDe));
  const [refus, setRefus] = useState<{ erreur: string; champs: ChampErreur[] } | null>(null);
  const [fait, setFait] = useState(false);
  const [envoi, setEnvoi] = useState(false);

  const changer = (i: number, cle: keyof Ligne, v: string) => {
    setLignes((l) => l.map((x, j) => (j === i ? { ...x, [cle]: v } : x)));
    setFait(false);
  };

  async function enregistrer() {
    setEnvoi(true);
    setRefus(null);
    setFait(false);
    try {
      const garde = await envoyer<CatalogueForfaits>("/api/admin/forfaits", "PUT", corpsDe(devise, multiplicateur, retour, lignes));
      if (garde) {
        setDevise(garde.devise);
        setMultiplicateur(texte(garde.multiplicateur));
        setRetour(garde.retour_paiement ?? "");
        setLignes(garde.forfaits.map(ligneDe));
      }
      setFait(true);
      router.refresh();
    } catch (e) {
      setRefus(refusDe(e));
    } finally {
      setEnvoi(false);
    }
  }

  return (
    <form onSubmit={avant(TA.forfaitsQuestion, TA.enregistrer, enregistrer)} className="flex flex-col gap-4">
      <div className="grid grid-cols-[repeat(auto-fill,minmax(160px,1fr))] gap-3">
        <div className="flex min-w-0 flex-col gap-1.5">
          <Label htmlFor="forfaits-devise" className={etiquette}>{TA.devise}</Label>
          <Input id="forfaits-devise" value={devise} maxLength={3} onChange={(e) => setDevise(e.target.value.toUpperCase())} className={champ} />
        </div>
        <div className="flex min-w-0 flex-col gap-1.5">
          <Label htmlFor="forfaits-multiplicateur" className={etiquette}>{TA.multiplicateur}</Label>
          <Input id="forfaits-multiplicateur" type="number" inputMode="decimal" step="any" min={0} value={multiplicateur}
            onChange={(e) => setMultiplicateur(e.target.value)} className={champ} />
        </div>
        <div className="flex min-w-0 flex-col gap-1.5">
          <Label htmlFor="forfaits-retour" className={etiquette}>{TA.retourPaiement}</Label>
          <Input id="forfaits-retour" type="url" inputMode="url" placeholder="https://megga.ai" value={retour}
            onChange={(e) => setRetour(e.target.value)} className={champ} />
        </div>
      </div>
      {lignes.map((l, i) => (
        <fieldset key={i} className={cadre + " m-0"}>
          <div className="grid grid-cols-[repeat(auto-fill,minmax(160px,1fr))] gap-3">
            {CHAMPS.map((c) => (
              <div key={c.cle} className="flex min-w-0 flex-col gap-1.5">
                <Label htmlFor={`forfait-${i}-${c.cle}`} className={etiquette}>{c.titre}</Label>
                <Input id={`forfait-${i}-${c.cle}`} type={c.nombre ? "number" : "text"} inputMode={c.nombre ? "decimal" : undefined}
                  step={c.nombre ? "any" : undefined} min={c.nombre ? 0 : undefined} value={l[c.cle]}
                  onChange={(e) => changer(i, c.cle, e.target.value)} className={champ} />
              </div>
            ))}
          </div>
          <div>
            <button type="button" onClick={() => { setLignes((x) => x.filter((_, j) => j !== i)); setFait(false); }}
              className="rounded-full px-3 py-1.5 text-[13.5px] font-semibold text-muted-ink hover:bg-hover hover:text-ink">
              {TA.retirer}
            </button>
          </div>
        </fieldset>
      ))}
      <ErreursChamps erreur={refus?.erreur ?? null} champs={refus?.champs} />
      <Fait texte={fait ? TA.forfaitsEnregistres : null} />
      <div className="flex flex-wrap gap-2">
        <button type="button" disabled={lignes.length >= 20}
          onClick={() => { setLignes((x) => [...x, { id: "", nom: "", prix_mensuel: "", conversations: "", remise_annuelle: "", recharge_conversations: "", recharge_prix: "" }]); setFait(false); }}
          className="trait rounded-full px-4 py-2 text-[14px] font-semibold text-ink hover:bg-hover disabled:opacity-50">
          {TA.ajouterForfait}
        </button>
        <button type="submit" disabled={envoi} className="rounded-full bg-marque px-4 py-2 text-[14px] font-bold text-on-marque disabled:opacity-60">
          {TA.enregistrer}
        </button>
      </div>
      {fenetre}
    </form>
  );
}
