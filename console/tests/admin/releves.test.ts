import { describe, expect, it } from "vitest";
import { agregerReleves, santeDe, type ClientReleve, type JourReleve, type Releves } from "@/lib/admin/releves";
import { acces } from "./aides";

// La vue d'ensemble d'après le relevé chiffré, sans réseau.

const jour = (tours: number, cout: number, reponse: { nombre: number; moyenne: number | null } = { nombre: 0, moyenne: null }): JourReleve => ({
  tours, tours_api: 0, tours_en_echec: 0, secours: 0, personnes: 1, cout,
  delais: { lecture: { nombre: 0, moyenne: null }, reponse, lentes: 0 },
});

const client = (id: string, autres: Partial<ClientReleve> = {}): ClientReleve => ({
  id, entreprise: `Entreprise ${id}`, zone: "europe", actif: true, version_en_service: 1, ecart: false, releve_le: 1, silencieux: false,
  etat: { demarre: true, pannes_en_cours: [] },
  totaux: { tours: 10, tours_api: 0, tours_en_echec: 0, secours: 0, cout: 1.5, sans_tarif: [] },
  jours: { "2026-11-19": jour(4, 0.5, { nombre: 2, moyenne: 6 }), "2026-11-20": jour(6, 1, { nombre: 3, moyenne: 11 }) },
  ...autres,
});

const releves = (clients: ClientReleve[]): Releves => ({ depuis: "2026-11-14", periode_jours: 7, devise: "USD", clients });

const tous = acces({ droits: ["clients.voir", "couts.voir"] });
const sansCout = acces({ droits: ["clients.voir"] });

describe("la santé d'un agent", () => {
  it("la pire l'emporte : silencieux, en panne, écart, échecs, puis en bonne santé", () => {
    const totaux = { tours: 1, tours_api: 0, tours_en_echec: 2, secours: 0, cout: 0, sans_tarif: [] };
    expect(santeDe(client("alpha", { silencieux: true, ecart: true, totaux }))).toBe("silencieux");
    expect(santeDe(client("alpha", { etat: { pannes_en_cours: [{ quoi: "demarrage", quand: 1 }] }, ecart: true }))).toBe("panne");
    expect(santeDe(client("alpha", { ecart: true, totaux }))).toBe("ecart");
    expect(santeDe(client("alpha", { totaux }))).toBe("echecs");
    expect(santeDe(client("alpha"))).toBe("ok");
  });
});

describe("la vue d'ensemble des relevés", () => {
  it("tuiles, jours additionnés, la pire santé d'abord, la réponse moyenne pondérée", () => {
    const v = agregerReleves(releves([client("beta"), client("alpha", { silencieux: true }), client("gamma", { actif: false })]), tous);
    expect(v.tuiles).toEqual({ enService: 2, aSurveiller: 1, silencieux: 1, tours: 20, echecs: 0, cout: { devise: "USD", total: 3 } });
    expect(v.lignes.map((l) => [l.client, l.sante])).toEqual([["alpha", "silencieux"], ["beta", "ok"]]);
    expect(v.lignes[1].reponse).toBe(9); // (2 × 6 + 3 × 11) / 5
    expect(v.parJour).toEqual([{ jour: "2026-11-19", tours: 8, cout: 1 }, { jour: "2026-11-20", tours: 12, cout: 2 }]);
  });

  it("sans couts.voir, aucun coût nulle part", () => {
    const v = agregerReleves(releves([client("alpha", { totaux: { ...client("alpha").totaux, sans_tarif: ["inconnu"] } })]), sansCout);
    expect(v.tuiles.cout).toBeUndefined();
    expect(v.lignes[0].cout).toBeUndefined();
    expect(v.sansTarif).toEqual([]);
    expect(v.parJour.every((j) => j.cout === 0)).toBe(true);
  });

  it("le périmètre du membre filtre les clients avant tout calcul", () => {
    const limite = acces({ droits: ["clients.voir", "couts.voir"], perimetre: ["alpha"] });
    const v = agregerReleves(releves([client("alpha"), client("beta", { silencieux: true })]), limite);
    expect(v.lignes.map((l) => l.client)).toEqual(["alpha"]);
    expect(v.tuiles.aSurveiller).toBe(0);
    expect(v.tuiles.tours).toBe(10);
  });

  it("les modèles sans tarif sont dits une fois, triés", () => {
    const sans = (s: string[]) => ({ ...client("autre").totaux, sans_tarif: s });
    const v = agregerReleves(releves([client("alpha", { totaux: sans(["m2", "inconnu"]) }), client("beta", { totaux: sans(["inconnu"]) })]), tous);
    expect(v.sansTarif).toEqual(["inconnu", "m2"]);
  });

  it("sans réponse mesurée, la réponse est inconnue", () => {
    const v = agregerReleves(releves([client("alpha", { jours: { "2026-11-20": jour(1, 0) } })]), tous);
    expect(v.lignes[0].reponse).toBeNull();
  });
});
