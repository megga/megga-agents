"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { envoyer, RefusEnvoi } from "@/components/admin/envoyer";
import { ErreursChamps } from "@/components/admin/erreurs";
import { champ, etiquette } from "@/components/admin/formulaire";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { ChampErreur, Tarifs } from "@/lib/admin/atelier";
import { TA } from "@/lib/admin/textes";

// Changer les tarifs (tarifs.regler) : la devise, chaque modèle (entrée, sortie, cache lu et écrit, par million de jetons),
// la voix et l'écoute. Les modèles vus dans l'activité sans tarif s'ajoutent d'un clic. L'atelier valide le tout et dit ce
// qui ne va pas, champ par champ ; la console n'en juge pas avant lui.

type Ligne = { modele: string; entree: string; sortie: string; cache_lecture: string; cache_ecriture: string };
type CleTarif = Exclude<keyof Ligne, "modele">;

const COLONNES: { cle: CleTarif; texte: string }[] = [
  { cle: "entree", texte: TA.entree },
  { cle: "sortie", texte: TA.sortie },
  { cle: "cache_lecture", texte: TA.cacheLecture },
  { cle: "cache_ecriture", texte: TA.cacheEcriture },
];

const texte = (n: number | null | undefined) => (n == null ? "" : String(n));

const lignesDe = (t: Tarifs): Ligne[] =>
  Object.entries(t.modeles).map(([modele, x]) => ({
    modele,
    entree: texte(x.entree),
    sortie: texte(x.sortie),
    cache_lecture: texte(x.cache_lecture),
    cache_ecriture: texte(x.cache_ecriture),
  }));

/** Un champ vide ne part pas : l'atelier dit qu'il manque, ou prend sa valeur par défaut (le cache, 0). */
const nombre = (s: string) => (s.trim() === "" ? undefined : Number(s));

function corpsDe(devise: string, lignes: Ligne[], voix: string, ecoute: string) {
  const modeles = lignes.map((l) => [l.modele, Object.fromEntries(COLONNES.map((c) => [c.cle, nombre(l[c.cle])]))]);
  return {
    devise: devise.trim(),
    modeles: Object.fromEntries(modeles),
    voix_par_1000_caracteres: nombre(voix) ?? null,
    par_vocal_entendu: nombre(ecoute) ?? null,
  };
}

/** Un tarif : un nombre positif, à virgule ; l'atelier le vérifie (le formulaire ne bloque rien avant lui). */
function ChampTarif({ id, titre, valeur, aide, onChange }: { id: string; titre: string; valeur: string; aide?: string; onChange: (v: string) => void }) {
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <Label htmlFor={id} className={etiquette}>{titre}</Label>
      <Input id={id} type="number" inputMode="decimal" step="any" min={0} value={valeur} onChange={(e) => onChange(e.target.value)} className={champ} />
      {aide && <span className="text-[12.5px] text-faint">{aide}</span>}
    </div>
  );
}

const titre2 = "m-0 text-[17px] font-extrabold";
const sousTitre = "m-0 text-[13.5px] text-muted-ink";

