"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Confirmation } from "@/components/admin/confirmation";
import { useDemande } from "@/components/admin/demande";
import { envoyer, refusDe } from "@/components/admin/envoyer";
import { ErreursChamps, Fait } from "@/components/admin/erreurs";
import { cadre, champ, etiquette, titreBloc } from "@/components/admin/formulaire";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { Abonnement, Forfait } from "@/lib/admin/atelier";
import type { ChampErreur } from "@/lib/admin/champs";
import { TA } from "@/lib/admin/textes";

// L'abonnement d'un client (tarifs.regler) et ses recharges achetées hors Stripe. Choisir un client déjà abonné reprend son
// abonnement ; chaque envoi se confirme, l'atelier valide.

type ClientChoix = { id: string; nom: string; abonnement: Abonnement | null };

const aujourdhui = () => new Date().toISOString().slice(0, 10);
const vide = (forfait: string): Abonnement => ({ forfait, rythme: "mensuel", statut: "essai", debut: aujourdhui(), seuil_recharge: null });
const adresse = (id: string, quoi: string) => `/api/admin/clients/${encodeURIComponent(id)}/${quoi}`;

function Champ({ id, titre, children }: { id: string; titre: string; children: React.ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <Label htmlFor={id} className={etiquette}>{titre}</Label>
      {children}
    </div>
  );
}

export function FormAbonnement({ clients, forfaits }: { clients: ClientChoix[]; forfaits: Forfait[] }) {
  const router = useRouter();
  const { avant, fenetre } = useDemande();
  const [client, setClient] = useState("");
  const [a, setA] = useState<Abonnement>(() => vide(forfaits[0]?.id ?? ""));
  const [seuil, setSeuil] = useState("");
  const [refus, setRefus] = useState<{ erreur: string; champs: ChampErreur[] } | null>(null);
  const [fait, setFait] = useState<string | null>(null);
  const choisi = clients.find((c) => c.id === client) ?? null;

  function choisir(id: string) {
    setClient(id);
    const existant = clients.find((c) => c.id === id)?.abonnement ?? null;
    setA(existant ?? vide(forfaits[0]?.id ?? ""));
    setSeuil(existant?.seuil_recharge == null ? "" : String(existant.seuil_recharge));
    setRefus(null);
    setFait(null);
  }

  async function enregistrer() {
    setRefus(null);
    setFait(null);
    try {
      await envoyer(adresse(client, "abonnement"), "PUT", { ...a, seuil_recharge: seuil.trim() === "" ? null : Number(seuil) });
      setFait(TA.abonnementEnregistre);
      router.refresh();
    } catch (e) {
      setRefus(refusDe(e));
    }
  }

  return (
    <section className={cadre}>
      <h2 className={titreBloc}>{TA.abonnerClient}</h2>
      <form onSubmit={avant(TA.abonnementQuestion, TA.enregistrer, enregistrer)} className="flex flex-col gap-3">
        <div className="grid grid-cols-[repeat(auto-fill,minmax(160px,1fr))] gap-3">
          <Champ id="abonnement-client" titre={TA.client}>
            <select id="abonnement-client" required value={client} onChange={(e) => choisir(e.target.value)} className={"trait " + champ}>
              <option value="" disabled>{TA.choisirClient}</option>
              {clients.map((c) => <option key={c.id} value={c.id}>{c.nom}</option>)}
            </select>
          </Champ>
          <Champ id="abonnement-forfait" titre={TA.forfait}>
            <select id="abonnement-forfait" value={a.forfait} onChange={(e) => setA({ ...a, forfait: e.target.value })} className={"trait " + champ}>
              {forfaits.map((f) => <option key={f.id} value={f.id}>{f.nom}</option>)}
            </select>
          </Champ>
          <Champ id="abonnement-rythme" titre={TA.rythme}>
            <select id="abonnement-rythme" value={a.rythme} onChange={(e) => setA({ ...a, rythme: e.target.value as Abonnement["rythme"] })} className={"trait " + champ}>
              {(["mensuel", "annuel"] as const).map((r) => <option key={r} value={r}>{TA.rythmes[r]}</option>)}
            </select>
          </Champ>
          <Champ id="abonnement-statut" titre={TA.statut}>
            <select id="abonnement-statut" value={a.statut} onChange={(e) => setA({ ...a, statut: e.target.value as Abonnement["statut"] })} className={"trait " + champ}>
              {(["essai", "actif", "retard", "parti"] as const).map((s) => <option key={s} value={s}>{TA.statutsAbonnement[s]}</option>)}
            </select>
          </Champ>
          <Champ id="abonnement-debut" titre={TA.debutAbonnement}>
            <Input id="abonnement-debut" type="date" value={a.debut} onChange={(e) => setA({ ...a, debut: e.target.value })} className={champ} />
          </Champ>
          <Champ id="abonnement-seuil" titre={TA.seuilRecharge}>
            <Input id="abonnement-seuil" type="number" inputMode="numeric" min={0} value={seuil} onChange={(e) => setSeuil(e.target.value)} className={champ} />
          </Champ>
        </div>
        <ErreursChamps erreur={refus?.erreur ?? null} champs={refus?.champs} />
        <Fait texte={fait} />
        <div className="flex flex-wrap gap-2">
          <button type="submit" disabled={!client} className="rounded-full bg-marque px-4 py-2 text-[14px] font-bold text-on-marque disabled:opacity-60">
            {TA.enregistrer}
          </button>
          {choisi?.abonnement && (
            <Confirmation
              titre={TA.retirerAbonnementTitre}
              effet={TA.retirerAbonnementEffet}
              bouton={TA.retirer}
              onConfirmer={async () => {
                await envoyer(adresse(client, "abonnement"), "DELETE");
                setFait(TA.abonnementRetire);
                router.refresh();
              }}
            >
              {TA.retirer}
            </Confirmation>
          )}
        </div>
      </form>
      {fenetre}
    </section>
  );
}

