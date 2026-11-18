"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { envoyer, RefusEnvoi } from "@/components/admin/envoyer";
import { ErreursChamps } from "@/components/admin/erreurs";
import { champ, etiquette, zoneTexte } from "@/components/admin/formulaire";
import { Pastille, PastillesEtat, type Etat } from "@/components/admin/pastille";
import { Tableau } from "@/components/admin/tableau";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { ChampErreur } from "@/lib/admin/champs";
import type { EtatClient } from "@/lib/admin/suivi";
import { TA } from "@/lib/admin/textes";

// La liste des clients du moteur, déjà bornée au périmètre côté serveur : la recherche se fait ici, dans le navigateur
// (entreprise, agent, identifiant). Dans un cadre étroit, les colonnes se replient sous l'entreprise. « Nouveau client » pour
// qui peut créer : d'après un modèle par métier, ou d'une configuration entière ; l'atelier dit ce qui ne va pas, champ par champ.

export type LigneClient = {
  id: string;
  entreprise: string | null;
  agent: string | null;
  version: string;
  etat: EtatClient;
  installation: { etat: Etat; texte: string };
};

/** Ce que le formulaire du nouveau client propose : les modèles par métier et les zones du catalogue. */
export type Creation = { gabarits: { id: string; titre: string }[]; zones: string[] };

const trouve = (l: LigneClient, q: string) => [l.entreprise, l.agent, l.id].some((v) => v?.toLocaleLowerCase("fr").includes(q));
const estObjet = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);

function Champ({ id, titre, aide, valeur, onChange }: { id: string; titre: string; aide?: string; valeur: string; onChange: (v: string) => void }) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id} className={etiquette}>{titre}</Label>
      <Input id={id} value={valeur} autoComplete="off" onChange={(e) => onChange(e.target.value)} className={champ} />
      {aide && <span className="text-[12.5px] text-faint">{aide}</span>}
    </div>
  );
}

function NouveauClient({ creation }: { creation: Creation }) {
  const router = useRouter();
  const [mode, setMode] = useState<"modele" | "config">("modele");
  const [gabarit, setGabarit] = useState(creation.gabarits[0]?.id ?? "");
  const [id, setId] = useState("");
  const [entreprise, setEntreprise] = useState("");
  const [zone, setZone] = useState(creation.zones.includes("europe") ? "europe" : (creation.zones[0] ?? ""));
  const [numero, setNumero] = useState("");
  const [prenom, setPrenom] = useState("");
  const [config, setConfig] = useState("");
  const [refus, setRefus] = useState<{ erreur: string; champs: ChampErreur[] } | null>(null);
  const [envoi, setEnvoi] = useState(false);

  function corps(): Record<string, unknown> | null {
    if (mode === "modele") {
      const client = { id: id.trim(), entreprise: entreprise.trim(), zone, ...(numero.trim() ? { numero_id: numero.trim() } : {}) };
      return { gabarit, client, nom_agent: prenom.trim() };
    }
    try {
      const c: unknown = JSON.parse(config);
      if (estObjet(c)) return { config: c };
    } catch {
      // la même phrase, plus bas
    }
    setRefus({ erreur: TA.configurationIllisible, champs: [] });
    return null;
  }

  async function creer(e: React.FormEvent) {
    e.preventDefault();
    setRefus(null);
    const c = corps();
    if (!c) return;
    setEnvoi(true);
    try {
      const r = await envoyer<{ client: string }>("/api/admin/clients", "POST", c);
      if (r) router.push(`/admin/clients/${encodeURIComponent(r.client)}/versions`);
    } catch (e) {
      setRefus({ erreur: e instanceof Error ? e.message : TA.erreurInterne, champs: e instanceof RefusEnvoi ? e.champs : [] });
    } finally {
      setEnvoi(false);
    }
  }

  return (
    <form noValidate onSubmit={creer} className="trait flex flex-col gap-3.5 rounded-2xl bg-bg px-5 pt-4 pb-5">
      <h2 className="m-0 text-[18px] font-extrabold">{TA.nouveauClient}</h2>
      <div role="radiogroup" className="flex flex-wrap gap-x-4 gap-y-1.5 text-[14px]">
        {(["modele", "config"] as const).map((m) => (
          <label key={m} className="flex items-center gap-2">
            <input type="radio" name="nouveau-mode" checked={mode === m} onChange={() => { setMode(m); setRefus(null); }} className="accent-marque" />
            {m === "modele" ? TA.dApresModele : TA.configEntiere}
          </label>
        ))}
      </div>
      {mode === "modele" ? (
        <div className="grid gap-3.5 min-[761px]:grid-cols-2">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="nouveau-gabarit" className={etiquette}>{TA.modeleMetier}</Label>
            <select id="nouveau-gabarit" value={gabarit} onChange={(e) => setGabarit(e.target.value)} className={"trait " + champ}>
              {creation.gabarits.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.titre}
                </option>
              ))}
            </select>
          </div>
          <Champ id="nouveau-id" titre={TA.identifiant} aide={TA.identifiantAide} valeur={id} onChange={setId} />
          <Champ id="nouveau-entreprise" titre={TA.entreprise} valeur={entreprise} onChange={setEntreprise} />
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="nouveau-zone" className={etiquette}>{TA.zone}</Label>
            <select id="nouveau-zone" value={zone} onChange={(e) => setZone(e.target.value)} className={"trait " + champ}>
              {creation.zones.map((z) => (
                <option key={z} value={z}>
                  {TA.zones[z] ?? z}
                </option>
              ))}
            </select>
          </div>
          <Champ id="nouveau-numero" titre={TA.numeroWhatsapp} aide={TA.numeroWhatsappAide} valeur={numero} onChange={setNumero} />
          <Champ id="nouveau-prenom" titre={TA.prenomAgent} valeur={prenom} onChange={setPrenom} />
        </div>
      ) : (
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="nouveau-config" className={etiquette}>{TA.configurationCollee}</Label>
          <textarea id="nouveau-config" value={config} spellCheck={false} onChange={(e) => setConfig(e.target.value)} className={zoneTexte + " min-h-48"} />
          <span className="text-[12.5px] text-faint">{TA.configurationAide}</span>
        </div>
      )}
      <ErreursChamps erreur={refus?.erreur ?? null} champs={refus?.champs} />
      <button type="submit" disabled={envoi} className="h-10 self-start rounded-full bg-marque px-5 text-[14.5px] font-bold text-on-marque disabled:opacity-60">
        {TA.creerClient}
      </button>
    </form>
  );
}

