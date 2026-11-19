"use client";

import { CopilotKitProvider } from "@copilotkit/react-core/v2";
import { useCallback, useEffect, useRef, useState } from "react";
import { T } from "@/lib/textes";
import { dernierTexte } from "./bulles";
import { Fil } from "./fil";
import { Plus } from "./icones";
import { Palette } from "./palette";
import { Rail } from "./rail";
import { Studio } from "./studio";
import { Tete } from "./tete";
import type { AgentVu, Memoire } from "./types";



export function Console({ entreprise, agentsInitiaux }: { entreprise: string; agentsInitiaux: AgentVu[] }) {
  const [agents, setAgents] = useState(agentsInitiaux);
  const [actif, setActif] = useState<string | null>(agentsInitiaux[0]?.id ?? null);
  const [studio, setStudio] = useState(false);
  const [palette, setPalette] = useState(false);
  const [ouvertures, setOuvertures] = useState(0);
  const [nouveau, setNouveau] = useState<string | null>(null);
  const [bulle, setBulle] = useState<string | null>(null);
  const [apercus, setApercus] = useState<Record<string, string>>({});
  const [fils, setFils] = useState<Record<string, Memoire>>({});
  const minuteur = useRef<ReturnType<typeof setTimeout>>(undefined);

  const dire = useCallback((m: string) => {
    setBulle(m);
    clearTimeout(minuteur.current);
    minuteur.current = setTimeout(() => setBulle(null), 1800);
  }, []);

  // Chaque ouverture remonte le Studio ou la recherche à neuf.
  const ouvrirStudio = useCallback(() => {
    setOuvertures((n) => n + 1);
    setStudio(true);
  }, []);
  const ouvrirPalette = useCallback(() => {
    setOuvertures((n) => n + 1);
    setPalette(true);
  }, []);

  useEffect(() => {
    function touche(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        ouvrirPalette();
      }
    }
    addEventListener("keydown", touche);
    return () => removeEventListener("keydown", touche);
  }, [ouvrirPalette]);

  const garder = useCallback((id: string, m: Memoire) => {
    const messages = m.messages;
    setFils((f) => ({ ...f, [id]: m }));
    const dernier = dernierTexte(messages);
    if (dernier) setApercus((a) => (a[id] === dernier ? a : { ...a, [id]: dernier }));
  }, []);

  async function epingler(a: AgentVu) {
    const r = await fetch(`/api/agents/${a.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ epingle: !a.epingle }),
    });
    const corps = await r.json().catch(() => ({}));
    if (!r.ok) return dire(corps.erreur || T.erreurGenerale);
    setAgents((l) => l.map((x) => (x.id === a.id ? corps.agent : x)));
    dire(a.epingle ? T.plusEpingle(a.prenom) : T.estEpingle(a.prenom));
  }

  function cree(a: AgentVu) {
    setStudio(false);
    setAgents((l) => [a, ...l]);
    setActif(a.id);
    setNouveau(a.id);
    setTimeout(() => setNouveau(null), 1400);
  }

  const agent = agents.find((a) => a.id === actif) ?? null;
  // CopilotKit lit la liste des agents au démarrage : il repart quand elle change.
  const cle = agents.map((a) => a.id).join(",");

  return (
    <div className="flex h-dvh">
      <Rail
        agents={agents}
        actif={actif}
        nouveau={nouveau}
        apercus={apercus}
        entreprise={entreprise}
        onChoisir={setActif}
        onNouvel={ouvrirStudio}
        onChercher={ouvrirPalette}
        onEpingler={epingler}
      />
      <main className="flex min-w-0 flex-1 flex-col">
        {agent ? (
          <CopilotKitProvider key={cle} runtimeUrl="/api/copilotkit" showDevConsole={false} enableInspector={false}>
            <Fil key={agent.id} agent={agent} agents={agents} memoire={fils[agent.id]} onChange={garder} />
          </CopilotKitProvider>
        ) : (
          <div className="flex flex-1 flex-col items-center justify-center gap-3 px-6 text-center">
            <Tete couleur={0} yeux={0} className="flotte w-[180px]" />
            <button type="button" onClick={ouvrirStudio} className="mt-1 inline-flex items-center gap-2 rounded-full bg-marque px-[22px] py-2.5 text-[14.5px] font-bold text-on-marque">
              <Plus className="size-[18px]" />
              {T.creerUnAgent}
            </button>
          </div>
        )}
      </main>
      <Studio key={"s" + ouvertures} ouvert={studio} onFermer={() => setStudio(false)} onCree={cree} onErreur={dire} />
      <Palette key={"p" + ouvertures} ouvert={palette} agents={agents} onFermer={() => setPalette(false)} onChoisir={setActif} />
      <div
        role="status"
        className={
          "pointer-events-none fixed bottom-[110px] left-1/2 z-[60] -translate-x-1/2 rounded-full bg-ink px-4 py-2 text-[14px] font-semibold text-bg transition-opacity duration-200 " +
          (bulle ? "opacity-100" : "opacity-0")
        }
      >
        {bulle}
      </div>
    </div>
  );
}