export function FormRecharge({ clients }: { clients: ClientChoix[] }) {
  const router = useRouter();
  const { avant, fenetre } = useDemande();
  const [client, setClient] = useState("");
  const [conversations, setConversations] = useState("");
  const [prix, setPrix] = useState("");
  const [refus, setRefus] = useState<{ erreur: string; champs: ChampErreur[] } | null>(null);
  const [fait, setFait] = useState<string | null>(null);

  async function ajouter() {
    setRefus(null);
    setFait(null);
    try {
      await envoyer(adresse(client, "recharges"), "POST", { conversations: Number(conversations), prix: Number(prix) });
      setFait(TA.rechargeAjoutee);
      setConversations("");
      setPrix("");
      router.refresh();
    } catch (e) {
      setRefus(refusDe(e));
    }
  }

  return (
    <section className={cadre}>
      <h2 className={titreBloc}>{TA.ajouterRecharge}</h2>
      <form onSubmit={avant(TA.rechargeQuestion, TA.ajouterRecharge, ajouter)} className="flex flex-col gap-3">
        <div className="grid grid-cols-[repeat(auto-fill,minmax(160px,1fr))] gap-3">
          <Champ id="recharge-client" titre={TA.client}>
            <select id="recharge-client" required value={client} onChange={(e) => setClient(e.target.value)} className={"trait " + champ}>
              <option value="" disabled>{TA.choisirClient}</option>
              {clients.filter((c) => c.abonnement).map((c) => <option key={c.id} value={c.id}>{c.nom}</option>)}
            </select>
          </Champ>
          <Champ id="recharge-conversations" titre={TA.conversations}>
            <Input id="recharge-conversations" type="number" inputMode="numeric" min={1} required value={conversations}
              onChange={(e) => setConversations(e.target.value)} className={champ} />
          </Champ>
          <Champ id="recharge-prix" titre={TA.rechargePrix}>
            <Input id="recharge-prix" type="number" inputMode="decimal" step="any" min={0} required value={prix}
              onChange={(e) => setPrix(e.target.value)} className={champ} />
          </Champ>
        </div>
        <ErreursChamps erreur={refus?.erreur ?? null} champs={refus?.champs} />
        <Fait texte={fait} />
        <div>
          <button type="submit" disabled={!client} className="rounded-full bg-marque px-4 py-2 text-[14px] font-bold text-on-marque disabled:opacity-60">
            {TA.ajouterRecharge}
          </button>
        </div>
      </form>
      {fenetre}
    </section>
  );
}
