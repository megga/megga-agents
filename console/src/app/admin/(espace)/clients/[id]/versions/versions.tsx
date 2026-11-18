"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Confirmation } from "@/components/admin/confirmation";
import { envoyer, RefusEnvoi } from "@/components/admin/envoyer";
import { ErreursChamps } from "@/components/admin/erreurs";
import { champ, etiquette, zoneTexte } from "@/components/admin/formulaire";
import { Tableau } from "@/components/admin/tableau";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { ChampErreur } from "@/lib/admin/champs";
import { TA } from "@/lib/admin/textes";
import { differences, enTexte, type Difference } from "@/lib/admin/versions";

// Les gestes de l'onglet Versions : préparer un brouillon (des changements en JSON, validés par l'atelier, ou un modèle par
// métier), l'essayer, le mettre en service (ou revenir à une version, ou forcer). Chaque route refait les contrôles : l'écran
// ne fait que les suivre (un externe ne voit ni le modèle par métier ni les gestes de pilotage).

const adresse = (id: string) => `/api/admin/clients/${encodeURIComponent(id)}`;
const estObjet = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);
const refusDe = (e: unknown) => ({ erreur: e instanceof Error ? e.message : TA.erreurInterne, champs: e instanceof RefusEnvoi ? e.champs : [] });

/** Ce qui change d'une configuration à l'autre : le réglage, avant, après (repliés sous le réglage dans un cadre étroit). */
export function TableauDifferences({ liste }: { liste: Difference[] }) {
  const valeur = (v: unknown) => <span className="whitespace-pre-wrap wrap-anywhere">{enTexte(v)}</span>;
  return (
    <Tableau
      colonnes={[TA.reglage, TA.avant, TA.apres]}
      vide={TA.rienNeChange}
      replier={[1, 2]}
      lignes={liste.map((d) => [<b key="champ" className="font-bold wrap-anywhere">{d.champ}</b>, valeur(d.avant), valeur(d.apres)])}
    />
  );
}

type Geste = { titre: string; bouton: string; effet: string; forcer: boolean };

/** Le geste de pilotage d'une version, s'il y en a un ; l'effet dit ce qui se passe (conteneur, ou ordre à l'installation). */
export function gesteDe(v: { numero: number; etat: "brouillon" | "publiee"; essais: number }, enService: number | null, ecart: boolean, ordre: boolean): Geste | null {
  const n = v.numero;
  const effet = ordre ? TA.effetOrdre(n) : TA.effetActiver(n);
  if (v.etat === "brouillon" && v.essais === 0) return { titre: TA.forcerTitre(n), bouton: TA.forcer, effet: `${TA.jamaisEssayee} ${effet}`, forcer: true };
  if (n === enService) return ecart ? { titre: TA.relancerTitre(n), bouton: TA.mettreEnService, effet: `${TA.ecartARelancer} ${effet}`, forcer: false } : null;
  if (v.etat === "publiee" && enService !== null && n < enService) return { titre: TA.revenirTitre(n), bouton: TA.revenirVersion, effet, forcer: false };
  return { titre: TA.mettreEnServiceTitre(n), bouton: TA.mettreEnService, effet, forcer: false };
}

/** Mettre en service, revenir à une version, forcer, ou relancer après un écart (clients.piloter), derrière une confirmation. */
export function GestesVersion({ id, version, enService, ecart, ordre }: {
  id: string;
  version: { numero: number; etat: "brouillon" | "publiee"; essais: number };
  enService: number | null;
  ecart: boolean;
  /** Hors Cloudflare : un ordre signé part à l'installation au lieu de redémarrer un conteneur. */
  ordre: boolean;
}) {
  const router = useRouter();
  const [fait, setFait] = useState<string | null>(null);
  const geste = gesteDe(version, enService, ecart, ordre);
  if (!geste && !fait) return null;
  return (
    <div className="flex flex-wrap items-center gap-3">
      {geste && (
        <Confirmation
          titre={geste.titre}
          effet={geste.effet}
          bouton={geste.bouton}
          onConfirmer={async () => {
            const r = await envoyer<{ pilotage?: { ordre?: number } }>(`${adresse(id)}/versions/${version.numero}/activer`, "POST",
              geste.forcer ? { forcer: true } : {});
            const ordrePart = typeof r?.pilotage?.ordre === "number" ? ` ${TA.ordreParti(r.pilotage.ordre)}` : "";
            setFait(TA.enServiceFait(version.numero) + ordrePart);
            router.refresh();
          }}
        >
          {geste.bouton}
        </Confirmation>
      )}
      {fait && (
        <p role="status" className="m-0 text-[13.5px] font-semibold text-ok">
          {fait}
        </p>
      )}
    </div>
  );
}

const nouvelleConversation = () => "admin-" + Math.random().toString(36).slice(2, 10);