export function Clients({ lignes, creation }: { lignes: LigneClient[]; creation: Creation | null }) {
  const [recherche, setRecherche] = useState("");
  const [nouveau, setNouveau] = useState(false);
  const q = recherche.trim().toLocaleLowerCase("fr");
  const vues = q ? lignes.filter((l) => trouve(l, q)) : lignes;
  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <Input
          type="search"
          aria-label={TA.rechercherClient}
          placeholder={TA.rechercherClient}
          value={recherche}
          onChange={(e) => setRecherche(e.target.value)}
          className={champ + " max-w-[360px] min-w-48 flex-1"}
        />
        {creation && (
          <button type="button" aria-expanded={nouveau} onClick={() => setNouveau((n) => !n)}
            className="trait h-10 rounded-full bg-bg px-4 text-[14px] font-semibold whitespace-nowrap text-ink hover:bg-hover aria-expanded:bg-hover">
            {TA.nouveauClient}
          </button>
        )}
      </div>
      {creation && nouveau && <NouveauClient creation={creation} />}
      <Tableau
        colonnes={[TA.entreprise, TA.agent, TA.identifiant, TA.version, TA.etat, TA.installation]}
        vide={lignes.length ? TA.aucunClientTrouve : TA.videClients}
        replier={[1, 2, 3, 4, 5]}
        lignes={vues.map((l) => [
          <Link key="entreprise" href={`/admin/clients/${encodeURIComponent(l.id)}`} className="font-bold text-ink hover:underline">
            {l.entreprise || l.id}
          </Link>,
          <span key="agent">{l.agent ?? ""}</span>,
          <span key="id" className="whitespace-nowrap text-muted-ink">{l.id}</span>,
          <span key="version" className="whitespace-nowrap">{l.version}</span>,
          <PastillesEtat key="etat" etat={l.etat} />,
          <Pastille key="installation" etat={l.installation.etat} texte={l.installation.texte} />,
        ])}
      />
    </>
  );
}