export function FormTarifs({ tarifs, proposes }: { tarifs: Tarifs; proposes: string[] }) {
  const router = useRouter();
  const [devise, setDevise] = useState(tarifs.devise);
  const [lignes, setLignes] = useState(() => lignesDe(tarifs));
  const [voix, setVoix] = useState(texte(tarifs.voix_par_1000_caracteres));
  const [ecoute, setEcoute] = useState(texte(tarifs.par_vocal_entendu));
  const [refus, setRefus] = useState<{ erreur: string; champs: ChampErreur[] } | null>(null);
  const [fait, setFait] = useState(false);
  const [envoi, setEnvoi] = useState(false);

  /** Les tarifs tels que l'atelier les a gardés (le cache laissé vide y vaut 0). */
  function remplir(t: Tarifs) {
    setDevise(t.devise);
    setLignes(lignesDe(t));
    setVoix(texte(t.voix_par_1000_caracteres));
    setEcoute(texte(t.par_vocal_entendu));
  }

  function changer(i: number, cle: CleTarif, v: string) {
    setLignes((l) => l.map((x, j) => (j === i ? { ...x, [cle]: v } : x)));
    setFait(false);
  }

  function ajouter(modele: string) {
    setLignes((l) => [...l, { modele, entree: "", sortie: "", cache_lecture: "", cache_ecriture: "" }]);
    setFait(false);
  }

  async function enregistrer(e: React.FormEvent) {
    e.preventDefault();
    setEnvoi(true);
    setRefus(null);
    setFait(false);
    try {
      const gardes = await envoyer<Tarifs>("/api/admin/tarifs", "PUT", corpsDe(devise, lignes, voix, ecoute));
      if (gardes) remplir(gardes);
      setFait(true);
      router.refresh(); // les coûts et les modèles sans tarif, relus avec les nouveaux tarifs
    } catch (e) {
      setRefus({ erreur: e instanceof Error ? e.message : TA.erreurInterne, champs: e instanceof RefusEnvoi ? e.champs : [] });
    } finally {
      setEnvoi(false);
    }
  }

  const aAjouter = proposes.filter((m) => !lignes.some((l) => l.modele === m));

  return (
    <form noValidate onSubmit={enregistrer} className="flex flex-col gap-5">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="tarifs-devise" className={etiquette}>{TA.devise}</Label>
        <Input id="tarifs-devise" value={devise} maxLength={3} autoCapitalize="characters" onChange={(e) => { setDevise(e.target.value); setFait(false); }}
          className={champ + " w-24"} />
      </div>

      <div className="flex flex-col gap-1">
        <h2 className={titre2}>{TA.parModele}</h2>
        <p className={sousTitre}>{TA.parMillion(tarifs.devise)}</p>
      </div>
      {!lignes.length && <p className="trait m-0 rounded-2xl bg-bg px-4 py-6 text-center text-[14px] text-faint">{TA.videTarifs}</p>}
      {lignes.map((l, i) => (
        <fieldset key={l.modele} className="trait m-0 flex min-w-0 flex-col gap-3 rounded-2xl bg-bg px-4 pt-3 pb-4">
          <legend className="float-left w-full text-[15px] font-bold break-all">{l.modele}</legend>
          <div className="grid grid-cols-2 gap-3 min-[900px]:grid-cols-4">
            {COLONNES.map((c) => (
              <ChampTarif key={c.cle} id={`tarif-${i}-${c.cle}`} titre={c.texte} valeur={l[c.cle]} onChange={(v) => changer(i, c.cle, v)} />
            ))}
          </div>
        </fieldset>
      ))}
      {aAjouter.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[13.5px] font-semibold text-warn">{TA.vusSansTarif}</span>
          {aAjouter.map((m) => (
            <button key={m} type="button" onClick={() => ajouter(m)} className="trait rounded-full bg-bg px-3 py-1 text-[13px] font-semibold break-all text-ink hover:bg-hover">
              {TA.ajouterModele(m)}
            </button>
          ))}
        </div>
      )}

      <h2 className={titre2}>{TA.voixEtEcoute}</h2>
      <div className="grid gap-3 min-[700px]:grid-cols-2">
        <ChampTarif id="tarif-voix" titre={TA.tarifVoix} valeur={voix} aide={TA.aideTarif(tarifs.devise)} onChange={(v) => { setVoix(v); setFait(false); }} />
        <ChampTarif id="tarif-ecoute" titre={TA.tarifEcoute} valeur={ecoute} aide={TA.aideTarif(tarifs.devise)} onChange={(v) => { setEcoute(v); setFait(false); }} />
      </div>

      <ErreursChamps erreur={refus?.erreur ?? null} champs={refus?.champs} />
      {fait && (
        <p role="status" className="m-0 text-[13.5px] font-semibold text-ok">
          {TA.tarifsEnregistres}
        </p>
      )}
      <button type="submit" disabled={envoi} className="self-start rounded-full bg-marque px-5 py-2 text-[14.5px] font-bold text-on-marque disabled:opacity-60">
        {TA.enregistrer}
      </button>
    </form>
  );
}
