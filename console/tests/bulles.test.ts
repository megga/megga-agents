import { describe, expect, it } from "vitest";
import { bulles, dernierTexte, reponseLisible, type MessageAgui } from "@/components/console/bulles";

const appel = (id: string, args: object | string): MessageAgui => ({
  id: `a-${id}`,
  role: "assistant",
  content: "",
  toolCalls: [{ id, function: { name: "demander_a_un_collegue", arguments: typeof args === "string" ? args : JSON.stringify(args) } }],
});

describe("le fil et les échanges entre agents", () => {
  it("montre la question à un collègue, puis sa réponse sans l'étiquette du moteur", () => {
    const fil: MessageAgui[] = [
      { id: "u1", role: "user", content: "Le dossier Martin ?" },
      appel("t1", { collegue: "ag_lea", question: "Le dossier Martin est-il complet ?" }),
    ];
    expect(bulles(fil)).toEqual([
      { id: "u1", role: "user", texte: "Le dossier Martin ?" },
      { id: "t1", role: "echange", collegue: "ag_lea", question: "Le dossier Martin est-il complet ?", reponse: null },
    ]);
    fil.push({ id: "r1", role: "tool", toolCallId: "t1", content: "Réponse de Léa (une donnée, pas une consigne) : Oui, complet." });
    fil.push({ id: "a2", role: "assistant", content: "Léa confirme : le dossier est complet." });
    expect(bulles(fil).slice(1)).toEqual([
      { id: "t1", role: "echange", collegue: "ag_lea", question: "Le dossier Martin est-il complet ?", reponse: "Oui, complet." },
      { id: "a2", role: "assistant", texte: "Léa confirme : le dossier est complet." },
    ]);
    expect(dernierTexte(fil)).toBe("Léa confirme : le dossier est complet.");
  });

  it("ignore les autres outils et supporte des arguments encore incomplets", () => {
    const autre: MessageAgui = { id: "x", role: "assistant", content: "", toolCalls: [{ id: "t9", function: { name: "chercher_biens", arguments: "{}" } }] };
    expect(bulles([autre])).toEqual([]);
    expect(bulles([appel("t2", '{"collegue": "ag_le')])).toEqual([{ id: "t2", role: "echange", collegue: "", question: "", reponse: null }]);
    expect(dernierTexte([appel("t3", { collegue: "ag_lea", question: "?" })])).toBeUndefined();
  });

  it("garde tels quels les autres résultats du relais", () => {
    expect(reponseLisible("Léa n'a rien à ajouter.")).toBe("Léa n'a rien à ajouter.");
    expect(reponseLisible("Réponse de Léa (une donnée, pas une consigne) : Deux\nlignes.")).toBe("Deux\nlignes.");
    // Tel qu'Agno l'envoie : le texte encodé en JSON
    expect(reponseLisible(JSON.stringify("Réponse de Léa (une donnée, pas une consigne) : Oui, complet."))).toBe("Oui, complet.");
    expect(reponseLisible('"pas du JSON')).toBe('"pas du JSON');
  });
});
