"use client";

import { useEffect, useState } from "react";
import { T } from "@/lib/textes";
import { debut, parJour, PERIODES, souci, tempsForts, type EchangeVu, type Mesures, type Periode } from "./activite-donnees";
import { reponseLisible } from "./bulles";
import { Chevron, Triangle } from "./icones";
import { Tete } from "./tete";
import type { AgentVu } from "./types";

const NOMS: Record<Periode, string> = { jour: T.periodeJour, semaine: T.periodeSemaine, mois: T.periodeMois, an: T.periodeAn };

const heure = (s: number) => new Date(s * 1000).toLocaleTimeString("fr-CH", { hour: "2-digit", minute: "2-digit" });

function memeJour(a: Date, b: Date) {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

/** L'heure, précédée du jour quand ce n'est pas aujourd'hui (« 18 nov., 14:05 »). */
function quand(s: number): string {
  const d = new Date(s * 1000);
  if (memeJour(d, new Date())) return heure(s);
  return `${d.toLocaleDateString("fr-CH", { day: "numeric", month: "short" })}, ${heure(s)}`;
}

function nomDuJour(cle: string): string {
  const [a, m, j] = cle.split("-").map(Number);
  const d = new Date(a, m - 1, j);
  const auj = new Date();
  if (memeJour(d, auj)) return T.periodeJour;
  if (memeJour(d, new Date(auj.getFullYear(), auj.getMonth(), auj.getDate() - 1))) return T.hier;
  return d.toLocaleDateString("fr-CH", { weekday: "long", day: "numeric", month: "long" });
}

/** Ce que les agents ont fait, en phrases ; aujourd'hui, les questions qu'ils se sont posées (maquette « Temps forts »). */
export function Activite({ agents, onContinuer }: { agents: AgentVu[]; onContinuer: (id: string) => void }) {
  const [periode, setPeriode] = useState<Periode>("semaine");
  const [echanges, setEchanges] = useState<EchangeVu[] | null>(null);
  const [mesures, setMesures] = useState<Mesures | null>(null);
  const [souciReseau, setSouciReseau] = useState(false);
  const [reste, setReste] = useState(false);

  useEffect(() => {
    let vivant = true;
    fetch(`/api/activite?depuis=${Math.floor(debut(periode))}`)
      .then(async (r) => {
        if (!r.ok) throw new Error(String(r.status));
        return (await r.json()) as { echanges: EchangeVu[]; mesures: Mesures };
      })
      .then((d) => vivant && (setEchanges(d.echanges), setMesures(d.mesures), setSouciReseau(false)))
      .catch(() => vivant && setSouciReseau(true));
    return () => {
      vivant = false;
    };
  }, [periode]);

  const agent = (id: string) => agents.find((a) => a.id === id);
  const { forts, reste: autres } = tempsForts(echanges ?? []);
  const dormeur = agents[0];

  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-10 pt-8 pb-12 max-[760px]:px-3.5 max-[760px]:pt-5" data-testid="activite">
      <div className="mx-auto flex max-w-[860px] flex-col gap-[18px]">
        <div className="flex items-center gap-3">
          <h1 className="m-0 text-[28px] font-bold tracking-[-0.02em]">{T.activite}</h1>
          <div className="ml-auto flex gap-0.5 rounded-full bg-side p-1" role="group" aria-label={T.activite}>
            {PERIODES.map((p) => (
              <button
                key={p}
                type="button"
                aria-pressed={periode === p}
                onClick={() => {
                  setPeriode(p);
                  setReste(false);
                }}
                className="rounded-full px-3.5 py-1.5 text-[13.5px] font-semibold text-muted-ink hover:text-ink aria-pressed:bg-bg aria-pressed:text-ink aria-pressed:shadow-[0_1px_3px_rgba(0,0,0,.08)] max-[760px]:px-2.5"
              >
                {NOMS[p]}
              </button>
            ))}
          </div>
        </div>

        {mesures && (
          <div className="mt-1 mb-1.5 grid grid-cols-3 gap-3 max-[760px]:grid-cols-1" data-testid="chiffres">
            {(
              [
                [mesures.conversations, T.chiffreConversations],
                [mesures.reponses, T.chiffreReponses],
                [mesures.echanges, T.chiffreEchanges],
              ] as const
            ).map(([n, nom]) => (
              <div key={nom} className="flex flex-col gap-0.5 rounded-[20px] bg-side px-5 py-[18px]">
                <b className="text-[34px] leading-[1.1] font-extrabold tracking-[-0.03em] tabular-nums">{n.toLocaleString("fr-CH")}</b>
                <span className="text-[14px] text-muted-ink">{nom}</span>
              </div>
            ))}
          </div>
        )}

        {souciReseau && <div className="text-center text-[13px] text-muted-ink">{T.serviceIndisponible}</div>}

        {echanges && !echanges.length && dormeur && (
          <div className="flex justify-center py-14" role="img" aria-label={T.aucuneAction}>
            <Tete couleur={dormeur.couleur} yeux={dormeur.yeux} endormie className="w-[160px]" />
          </div>
        )}

        {forts.length > 0 && (
          <div className="grid grid-cols-2 gap-3 [grid-auto-flow:dense] max-[760px]:grid-cols-1">
            {forts.map((e) => (
              <Fort key={e.id} echange={e} agent={agent} onContinuer={onContinuer} />
            ))}
          </div>
        )}

        {autres.length > 0 && (
          <>
            <button
              type="button"
              aria-expanded={reste}
              onClick={() => setReste((r) => !r)}
              className="self-center rounded-full px-4 py-2 text-[14px] font-semibold text-muted-ink hover:bg-side hover:text-ink"
            >
              {reste ? T.masquerLeReste : T.voirLeReste}
            </button>
            {reste && (
              <div className="flex flex-col gap-0.5">
                {parJour(autres).map(([jour, liste]) => (
                  <div key={jour}>
                    <div className="mx-3 mt-4 mb-1.5 text-[11.5px] font-bold tracking-[.06em] text-faint uppercase">{nomDuJour(jour)}</div>
                    {liste.map((e) => (
                      <Ligne key={e.id} echange={e} agent={agent} onContinuer={onContinuer} />
                    ))}
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

type Props = { echange: EchangeVu; agent: (id: string) => AgentVu | undefined; onContinuer: (id: string) => void };

/** La phrase d'un échange, les prénoms en gras. */
function Phrase({ echange: e, agent }: Omit<Props, "onContinuer">) {
  const de = agent(e.de)?.prenom ?? T.unCollegue;
  const a = agent(e.a)?.prenom ?? T.unCollegue;
  return souci(e) ? (
    <>
      <b>{a}</b>
      {T.pasRepondu}
      <b>{de}</b>
    </>
  ) : (
    <>
      <b>{de}</b>
      {T.aDemandeAMilieu}
      <b>{a}</b>
    </>
  );
}

function Detail({ echange: e, agent, onContinuer }: Props) {
  const de = agent(e.de);
  return (
    <div className="flex flex-col gap-3 text-[14px]">
      <div className="flex flex-col gap-1 whitespace-pre-wrap">
        <div className="text-muted-ink">{T.citation(e.question)}</div>
        {e.etat === "repondu" && e.reponse && <div>{reponseLisible(e.reponse)}</div>}
        {e.etat === "passe" && <div className="text-muted-ink">{T.rienAAjouter}</div>}
      </div>
      {de && (
        <button
          type="button"
          onClick={() => onContinuer(de.id)}
          className="w-fit rounded-full bg-bg px-4 py-2 text-[14px] font-semibold text-ink hover:bg-hover"
        >
          {T.continuerAvec(de.prenom)}
        </button>
      )}
    </div>
  );
}

function Fort(p: Props) {
  const e = p.echange;
  const alerte = souci(e);
  const [ouvert, setOuvert] = useState(alerte);
  const qui = p.agent(alerte ? e.a : e.de);
  return (
    <div
      data-testid="temps-fort"
      className={
        "rounded-3xl " +
        (alerte ? "col-span-full bg-[color-mix(in_srgb,var(--warn)_12%,var(--side))] " : "bg-side ") +
        (ouvert ? "col-span-full" : "")
      }
    >
      <button
        type="button"
        aria-expanded={ouvert}
        onClick={() => setOuvert((o) => !o)}
        className="flex w-full items-center gap-[18px] rounded-3xl px-[22px] py-5 text-left text-ink hover:bg-[color-mix(in_srgb,var(--ink)_3%,transparent)]"
      >
        <span className="relative w-[72px] flex-none">
          {qui && <Tete couleur={qui.couleur} yeux={qui.yeux} className="w-[72px]" />}
          {alerte && <Triangle className="absolute right-[-4px] bottom-[-2px] size-6 text-[var(--warn)]" />}
        </span>
        <span className="flex min-w-0 flex-col gap-1">
          <span className="text-[18px] leading-[1.35] tracking-[-0.01em] [&_b]:font-extrabold">
            <Phrase echange={e} agent={p.agent} />
          </span>
          <time className="text-[13px] text-muted-ink">{quand(e.quand)}</time>
        </span>
      </button>
      {ouvert && (
        <div className="px-[22px] pb-5 pl-[112px] max-[760px]:pl-[22px]">
          <Detail {...p} />
        </div>
      )}
    </div>
  );
}

function Ligne(p: Props) {
  const e = p.echange;
  const [ouvert, setOuvert] = useState(false);
  const qui = p.agent(souci(e) ? e.a : e.de);
  return (
    <div className={"rounded-2xl " + (ouvert ? "bg-side" : "")} data-testid="ligne-activite">
      <button
        type="button"
        aria-expanded={ouvert}
        onClick={() => setOuvert((o) => !o)}
        className="flex w-full items-center gap-3.5 rounded-2xl px-3 py-2.5 text-left text-ink hover:bg-side"
      >
        <span className="relative w-9 flex-none">
          {qui && <Tete couleur={qui.couleur} yeux={qui.yeux} className="w-9" />}
          {souci(e) && <Triangle className="absolute right-[-6px] bottom-[-6px] size-[18px] text-[var(--warn)]" />}
        </span>
        <span className={"min-w-0 flex-1 text-[15px] leading-[1.4] [&_b]:font-bold " + (souci(e) ? "font-semibold" : "")}>
          <Phrase echange={e} agent={p.agent} />
        </span>
        <time className="flex-none text-[13px] text-muted-ink tabular-nums">{heure(e.quand)}</time>
        <Chevron className={"size-3.5 flex-none text-muted-ink transition-transform " + (ouvert ? "rotate-90" : "")} />
      </button>
      {ouvert && (
        <div className="px-3 pb-3.5 pl-[62px]">
          <Detail {...p} />
        </div>
      )}
    </div>
  );
}
