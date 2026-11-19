"use client";

import { useAgent, useCopilotKit } from "@copilotkit/react-core/v2";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { T } from "@/lib/textes";
import { Fleche } from "./icones";
import { Tete } from "./tete";
import { bulles, texteDe, type MessageAgui } from "./bulles";
import type { AgentVu, Bulle, Memoire } from "./types";

export { bulles } from "./bulles";

/** La conversation avec un agent et sa barre de saisie, branchées par CopilotKit (AG-UI). */
export function Fil({
  agent: a,
  agents,
  memoire,
  onChange,
}: {
  agent: AgentVu;
  agents: AgentVu[];
  memoire: Memoire | undefined;
  onChange: (id: string, memoire: Memoire) => void;
}) {
  const { agent, isReady } = useAgent({ agentId: a.id });
  const { copilotkit } = useCopilotKit();
  const [texte, setTexte] = useState("");
  const [souci, setSouci] = useState(false);
  const enAttente = useRef(false);
  const restaure = useRef(false);
  const fond = useRef<HTMLDivElement>(null);
  const zone = useRef<HTMLTextAreaElement>(null);

  // Le fil de cet agent est gardé par la console tant que la page reste ouverte. Quand CopilotKit repart
  // (un agent de plus), l'agent reprend la même conversation : le serveur y retrouve ce qui a été dit.
  useEffect(() => {
    if (!isReady || restaure.current) return;
    restaure.current = true;
    if (memoire && !agent.messages.length) {
      agent.threadId = memoire.threadId;
      agent.setMessages(memoire.messages as never);
    }
  }, [isReady, agent, memoire]);

  const messages = bulles(agent.messages as MessageAgui[]);
  const enCours = agent.isRunning;
  const fin = messages.at(-1);
  // Les trois points, sauf quand l'agent attend un collègue : sa ligne le dit déjà.
  const attend = enCours && fin?.role !== "assistant" && !(fin?.role === "echange" && fin.reponse === null);
  const prenomDe = (id: string) => agents.find((x) => x.id === id)?.prenom ?? T.unCollegue;

  useEffect(() => {
    if (restaure.current && agent.messages.length) onChange(a.id, { threadId: agent.threadId, messages: [...(agent.messages as MessageAgui[])] });
  }, [a.id, agent, agent.messages, agent.messages.length, agent.threadId, enCours, onChange]);

  const dernier = fin?.role === "echange" ? fin.reponse : fin?.texte;
  useLayoutEffect(() => {
    fond.current?.scrollIntoView({ block: "end" });
  }, [messages.length, dernier, attend]);

  useEffect(() => {
    if (window.matchMedia?.("(pointer: fine)").matches) zone.current?.focus();
  }, [a.id]);

  // Un message écrit avant que CopilotKit soit prêt part dès qu'il l'est.
  useEffect(() => {
    if (isReady && enAttente.current) {
      enAttente.current = false;
      envoyer();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isReady]);

  async function envoyer() {
    const t = texte.trim();
    if (!t || enCours) return;
    if (!isReady) {
      enAttente.current = true;
      // Toujours pas prêt au bout de 10 secondes : on le dit, et le message partira s'il le devient.
      setTimeout(() => enAttente.current && setSouci(true), 10_000);
      return;
    }
    setTexte("");
    if (zone.current) zone.current.style.height = "auto";
    setSouci(false);
    agent.addMessage({ id: crypto.randomUUID(), role: "user", content: t } as never);
    const avant = agent.messages.length;
    try {
      await copilotkit.runAgent({ agent });
    } catch {
      return setSouci(true);
    }
    // Une erreur du modèle peut finir le tour sans lever d'exception : sans réponse, on le dit aussi.
    const reponses = (agent.messages as MessageAgui[]).slice(avant);
    if (!reponses.some((m) => m.role === "assistant" && texteDe(m.content).trim())) setSouci(true);
  }

  function taille(el: HTMLTextAreaElement) {
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 200) + "px";
  }

  return (
    <>
      <div className="min-h-0 flex-1 overflow-y-auto px-6 pt-10 pb-3 max-[760px]:px-3.5 max-[760px]:pt-5" data-testid="fil">
        <div className="mx-auto flex max-w-[760px] flex-col gap-[18px]">
          <div className="text-center text-[12.5px] font-semibold text-faint">{messages.length ? T.aujourdhui : T.nouvelAgent}</div>
          <MessageAgent agent={a} texte={T.accueil(a.prenom)} />
          {messages.map((m) =>
            m.role === "echange" ? (
              <Echange key={m.id} echange={m} agent={a.prenom} collegue={prenomDe(m.collegue)} />
            ) : m.role === "user" ? (
              <div key={m.id} className="max-w-[75%] self-end rounded-[20px_20px_6px_20px] bg-hover px-4 py-2.5 whitespace-pre-wrap max-[760px]:max-w-[90%]">
                {m.texte}
              </div>
            ) : (
              <MessageAgent key={m.id} agent={a} texte={m.texte} />
            ),
          )}
          {attend && (
            <div className="flex items-start gap-3" aria-live="polite">
              <Tete couleur={a.couleur} yeux={a.yeux} className="w-11 flex-none pt-1" />
              <div className="points pt-4"><i /><i /><i /></div>
            </div>
          )}
          {souci && <div className="text-center text-[13px] text-muted-ink">{T.sansReponse}</div>}
          <div ref={fond} />
        </div>
      </div>
      <div className="flex-none px-6 pt-2 pb-[max(18px,env(safe-area-inset-bottom))] max-[760px]:px-3">
        <form
          className="trait relative mx-auto flex max-w-[760px] items-end gap-1.5 rounded-[30px] bg-bg py-[7px] pr-[7px] pl-[18px] shadow-doux"
          onSubmit={(e) => {
            e.preventDefault();
            envoyer();
          }}
        >
          <textarea
            ref={zone}
            rows={1}
            value={texte}
            placeholder={T.ecrireA(a.prenom)}
            aria-label={T.ecrireA(a.prenom)}
            className="min-h-0 flex-1 resize-none self-center border-0 bg-transparent px-0.5 py-2 text-[16px] text-ink outline-none placeholder:text-faint focus-visible:outline-none"
            onChange={(e) => {
              setTexte(e.target.value);
              taille(e.target);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                envoyer();
              }
            }}
          />
          <button
            type="submit"
            aria-label={T.envoyer}
            title={T.envoyer}
            disabled={!texte.trim() || enCours}
            className="grid size-10 flex-none place-items-center rounded-full bg-marque text-on-marque transition-opacity disabled:opacity-40"
          >
            <Fleche className="size-[18px]" />
          </button>
        </form>
      </div>
    </>
  );
}

