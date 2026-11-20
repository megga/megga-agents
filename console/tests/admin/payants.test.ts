import { describe, expect, it } from "vitest";
import type { LignePayant, VuePayants } from "@/lib/admin/atelier";
import { bornerPayants, partConsommee, totauxDe } from "@/lib/admin/payants";
import { acces } from "./aides";

// Les clients payants bornés au périmètre du membre, sans réseau (20.11.2026).

const ligne = (client: string, statut: LignePayant["abonnement"]["statut"], revenu: number, cout: number, proche = false): LignePayant => ({
  client, entreprise: null, abonnement: { forfait: "essentiel", rythme: "mensuel", statut, debut: "2026-11-01", seuil_recharge: null },
  forfait_inconnu: false, mois: { debut: "2026-11-01" }, enveloppe: 200, consommees: 50, reste: 150, proche,
  recharges: { nombre: 0, conversations: 0, prix: 0 }, revenu, cout, marge: revenu - cout,
});

const vue = (clients: LignePayant[], devise_couts = "USD"): VuePayants => ({
  devise: "USD", devise_couts, catalogue: { devise: "USD", multiplicateur: 3, forfaits: [] }, clients,
  totaux: totauxDe(clients, true), releve_lisible: true,
});

describe("clients payants", () => {
  const lignes = [ligne("garage-essai", "actif", 290, 40), ligne("agence-essai", "retard", 290, 100, true), ligne("chalet-essai", "essai", 0, 5)];

  it("les totaux : revenu, coût des seuls payants, marge, proches", () => {
    const t = totauxDe(lignes, true);
    expect(t).toMatchObject({ actif: 1, retard: 1, essai: 1, parti: 0, revenu: 580, cout: 140, marge: 440, proches: 1 });
    expect(totauxDe(lignes, false).marge).toBeNull();
  });

  it("borne au périmètre et refait les totaux, les proches d'abord", () => {
    const v = bornerPayants(acces({ droits: ["couts.voir"], perimetre: ["garage-essai", "agence-essai"] }), vue(lignes));
    expect(v.clients.map((l) => l.client)).toEqual(["agence-essai", "garage-essai"]);
    expect(v.totaux.revenu).toBe(580);
    expect(bornerPayants(acces({ droits: ["couts.voir"], perimetre: ["chalet-essai"] }), vue(lignes)).totaux.revenu).toBe(0);
  });

  it("sans la même devise, aucune marge", () => {
    expect(bornerPayants(acces({ droits: ["couts.voir"] }), vue(lignes, "CHF")).totaux.marge).toBeNull();
  });

  it("la part consommée", () => {
    expect(partConsommee(lignes[0])).toBe(25);
    expect(partConsommee({ ...lignes[0], enveloppe: 0 })).toBeNull();
  });
});
