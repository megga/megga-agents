"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Confirmation } from "@/components/admin/confirmation";
import { envoyer } from "@/components/admin/envoyer";
import { Fait } from "@/components/admin/erreurs";
import { cadre, champ, etiquette, titreBloc } from "@/components/admin/formulaire";
import { Pastille } from "@/components/admin/pastille";
import { SecretUnique } from "@/components/admin/secret";
import { Tableau } from "@/components/admin/tableau";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { TA } from "@/lib/admin/textes";

// Les gestes de l'onglet Accès : reprendre ou rendre la main (clients.piloter) ; créer un jeton, retirer les jetons, créer ou
// retirer une clé de logiciel (acces.gerer). Chacun derrière une confirmation qui dit son effet. Un jeton ou une clé n'est
// tenu que par SecretUnique, le temps de le copier : fermé, il est oublié (aucun autre état ne le garde).

const adresse = (id: string) => `/api/admin/clients/${encodeURIComponent(id)}`;

/** Qui tient l'agent : reprendre la main (seul MEGGA met alors en service) ou la rendre au client. */
export function Main({ id, gere }: { id: string; gere: boolean }) {
  const router = useRouter();
  const [fait, setFait] = useState<string | null>(null);
  const bouton = gere ? TA.rendreMain : TA.reprendreMain;
  return (
    <section className={cadre}>
      <h2 className={titreBloc}>{TA.quiTientAgent}</h2>
      <p className="m-0 text-[14px]">{gere ? TA.tenuParMeggaPhrase : TA.tenuParClient}</p>
      <div className="flex flex-wrap items-center gap-3">
        <Confirmation
          titre={gere ? TA.rendreTitre : TA.reprendreTitre}
          effet={gere ? TA.rendreEffet : TA.reprendreEffet}
          bouton={bouton}
          onConfirmer={async () => {
            const r = await envoyer<{ gere_par_megga: boolean }>(`${adresse(id)}/reprise`, "POST", { gere_par_megga: !gere });
            setFait(r?.gere_par_megga ? TA.mainReprise : TA.mainRendue);
            router.refresh();
          }}
        >
          {bouton}
        </Confirmation>
        <Fait texte={fait} />
      </div>
    </section>
  );
}

/** Les jetons du client : aucune route ne les liste ; en créer un (montré une fois), ou les retirer tous. */
export function Jetons({ id }: { id: string }) {
  const [secret, setSecret] = useState<string | null>(null);
  const [fait, setFait] = useState<string | null>(null);
  return (
    <section className={cadre}>
      <h2 className={titreBloc}>{TA.jetonsClient}</h2>
      <p className="m-0 text-[13.5px] text-muted-ink">{TA.jetonsSansListe}</p>
      <div className="flex flex-wrap items-center gap-2">
        <Confirmation
          titre={TA.creerJetonTitre}
          effet={TA.creerJetonEffet}
          bouton={TA.creerJeton}
          onConfirmer={async () => {
            const r = await envoyer<{ jeton: string }>(`${adresse(id)}/jetons`, "POST");
            setFait(null);
            setSecret(r?.jeton ?? null);
          }}
        >
          {TA.creerJeton}
        </Confirmation>
        <Confirmation
          titre={TA.retirerJetonsTitre}
          effet={TA.retirerJetonsEffet}
          bouton={TA.retirerJetons}
          onConfirmer={async () => {
            const r = await envoyer<{ retires: number }>(`${adresse(id)}/jetons`, "DELETE");
            setFait(TA.jetonsRetires(r?.retires ?? 0));
          }}
        >
          {TA.retirerJetons}
        </Confirmation>
      </div>
      <Fait texte={fait} />
      <SecretUnique valeur={secret} onFermer={() => setSecret(null)} />
    </section>
  );
}

/** Une clé telle que l'écran la montre : jamais la clé elle-même, que l'atelier ne garde pas. */
export type CleVue = { id: string; logiciel: string; parMinute: number | null; creeLe: string; retireeLe: string | null };

/** Les clés des logiciels du client : la liste, en retirer une, en créer une (montrée une fois). */
export function Cles({ id, cles }: { id: string; cles: CleVue[] }) {
  const router = useRouter();
  const [logiciel, setLogiciel] = useState("");
  const [parMinute, setParMinute] = useState("");
  const [secret, setSecret] = useState<string | null>(null);

  async function creer() {
    const debit = parMinute.trim() === "" ? {} : { par_minute: Number(parMinute) };
    const r = await envoyer<{ cle: string }>(`${adresse(id)}/cles`, "POST", { logiciel: logiciel.trim(), ...debit });
    setLogiciel("");
    setParMinute("");
    setSecret(r?.cle ?? null);
    router.refresh();
  }

  return (
    <section className={cadre}>
      <h2 className={titreBloc}>{TA.clesLogiciels}</h2>
      <Tableau
        colonnes={[TA.logiciel, TA.identifiant, TA.parMinute, TA.creeeLe, TA.etat]}
        vide={TA.videCles}
        replier={[1, 2, 3, 4]}
        lignes={cles.map((c) => [
          <b key="logiciel" className="font-bold wrap-anywhere">{c.logiciel}</b>,
          <span key="id" className="whitespace-nowrap text-muted-ink">{c.id}</span>,
          <span key="debit" className="tabular-nums">{c.parMinute === null ? TA.inconnu : TA.nombre(c.parMinute)}</span>,
          <span key="cree" className="whitespace-nowrap">{c.creeLe}</span>,
          c.retireeLe ? (
            <Pastille key="etat" etat="faint" texte={TA.retireeLe(c.retireeLe)} />
          ) : (
            <span key="etat" className="flex flex-wrap items-center gap-2">
              <Pastille etat="ok" texte={TA.enService} />
              <Confirmation
                titre={TA.retirerCleTitre(c.logiciel)}
                effet={TA.retirerCleEffet}
                bouton={TA.retirer}
                onConfirmer={async () => {
                  await envoyer(`${adresse(id)}/cles/${encodeURIComponent(c.id)}`, "DELETE");
                  router.refresh();
                }}
              >
                {TA.retirer}
              </Confirmation>
            </span>
          ),
        ])}
      />
      <div className="grid gap-3.5 min-[761px]:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="cle-logiciel" className={etiquette}>{TA.logiciel}</Label>
          <Input id="cle-logiciel" value={logiciel} maxLength={20} autoComplete="off" onChange={(e) => setLogiciel(e.target.value)} className={champ} />
          <span className="text-[12.5px] text-faint">{TA.logicielAide}</span>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="cle-debit" className={etiquette}>{TA.parMinute}</Label>
          <Input id="cle-debit" type="number" inputMode="numeric" min={1} max={600} step={1} value={parMinute} onChange={(e) => setParMinute(e.target.value)}
            className={champ} />
          <span className="text-[12.5px] text-faint">{TA.parMinuteAide}</span>
        </div>
      </div>
      <div>
        <Confirmation titre={TA.creerCleTitre(logiciel.trim())} effet={TA.creerCleEffet} bouton={TA.creerCle} onConfirmer={creer}>
          {TA.creerCle}
        </Confirmation>
      </div>
      <SecretUnique valeur={secret} onFermer={() => setSecret(null)} />
    </section>
  );
}