/** Une question de l'agent à un collègue : une ligne de texte, qui se déplie sur la question et la réponse. */
function Echange({ echange: e, agent, collegue }: { echange: Extract<Bulle, { role: "echange" }>; agent: string; collegue: string }) {
  if (e.reponse === null) {
    return (
      <div className="pl-14 text-[13px] text-muted-ink" aria-live="polite" data-testid="echange">
        {T.consulte(agent, collegue)}
      </div>
    );
  }
  return (
    <details className="group pl-14 text-[13px] text-muted-ink" data-testid="echange">
      <summary className="w-fit cursor-pointer list-none select-none hover:text-ink [&::-webkit-details-marker]:hidden">
        {T.aDemandeA(agent, collegue)}
      </summary>
      <div className="mt-1.5 flex flex-col gap-1 whitespace-pre-wrap">
        <div>{T.citation(e.question)}</div>
        <div className="text-ink">{e.reponse}</div>
      </div>
    </details>
  );
}

function MessageAgent({ agent, texte }: { agent: AgentVu; texte: string }) {
  return (
    <div className="flex items-start gap-3">
      <Tete couleur={agent.couleur} yeux={agent.yeux} className="w-11 flex-none pt-1" />
      <div className="min-w-0 flex-1 pt-2 whitespace-pre-wrap">{texte}</div>
    </div>
  );
}
