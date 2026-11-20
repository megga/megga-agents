"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Confirmation } from "@/components/admin/confirmation";
import { useDemande } from "@/components/admin/demande";
import { envoyer, refusDe } from "@/components/admin/envoyer";
import { ErreursChamps, Fait } from "@/components/admin/erreurs";
import { cadre, champ, etiquette, titreBloc } from "@/components/admin/formulaire";
import { SecretUnique } from "@/components/admin/secret";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { Destination, RegleAlerte } from "@/lib/admin/atelier";
import type { ChampErreur } from "@/lib/admin/champs";
import { TA } from "@/lib/admin/textes";

// Régler les alertes envoyées (alertes.regler, périmètre complet) : les règles, envoyées en entier à l'atelier qui les
// valide champ par champ ; les destinations, ajoutées, essayées ou retirées une à une. Les clients visés d'une règle ne se
// changent pas ici : ils sont gardés tels quels (tous, par défaut).

type Mesures = Record<string, { libelle: string; unite: string }>;
type Ligne = Omit<RegleAlerte, "alerte" | "avertissement" | "fenetre_jours" | "rappel_heures"> & {
  alerte: string;
  avertissement: string;
  fenetre_jours: string;
  rappel_heures: string;
};

const COMPARAISONS = [">", ">=", "<", "<="] as const;
const texte = (n: number | null) => (n == null ? "" : String(n));
const nombre = (s: string) => (s.trim() === "" ? null : Number(s.replace(",", ".")));

const ligneDe = (r: RegleAlerte): Ligne => ({
  ...r,
  alerte: texte(r.alerte),
  avertissement: texte(r.avertissement),
  fenetre_jours: texte(r.fenetre_jours),
  rappel_heures: texte(r.rappel_heures),
});

const regleDe = (l: Ligne) => ({
  ...l,
  alerte: nombre(l.alerte),
  avertissement: nombre(l.avertissement),
  fenetre_jours: nombre(l.fenetre_jours) ?? 1,
  rappel_heures: nombre(l.rappel_heures) ?? 0,
});

/** Un identifiant libre, tiré du nom de la mesure : regle, regle-2… */
function idLibre(base: string, pris: string[]): string {
  const racine = base.replaceAll("_", "-").slice(0, 30) || "regle";
  let id = racine;
  for (let i = 2; pris.includes(id); i++) id = `${racine}-${i}`;
  return id;
}

function Champ({ id, titre, children }: { id: string; titre: string; children: React.ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <Label htmlFor={id} className={etiquette}>{titre}</Label>
      {children}
    </div>
  );
}

