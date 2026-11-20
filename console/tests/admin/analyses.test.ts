import { describe, expect, it } from "vitest";
import { analyser } from "@/lib/admin/analyses";
import type { ClientReleve, JourReleve, Releves } from "@/lib/admin/releves";
import { acces } from "./aides";

// L'écran Analyses d'après le relevé chiffré, sans réseau (21.11.2026).

const jour = (tours: number, personnes: number, cout: number, autres: Partial<JourReleve> = {}): JourReleve => ({
  tours, tours_api: 1, tours_en_echec: 0, secours: 0, personnes, cout,
  modeles: { "claude-sonnet-5-5": { tours, entree: 1000 * tours, sortie: 10 * tours, cache_lecture: 0, cache_ecriture: 0 } },
  postes: { "claude-sonnet-5-5": cout - 0.5, voix: 0.5 },
  journal: { vocal_entendu: { nombre: 2 }, voix_caracteres: { nombre: 1, quantite: 300 } },
  ...autres,
});

const client = (id: string, jours: Record<string, JourReleve>, actif = true): ClientReleve => ({
  id, entreprise: `Entreprise ${id}`, zone: "europe", actif, version_en_service: 1, ecart: false, releve_le: 1, silencieux: false, etat: null,
  totaux: { tours: Object.values(jours).reduce((n, j) => n + j.tours, 0), tours_api: 0, tours_en_echec: 0, secours: 0,
    cout: Object.values(jours).reduce((n, j) => n + (j.cout ?? 0), 0), sans_tarif: [] },
  jours,
});

const r: Releves = { depuis: "2026-11-19", periode_jours: 7, devise: "USD", clients: [
  client("garage-essai", { "2026-11-19": jour(10, 2, 2), "2026-11-20": jour(20, 4, 4) }),
  client("agence-essai", { "2026-11-20": jour(5, 1, 1.5) }),
  client("parti-essai", { "2026-11-20": jour(99, 9, 9) }, false),
] };

describe("analyses", () => {
  it("additionne jour par jour, par modèle, par client ; un client inactif ne compte pas", () => {
    const v = analyser(r, acces({ droits: ["clients.voir", "couts.voir"] }));
    expect(v.tuiles).toEqual({ conversations: 7, tours: 35, toursApi: 3, vocauxEntendus: 6, vocauxDits: 3,
      cout: { devise: "USD", total: 7.5, parConversation: 1.07 } });
    expect(v.parJour).toEqual([
      { jour: "2026-11-19", tours: 10, conversations: 2, cout: 2, vocaux: 3 },
      { jour: "2026-11-20", tours: 25, conversations: 5, cout: 5.5, vocaux: 6 },
    ]);
    expect(v.modeles).toEqual([{ modele: "claude-sonnet-5-5", tours: 35, entree: 35000, sortie: 350, cacheLecture: 0, cout: 6 }]);
    expect(v.autresPostes).toEqual([{ poste: "voix", cout: 1.5 }]);
    // Un modèle sans tarif : son coût est inconnu, pas nul.
    const sans = analyser({ ...r, clients: [client("sans-tarif", { "2026-11-20": jour(1, 1, 0, { postes: {} }) })] }, acces({ droits: ["clients.voir", "couts.voir"] }));
    expect(sans.modeles[0].cout).toBeNull();
    expect(v.clients.map((c) => [c.client, c.conversations, c.coutParConversation])).toEqual([["garage-essai", 6, 1], ["agence-essai", 1, 1.5]]);
  });

  it("sans couts.voir, aucun montant ; le périmètre borne les clients", () => {
    const v = analyser(r, acces({ droits: ["clients.voir"], perimetre: ["agence-essai"] }));
    expect(v.tuiles.cout).toBeUndefined();
    expect(v.autresPostes).toEqual([]);
    expect(v.modeles[0].cout).toBeUndefined();
    expect(v.parJour.every((j) => j.cout === 0)).toBe(true);
    expect(v.clients).toEqual([{ client: "agence-essai", entreprise: "Entreprise agence-essai", tours: 5, conversations: 1 }]);
  });
});
