"use client";

import { useAgent, useCopilotKit } from "@copilotkit/react-core/v2";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { T } from "@/lib/textes";
import { Fleche } from "./icones";
import { Tete } from "./tete";
import type { AgentVu, Bulle } from "./types";

type MessageAgui = { id: string; role: string; content?: unknown };

function texteDe(content: unknown): string {
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content.map((p) => (p && typeof p === "object" && "text" in p ? String((p as { text: unknown }).text ?? "") : "")).join("");
  }
  return "";
}

export function bulles(messages: readonly MessageAgui[]): Bulle[] {
  return messages
    .filter((m) => m.role === "user" || m.role === "assistant")
    .map((m) => ({ id: m.id, role: m.role as Bulle["role"], texte: texteDe(m.content) }))
    .filter((b) => b.texte.trim() !== "");
}

/** La conversation avec un agent et sa barre de saisie, branchées par CopilotKit (AG-UI). */
export function Fil({
  agent: a,
  memoire,
  onChange,
}: {
  agent: AgentVu;
  memoire: MessageAgui[] | undefined;
  onChange: (id: string, messages: MessageAgui[]) => void;
}) {
  const { agent, isReady } = useAgent({ agentId: a.id });
  const { copilotkit } = useCopilotKit();
  const [texte, setTexte] = useState("");
  const [souci, setSouci] = useState(false);
  const enAttente = useRef(false);
  const restaure = useRef(false);
  const fond = useRef<HTMLDivElement>(null);
  const zone = useRef<HTMLTextAreaElement>(null);

  // Le fil de cet agent est gardé par la console tant que la page reste ouverte.
  useEffect(() => {
    if (!isReady || restaure.current) return;
    restaure.current = true;
    if (memoire?.length && !agent.messages.length) agent.setMessages(memoire as never);
  }, [isReady, agent, memoire]);

  const messages = bulles(agent.messages as MessageAgui[]);
  const enCours = agent.isRunning;
  const attend = enCours && messages.at(-1)?.role !== "assistant";

  useEffect(() => {
    if (restaure.current) onChange(a.id, [...(agent.messages as MessageAgui[])]);
  }, [a.id, agent.messages, agent.messages.length, enCours, onChange]);

  const dernier = messages.at(-1)?.texte;
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
      return;
    }
    setTexte("");
    if (zone.current) zone.current.style.height = "auto";
    setSouci(false);
    agent.addMessage({ id: crypto.randomUUID(), role: "user", content: t } as never);
    try {
      await copilotkit.runAgent({ agent });
    } catch {
      setSouci(true);
    }
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
            m.role === "user" ? (
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

function MessageAgent({ agent, texte }: { agent: AgentVu; texte: string }) {
  return (
    <div className="flex items-start gap-3">
      <Tete couleur={agent.couleur} yeux={agent.yeux} className="w-11 flex-none pt-1" />
      <div className="min-w-0 flex-1 pt-2 whitespace-pre-wrap">{texte}</div>
    </div>
  );
}