export function FormRegles({ regles, mesures, destinations, fenetreMax }: {
  regles: RegleAlerte[];
  mesures: Mesures;
  destinations: Destination[];
  fenetreMax: number;
}) {
  const { avant, fenetre } = useDemande();
  const router = useRouter();
  const [lignes, setLignes] = useState(() => regles.map(ligneDe));
  const [refus, setRefus] = useState<{ erreur: string; champs: ChampErreur[] } | null>(null);
  const [fait, setFait] = useState(false);
  const [envoi, setEnvoi] = useState(false);

  function changer(i: number, valeurs: Partial<Ligne>) {
    setLignes((l) => l.map((x, j) => (j === i ? { ...x, ...valeurs } : x)));
    setFait(false);
  }

  function ajouter() {
    const mesure = Object.keys(mesures)[0] ?? "tours";
    setLignes((l) => [...l, {
      id: idLibre(mesure, l.map((x) => x.id)), nom: mesures[mesure]?.libelle ?? mesure, mesure, comparaison: ">=", alerte: "1",
      avertissement: "", fenetre_jours: "1", sans_donnees: "ok", clients: [], destinations: [], rappel_heures: "0", en_pause: false,
    }]);
    setFait(false);
  }

  async function enregistrer() {
    setEnvoi(true);
    setRefus(null);
    setFait(false);
    try {
      const r = await envoyer<{ regles: RegleAlerte[] }>("/api/admin/alertes/regles", "PUT", lignes.map(regleDe));
      if (r) setLignes(r.regles.map(ligneDe));
      setFait(true);
      router.refresh();
    } catch (e) {
      setRefus(refusDe(e));
    } finally {
      setEnvoi(false);
    }
  }

  return (
    <form noValidate onSubmit={avant(TA.confirmerRegles, TA.enregistrer, enregistrer)} className="flex flex-col gap-4">
      {fenetre}
      {!lignes.length && <p className="trait m-0 rounded-2xl bg-bg px-4 py-6 text-center text-[14px] text-faint">{TA.videRegles}</p>}
      {lignes.map((l, i) => {
        const p = `regle-${i}`;
        return (
          <fieldset key={l.id} className="trait m-0 flex min-w-0 flex-col gap-3 rounded-2xl bg-bg px-4 pt-3 pb-4">
            <legend className="float-left flex w-full items-center gap-2">
              <Input id={`${p}-nom`} aria-label={TA.nomRegle} value={l.nom} maxLength={80} onChange={(e) => changer(i, { nom: e.target.value })}
                className={champ + " mr-auto min-w-0 flex-1 font-bold"} />
              <button type="button" onClick={() => { setLignes((x) => x.filter((_, j) => j !== i)); setFait(false); }}
                className="trait flex-none rounded-full bg-bg px-3 py-1 text-[13px] font-semibold text-ink hover:bg-hover">
                {TA.retirer}
              </button>
            </legend>
            <div className="grid grid-cols-2 gap-3 min-[900px]:grid-cols-4">
              <Champ id={`${p}-mesure`} titre={TA.mesure}>
                <select id={`${p}-mesure`} value={l.mesure} onChange={(e) => changer(i, { mesure: e.target.value })} className={"trait " + champ}>
                  {Object.entries(mesures).map(([k, m]) => <option key={k} value={k}>{m.libelle}</option>)}
                </select>
              </Champ>
              <Champ id={`${p}-comparaison`} titre={TA.comparaison}>
                <select id={`${p}-comparaison`} value={l.comparaison} onChange={(e) => changer(i, { comparaison: e.target.value as Ligne["comparaison"] })}
                  className={"trait " + champ}>
                  {COMPARAISONS.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </Champ>
              <Champ id={`${p}-alerte`} titre={TA.seuilAlerte}>
                <Input id={`${p}-alerte`} inputMode="decimal" value={l.alerte} onChange={(e) => changer(i, { alerte: e.target.value })} className={champ} />
              </Champ>
              <Champ id={`${p}-avertissement`} titre={TA.seuilAvertissement}>
                <Input id={`${p}-avertissement`} inputMode="decimal" value={l.avertissement} onChange={(e) => changer(i, { avertissement: e.target.value })}
                  className={champ} />
              </Champ>
              <Champ id={`${p}-fenetre`} titre={TA.joursFenetre}>
                <Input id={`${p}-fenetre`} type="number" min={1} max={fenetreMax} value={l.fenetre_jours} onChange={(e) => changer(i, { fenetre_jours: e.target.value })}
                  className={champ} />
              </Champ>
              <Champ id={`${p}-sans`} titre={TA.sansDonnees}>
                <select id={`${p}-sans`} value={l.sans_donnees} onChange={(e) => changer(i, { sans_donnees: e.target.value as Ligne["sans_donnees"] })}
                  className={"trait " + champ}>
                  {Object.entries(TA.sansDonneesChoix).map(([k, t]) => <option key={k} value={k}>{t}</option>)}
                </select>
              </Champ>
              <Champ id={`${p}-rappel`} titre={TA.rappelEnHeures}>
                <Input id={`${p}-rappel`} type="number" min={0} max={168} value={l.rappel_heures} onChange={(e) => changer(i, { rappel_heures: e.target.value })}
                  className={champ} />
              </Champ>
              <label className="flex items-center gap-2 self-end pb-2 text-[14px] font-semibold">
                <input type="checkbox" checked={l.en_pause} onChange={(e) => changer(i, { en_pause: e.target.checked })} />
                {TA.enPause}
              </label>
            </div>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
              <span className={etiquette}>{TA.destinations}</span>
              {!destinations.length && <span className="text-[13.5px] text-faint">{TA.aucuneDestination}</span>}
              {destinations.map((d) => (
                <label key={d.id} className="flex items-center gap-2 text-[14px]">
                  <input type="checkbox" checked={l.destinations.includes(d.id)}
                    onChange={(e) => changer(i, { destinations: e.target.checked ? [...l.destinations, d.id] : l.destinations.filter((x) => x !== d.id) })} />
                  {d.id}
                </label>
              ))}
            </div>
          </fieldset>
        );
      })}
      <ErreursChamps erreur={refus?.erreur ?? null} champs={refus?.champs} />
      <Fait texte={fait ? TA.reglesEnregistrees : null} />
      <div className="flex flex-wrap gap-2">
        <button type="submit" disabled={envoi} className="rounded-full bg-marque px-5 py-2 text-[14.5px] font-bold text-on-marque disabled:opacity-60">
          {TA.enregistrer}
        </button>
        <button type="button" onClick={ajouter} className="trait rounded-full bg-bg px-4 py-2 text-[14px] font-semibold text-ink hover:bg-hover">
          {TA.ajouterRegle}
        </button>
      </div>
    </form>
  );
}

export function GererDestinations({ destinations }: { destinations: Destination[] }) {
  const { avant, demander, fenetre } = useDemande();
  const router = useRouter();
  const [id, setId] = useState("");
  const [genre, setGenre] = useState<Destination["genre"]>("slack");
  const [adresse, setAdresse] = useState("");
  const [refus, setRefus] = useState<{ erreur: string; champs: ChampErreur[] } | null>(null);
  const [fait, setFait] = useState<string | null>(null);
  const [secret, setSecret] = useState<string | null>(null);

  async function ajouter() {
    setRefus(null);
    setFait(null);
    try {
      const r = await envoyer<Destination & { secret?: string }>("/api/admin/alertes/destinations", "POST", { id: id.trim(), genre, adresse: adresse.trim() });
      if (r?.secret) setSecret(r.secret);
      setId("");
      setAdresse("");
      router.refresh();
    } catch (e) {
      setRefus(refusDe(e));
    }
  }

  async function essayer(cible: string) {
    setRefus(null);
    setFait(null);
    try {
      await envoyer("/api/admin/alertes/destinations/" + encodeURIComponent(cible) + "/essai", "POST");
      setFait(TA.essaiParti);
    } catch (e) {
      setRefus(refusDe(e));
    }
  }

  return (
    <div className={cadre}>
      {fenetre}
      <SecretUnique valeur={secret} onFermer={() => setSecret(null)} />
      <h2 className={titreBloc}>{TA.destinations}</h2>
      {destinations.map((d) => (
        <div key={d.id} className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <b className="font-bold">{d.id}</b>
          <span className="text-[13.5px] text-muted-ink">{TA.genresDestination[d.genre] ?? d.genre}</span>
          <span className="mr-auto min-w-0 text-[13.5px] break-all text-muted-ink">{d.adresse}</span>
          <button type="button" onClick={() => demander(TA.confirmerEssai(d.id), TA.essayer, () => void essayer(d.id))}
            className="trait rounded-full bg-bg px-3 py-1 text-[13px] font-semibold text-ink hover:bg-hover">
            {TA.essayer}
          </button>
          <Confirmation titre={TA.confirmerRetraitDestination(d.id)} effet={TA.effetRetraitDestination} bouton={TA.retirer}
            onConfirmer={async () => {
              await envoyer("/api/admin/alertes/destinations/" + encodeURIComponent(d.id), "DELETE");
              router.refresh();
            }}>
            {TA.retirer}
          </Confirmation>
        </div>
      ))}
      <form noValidate onSubmit={avant(TA.confirmerDestination, TA.ajouterDestination, ajouter)} className="grid gap-3 min-[700px]:grid-cols-[1fr_1fr_2fr_auto] min-[700px]:items-end">
        <Champ id="destination-id" titre={TA.identifiant}>
          <Input id="destination-id" value={id} maxLength={40} onChange={(e) => setId(e.target.value)} className={champ} />
        </Champ>
        <Champ id="destination-genre" titre={TA.genre}>
          <select id="destination-genre" value={genre} onChange={(e) => setGenre(e.target.value as Destination["genre"])} className={"trait " + champ}>
            {Object.entries(TA.genresDestination).map(([k, t]) => <option key={k} value={k}>{t}</option>)}
          </select>
        </Champ>
        <Champ id="destination-adresse" titre={TA.adresse}>
          <Input id="destination-adresse" value={adresse} maxLength={500} onChange={(e) => setAdresse(e.target.value)} className={champ} />
        </Champ>
        <button type="submit" className="h-10 rounded-full bg-marque px-5 text-[14.5px] font-bold text-on-marque">{TA.ajouterDestination}</button>
      </form>
      <ErreursChamps erreur={refus?.erreur ?? null} champs={refus?.champs} />
      <Fait texte={fait} />
    </div>
  );
}
