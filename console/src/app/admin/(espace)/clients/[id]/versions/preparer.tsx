"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useDemande } from "@/components/admin/demande";
import { envoyer, refusDe } from "@/components/admin/envoyer";
import { ErreursChamps } from "@/components/admin/erreurs";
import { cadre, champ, etiquette, titreBloc, zoneTexte } from "@/components/admin/formulaire";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { estObjet, type ChampErreur } from "@/lib/admin/champs";
import { TA } from "@/lib/admin/textes";
import { differences, type Difference } from "@/lib/admin/versions";
import { TableauDifferences } from "./versions";

// Préparer un brouillon (versions.preparer) : des changements en JSON (« Valider » montre ce qui changerait, ou les erreurs
// champ par champ), ou un modèle par métier (un membre interne seulement). La base est nommée à chaque envoi : celle que
// l'aperçu compare (un externe ne la choisit pas : la version en service, sinon la dernière). Le brouillon créé s'ouvre (?v=).

type Resultat = { base: number; liste: Difference[]; manques: string[] };

export function Preparer({ id, externe, gabarits, champsSimples, base }: {
  id: string;
  externe: boolean;
  gabarits: { id: string; titre: string; description: string }[];
  /** Pour un externe : les réglages simples du catalogue (null : catalogue illisible). */
  champsSimples: string[] | null;
  /** La base du brouillon et sa configuration ; enService : c'est la version en service (sinon la dernière). */
  base: { numero: number; config: Record<string, unknown>; enService: boolean } | null;
}) {
  const { avant, fenetre } = useDemande();
  const router = useRouter();
  const modeles = !externe && gabarits.length > 0;
  const [mode, setMode] = useState<"json" | "modele">("json");
  const [texte, setTexte] = useState("");
  const [gabarit, setGabarit] = useState(gabarits[0]?.id ?? "");
  const [prenom, setPrenom] = useState("");
  const [resultat, setResultat] = useState<Resultat | null>(null);
  const [refus, setRefus] = useState<{ erreur: string; champs: ChampErreur[] } | null>(null);
  const [envoi, setEnvoi] = useState(false);
  const avecBase = base ? { base: base.numero } : {};

  /** Les changements tapés, s'ils forment un objet JSON ; sinon la phrase qui le dit. */
  function changements(): Record<string, unknown> | null {
    try {
      const v: unknown = JSON.parse(texte);
      if (estObjet(v)) return v;
    } catch {
      // lu plus bas : la même phrase
    }
    setRefus({ erreur: TA.changementsIllisibles, champs: [] });
    return null;
  }

  async function geste(faire: () => Promise<void>) {
    setEnvoi(true);
    setRefus(null);
    setResultat(null);
    try {
      await faire();
    } catch (e) {
      setRefus(refusDe(e));
    } finally {
      setEnvoi(false);
    }
  }

  const valider = () => {
    const ch = changements();
    if (ch) {
      void geste(async () => {
        const r = await envoyer<{ base: number; config: Record<string, unknown>; manques: string[] }>(
          `/api/admin/clients/${encodeURIComponent(id)}/valider`, "POST", { ...avecBase, changements: ch });
        if (!r) return;
        const avant = base && base.numero === r.base ? base.config : null;
        setResultat({ base: r.base, liste: differences(avant, r.config), manques: r.manques ?? [] });
      });
    }
  };

  const creer = (corps: Record<string, unknown>) =>
    geste(async () => {
      const v = await envoyer<{ version: number }>(`/api/admin/clients/${encodeURIComponent(id)}/versions`, "POST", { ...avecBase, ...corps });
      if (v) router.push(`/admin/clients/${encodeURIComponent(id)}/versions?v=${v.version}`);
    });

  function soumettre(e: React.FormEvent) {
    e.preventDefault();
    if (mode === "modele") {
      void creer({ gabarit, ...(prenom.trim() ? { nom_agent: prenom.trim() } : {}) });
      return;
    }
    const ch = changements();
    if (ch) void creer({ changements: ch });
  }

  const choisi = gabarits.find((g) => g.id === gabarit);
  return (
    <form noValidate onSubmit={avant(TA.confirmerBrouillon, TA.creerBrouillon, soumettre)} className={cadre}>
      {fenetre}
      <h2 className={titreBloc}>{TA.preparerBrouillon}</h2>
      {modeles && (
        <div role="radiogroup" className="flex flex-wrap gap-x-4 gap-y-1.5 text-[14px]">
          {(["json", "modele"] as const).map((m) => (
            <label key={m} className="flex items-center gap-2">
              <input type="radio" name="preparer-mode" checked={mode === m} onChange={() => { setMode(m); setRefus(null); setResultat(null); }} className="accent-marque" />
              {m === "json" ? TA.dApresChangements : TA.dApresModele}
            </label>
          ))}
        </div>
      )}
      {base && <p className="m-0 text-[13.5px] text-muted-ink">{base.enService ? TA.dApresEnService(base.numero) : TA.dApresVersion(base.numero)}</p>}
      {mode === "json" ? (
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="preparer-changements" className={etiquette}>{TA.changements}</Label>
          <textarea id="preparer-changements" value={texte} spellCheck={false} placeholder={TA.exempleChangements}
            onChange={(e) => { setTexte(e.target.value); setResultat(null); }} className={zoneTexte} />
          <span className="text-[12.5px] text-faint">{TA.changementsAide}</span>
          {externe && champsSimples && <span className="text-[12.5px] font-semibold text-warn">{TA.reglagesSimples(champsSimples.join(", "))}</span>}
        </div>
      ) : (
        <div className="grid gap-3.5 min-[761px]:grid-cols-2">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="preparer-gabarit" className={etiquette}>{TA.modeleMetier}</Label>
            <select id="preparer-gabarit" value={gabarit} onChange={(e) => setGabarit(e.target.value)} className={"trait " + champ}>
              {gabarits.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.titre}
                </option>
              ))}
            </select>
            {choisi && <span className="text-[12.5px] text-faint">{choisi.description}</span>}
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="preparer-prenom" className={etiquette}>{TA.prenomAgent}</Label>
            <Input id="preparer-prenom" value={prenom} maxLength={40} autoComplete="off" onChange={(e) => setPrenom(e.target.value)} className={champ} />
            <span className="text-[12.5px] text-faint">{TA.prenomAgentAide}</span>
          </div>
        </div>
      )}
      <ErreursChamps erreur={refus?.erreur ?? null} champs={refus?.champs} />
      {resultat && (
        <div role="status" className="flex flex-col gap-2">
          <p className="m-0 text-[13.5px] font-semibold text-ok">{TA.resultatValide(resultat.base)}</p>
          <TableauDifferences liste={resultat.liste} />
          {resultat.manques.length > 0 && <p className="m-0 text-[13.5px] font-semibold text-warn">{TA.manquesVersion(resultat.manques.join(" ; "))}</p>}
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        {mode === "json" && (
          <button type="button" onClick={valider} disabled={envoi} className="trait h-10 rounded-full bg-bg px-5 text-[14.5px] font-semibold text-ink hover:bg-hover disabled:opacity-60">
            {TA.valider}
          </button>
        )}
        <button type="submit" disabled={envoi} className="h-10 rounded-full bg-marque px-5 text-[14.5px] font-bold text-on-marque disabled:opacity-60">
          {TA.creerBrouillon}
        </button>
      </div>
    </form>
  );
}