/** Une petite conversation avec un brouillon, hors WhatsApp ; changer de rôle en commence une autre. */
export function Essai({ id, numero, roles }: { id: string; numero: number; roles: string[] }) {
  const router = useRouter();
  const [role, setRole] = useState<string | null>(roles.includes("visiteur") ? "visiteur" : (roles[0] ?? null));
  const [conversation, setConversation] = useState(nouvelleConversation);
  const [echanges, setEchanges] = useState<{ message: string; reponse: string }[]>([]);
  const [message, setMessage] = useState("");
  const [erreur, setErreur] = useState<string | null>(null);
  const [envoi, setEnvoi] = useState(false);

  function changerRole(r: string) {
    setRole(r);
    setConversation(nouvelleConversation());
    setEchanges([]);
  }

  async function essayer(e: React.FormEvent) {
    e.preventDefault();
    const texte = message.trim();
    if (!texte) return;
    setEnvoi(true);
    setErreur(null);
    try {
      const r = await envoyer<{ reponse: string }>(`${adresse(id)}/versions/${numero}/essai`, "POST", { message: texte, conversation, ...(role ? { role } : {}) });
      setEchanges((l) => [...l, { message: texte, reponse: r?.reponse ?? "" }]);
      setMessage("");
      router.refresh(); // le nombre d'essais : « Forcer » devient « Mettre en service »
    } catch (e) {
      setErreur(refusDe(e).erreur);
    } finally {
      setEnvoi(false);
    }
  }

  return (
    <form onSubmit={essayer} className="flex flex-col gap-3">
      <h3 className="m-0 text-[16px] font-extrabold">{TA.essaiTitre(numero)}</h3>
      <p className="m-0 text-[13.5px] text-warn">{TA.essaiConsomme}</p>
      {roles.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={`essai-${numero}-role`} className={etiquette}>{TA.roleEssai}</Label>
          <select id={`essai-${numero}-role`} value={role ?? ""} onChange={(e) => changerRole(e.target.value)} className={"trait w-fit " + champ}>
            {roles.map((r) => (
              <option key={r} value={r}>
                {TA.rolesEssai[r] ?? r}
              </option>
            ))}
          </select>
        </div>
      )}
      {echanges.length > 0 && (
        <ol className="m-0 flex list-none flex-col gap-2 p-0">
          {echanges.flatMap((x, i) => [
            <li key={`${i}-m`} className="max-w-[90%] self-start rounded-[20px_20px_20px_6px] bg-hover px-4 py-2.5 whitespace-pre-wrap wrap-anywhere">
              <span className="sr-only">{TA.recu} </span>
              {x.message}
            </li>,
            <li key={`${i}-r`} className="max-w-[90%] self-end rounded-[20px_20px_6px_20px] bg-soft px-4 py-2.5 whitespace-pre-wrap wrap-anywhere">
              <span className="sr-only">{TA.envoye} </span>
              {x.reponse}
            </li>,
          ])}
        </ol>
      )}
      <div className="flex flex-wrap items-end gap-2">
        <div className="flex min-w-0 flex-1 flex-col gap-1.5">
          <Label htmlFor={`essai-${numero}-message`} className={etiquette}>{TA.votreMessage}</Label>
          <Input id={`essai-${numero}-message`} value={message} maxLength={4000} autoComplete="off" onChange={(e) => setMessage(e.target.value)} className={champ} />
        </div>
        <button type="submit" disabled={envoi || !message.trim()} className="h-10 rounded-full bg-marque px-5 text-[14.5px] font-bold text-on-marque disabled:opacity-60">
          {TA.envoyer}
        </button>
      </div>
      <ErreursChamps erreur={erreur} />
    </form>
  );
}

type Resultat = { base: number; liste: Difference[]; manques: string[] };

/**
 * Préparer un brouillon : des changements en JSON (« Valider » montre ce qui changerait, ou les erreurs champ par champ), ou
 * un modèle par métier (un membre interne seulement). Le brouillon créé s'ouvre (?v=).
 */
export function Preparer({ id, externe, gabarits, champsSimples, derniere }: {
  id: string;
  externe: boolean;
  gabarits: { id: string; titre: string; description: string }[];
  /** Pour un externe : les réglages simples du catalogue (null : catalogue illisible). */
  champsSimples: string[] | null;
  /** La dernière version, base par défaut des changements, et sa configuration. */
  derniere: { numero: number; config: Record<string, unknown> } | null;
}) {
  const router = useRouter();
  const modeles = !externe && gabarits.length > 0;
  const [mode, setMode] = useState<"json" | "modele">("json");
  const [texte, setTexte] = useState("");
  const [gabarit, setGabarit] = useState(gabarits[0]?.id ?? "");
  const [prenom, setPrenom] = useState("");
  const [resultat, setResultat] = useState<Resultat | null>(null);
  const [refus, setRefus] = useState<{ erreur: string; champs: ChampErreur[] } | null>(null);
  const [envoi, setEnvoi] = useState(false);

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
        const r = await envoyer<{ base: number; config: Record<string, unknown>; manques: string[] }>(`${adresse(id)}/valider`, "POST", { changements: ch });
        if (!r) return;
        const avant = derniere && derniere.numero === r.base ? derniere.config : null;
        setResultat({ base: r.base, liste: differences(avant, r.config), manques: r.manques ?? [] });
      });
    }
  };

  const creer = (corps: Record<string, unknown>) =>
    geste(async () => {
      const v = await envoyer<{ version: number }>(`${adresse(id)}/versions`, "POST", corps);
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
    <form noValidate onSubmit={soumettre} className="trait flex flex-col gap-3.5 rounded-2xl bg-bg px-5 pt-4 pb-5">
      <h2 className="m-0 text-[18px] font-extrabold">{TA.preparerBrouillon}</h2>
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
      {derniere && <p className="m-0 text-[13.5px] text-muted-ink">{TA.dApresVersion(derniere.numero)}</p>}
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
