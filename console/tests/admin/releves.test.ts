import { describe, expect, it } from "vitest";
import type { ClientAtelier } from "@/lib/admin/atelier";
import { agregerReleves, completer, santeDe, soucisDe, type ClientReleve, type JourReleve, type Releves } from "@/lib/admin/releves";
import { acces } from "./aides";

// La vue d'ensemble d'après le relevé chiffré, sans réseau.

type DelaiEssai = { nombre: number; moyenne: number | null; mediane?: number | null; p95?: number | null };
const jour = (tours: number, cout: number, reponse: DelaiEssai = { nombre: 0, moyenne: null }): JourReleve => ({
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
    expect(santeDe(client("alpha", { totaux }))).toBe("soucis");
    expect(santeDe(client("alpha"))).toBe("ok");
  });

  it("les soucis du journal comptent : un client dont Meta refuse les envois n'est pas en bonne santé", () => {
    const refus = (n: number): JourReleve => ({ ...jour(5, 0), journal: { envoi_refuse: { nombre: n }, voix_caracteres: { nombre: 9 }, plafond: { nombre: 1 } } });
    const c = client("alpha", { jours: { "2026-11-19": refus(2), "2026-11-20": refus(3) } });
    expect(soucisDe(c)).toEqual([{ genre: "envoi_refuse", nombre: 5 }, { genre: "plafond", nombre: 2 }]);
    expect(santeDe(c)).toBe("soucis");
    expect(soucisDe(client("alpha"))).toEqual([]);
  });
});

describe("la vue d'ensemble des relevés", () => {
  it("tuiles, jours additionnés, la pire santé d'abord, la réponse moyenne pondérée", () => {
    const v = agregerReleves(releves([client("beta"), client("alpha", { silencieux: true }), client("gamma", { actif: false })]), tous);
    expect(v.tuiles).toEqual({ enService: 2, aSurveiller: 1, silencieux: 1, tours: 20, echecs: 0, personnesParJour: 2, cout: { devise: "USD", total: 3 } });
    expect(v.lignes.map((l) => [l.client, l.sante])).toEqual([["alpha", "silencieux"], ["beta", "ok"]]);
    expect(v.lignes[1].reponse).toBe(9); // (2 × 6 + 3 × 11) / 5
    expect(v.parJour).toEqual([{ jour: "2026-11-19", tours: 8, cout: 1 }, { jour: "2026-11-20", tours: 12, cout: 2 }]);
  });

  it("le cas lent du pire jour, et les outils de tous les clients, les plus appelés d'abord", () => {
    const avec = (p95: number | null, outils: JourReleve["outils"]) => ({ ...jour(3, 0, { nombre: 3, moyenne: 5, mediane: 4, p95 }), outils });
    const alpha = client("alpha", { jours: {
      "2026-11-19": avec(30, { rappeler: { appels: 2, echecs: 1, duree: 1, mesures: 2 } }),
      "2026-11-20": avec(12, { rappeler: { appels: 1, echecs: 0, duree: 0, mesures: 0 }, chercher: { appels: 4, echecs: 0, duree: 2, mesures: 4 } }),
    } });
    const v = agregerReleves(releves([alpha, client("beta")]), tous);
    expect(v.lignes.find((l) => l.client === "alpha")?.reponseLente).toBe(30);
    expect(v.lignes.find((l) => l.client === "beta")?.reponseLente).toBeNull(); // un relevé d'avant les centiles
    expect(v.outils).toEqual([
      { nom: "chercher", appels: 4, echecs: 0, dureeMoyenne: 0.5 },
      { nom: "rappeler", appels: 3, echecs: 1, dureeMoyenne: 0.5 },
    ]);
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

  it("les clients en service sans relevé s'ajoutent : installation hors Cloudflare, client absent de l'annuaire", () => {
    const atelier = (id: string, autres: Partial<ClientAtelier> = {}): ClientAtelier => ({
      id, nom_agent: "Lou", entreprise: `Entreprise ${id}`, version_en_service: 1, derniere_version: 1, gere_par_megga: false, ...autres });
    const r = releves([client("alpha")]);
    const clients = [atelier("alpha"), atelier("absent"), atelier("brouillon", { version_en_service: null }),
      atelier("chalet", { installation: { silencieuse: false, ecart: false } }), atelier("ferme", { installation: { silencieuse: true } }),
      atelier("revoque", { installation: { revoquee: 1 } })];
    const v = completer(agregerReleves(r, tous), r, clients, tous);
    expect(v.lignes.map((l) => [l.client, l.sante, l.horsReleve ?? false])).toEqual([
      ["ferme", "silencieux", true], ["revoque", "panne", true], ["absent", "ecart", true], ["alpha", "ok", false], ["chalet", "installation", true]]);
    expect(v.tuiles).toMatchObject({ enService: 5, aSurveiller: 3, silencieux: 1, tours: 10 });
    const limite = acces({ droits: ["clients.voir"], perimetre: ["alpha"] });
    expect(completer(agregerReleves(r, limite), r, clients, limite).lignes.map((l) => l.client)).toEqual(["alpha"]);
  });
});
