import { describe, expect, it } from "vitest";
import { RefusChamps, type Alerte, type ClientAtelier, type Jours, type Lecteur, type Suivi } from "@/lib/admin/atelier";
import {
  agreger,
  classerASurveiller,
  estEnCours,
  etatClient,
  GENRES_CONNUS,
  GENRES_DE_L_INSTANT,
  gravite,
  horsCloudflare,
  joursDe,
  lireAlertes,
  lireTout,
  sansCouts,
  soucis,
  texteGenre,
  trierAlertes,
  zoneClient,
} from "@/lib/admin/suivi";
import { TA } from "@/lib/admin/textes";
import { acces } from "./aides";

// Le suivi, sans réseau : un lecteur simulé tient la place de l'atelier.

const client = (id: string, autres: Partial<ClientAtelier> = {}): ClientAtelier => ({
  id, nom_agent: "Lou", entreprise: `Entreprise ${id}`, version_en_service: 1, derniere_version: 1, gere_par_megga: false, ...autres,
});

const suiviDe = (id: string, jours: number, total = 1.5, sansTarif: string[] = []): Suivi => ({
  ...client(id),
  periode_jours: jours,
  activite: { tours: 10, tours_api: 1, tours_en_echec: 2, secours: 1, personnes: 3, rappels_en_attente: 0, modeles: {}, journal: {} },
  couts: { devise: "USD", postes: { "claude-sonnet-5-5": total }, total, sans_tarif: sansTarif },
});

const ALERTES: Alerte[] = [
  { quand: 100, genre: "tour_echec", detail: "RuntimeError" },
  { quand: 200, genre: "conteneur_transmission", detail: "arrêté", resolue: null },
];

/**
 * Un atelier simulé : il note chaque lecture et compte celles qui sont en cours en même temps. echec : le suivi de ce client
 * ne répond pas, ses alertes disent « conteneur injoignable » (comme l'atelier) ; muet : ni suivi ni alertes ; jamais : ces
 * clients n'ont jamais été mis en service.
 */
function lecteur(ids: string[], o: { echec?: string; muet?: string; jamais?: string[]; sansTarif?: Record<string, string[]> } = {}) {
  const appels: string[] = [];
  let enCours = 0;
  let max = 0;
  async function suivre<T>(quoi: string, rendre: () => T): Promise<T> {
    appels.push(quoi);
    enCours++;
    max = Math.max(max, enCours);
    await new Promise((r) => setTimeout(r, 2));
    enCours--;
    return rendre();
  }
  const l: Lecteur = {
    clients: async () => ({
      clients: ids.map((id) => client(id, o.jamais?.includes(id) ? { version_en_service: null } : {})),
      porte: true,
    }),
    suivi: (id: string, jours: Jours) =>
      suivre(`suivi ${id}`, () => {
        if (id === o.echec || id === o.muet) throw new RefusChamps(504, TA.atelierLent);
        return suiviDe(id, jours, 1.5, o.sansTarif?.[id] ?? []);
      }),
    alertes: (id: string, jours: Jours) =>
      suivre(`alertes ${id}`, () => {
        if (id === o.muet) throw new RefusChamps(502, TA.atelierInjoignable);
        const injoignable = { quand: 300, genre: "conteneur_injoignable", detail: "le conteneur du client ne répond pas" };
        return { periode_jours: jours, alertes: id === o.echec ? [...ALERTES, injoignable] : ALERTES };
      }),
  };
  return { l, appels, max: () => max };
}

const tous = acces({ droits: ["clients.voir", "couts.voir"] });
const sansCout = acces({ droits: ["clients.voir"] });

describe("la période", () => {
  it("une période tapée à la main retombe sur 7 jours", () => {
    expect([joursDe("abc"), joursDe("999"), joursDe(undefined), joursDe("1"), joursDe("30")]).toEqual([7, 7, 7, 1, 30]);
    expect([joursDe(["30", "1"]), joursDe(""), joursDe(" 1"), joursDe("7")]).toEqual([30, 7, 7, 7]);
  });
});

describe("les soucis", () => {
  it("en cours : une panne de conteneur non résolue et les états de l'instant ; le reste est passé", () => {
    expect(estEnCours({ quand: 1, genre: "conteneur_transmission", detail: "", resolue: null })).toBe(true);
    expect(estEnCours({ quand: 1, genre: "conteneur_demarrage", detail: "", resolue: 2 })).toBe(false);
    for (const g of ["conteneur_injoignable", "ecart", "porte_injoignable", "licence_expiree", "installation_silencieuse"])
      expect(estEnCours({ quand: 1, genre: g, detail: "" }), g).toBe(true);
    for (const g of ["tour_echec", "envoi_refuse", "plafond", "message_ancien", "genre_futur"])
      expect(estEnCours({ quand: 1, genre: g, detail: "" }), g).toBe(false);
    for (const g of GENRES_DE_L_INSTANT) expect(GENRES_CONNUS, g).toContain(g);
  });

  it("un souci en cours pèse plus qu'un fait passé ; le plus grave d'abord", () => {
    const passe = { client: "x", genre: "tour_echec", enCours: false, quand: 1 };
    const enCours = { client: "x", genre: "ecart", enCours: true, quand: 1 };
    expect(gravite(enCours)).toBeGreaterThan(gravite(passe));
    expect(classerASurveiller([{ client: "b", soucis: [passe] }, { client: "a", soucis: [enCours] }, { client: "c", soucis: [passe, passe] }])
      .map((l) => l.client)).toEqual(["a", "c", "b"]);
    expect(classerASurveiller([{ client: "z", soucis: [] }, { client: "b", soucis: [passe] }, { client: "a", soucis: [passe] }])
      .map((l) => l.client)).toEqual(["a", "b"]);
  });

  it("chaque genre connu se dit en clair ; un genre inconnu, avec son nom", () => {
    for (const g of GENRES_CONNUS) expect(TA.genres[g], g).toBeTruthy();
    expect(texteGenre("tour_echec")).toBe(TA.genres.tour_echec);
    expect(texteGenre("autre")).toBe(TA.genreInconnu("autre"));
    expect(soucis("g", ALERTES)).toEqual([
      { client: "g", genre: "tour_echec", enCours: false, quand: 100 },
      { client: "g", genre: "conteneur_transmission", enCours: true, quand: 200 },
    ]);
  });

  it("les alertes : en cours d'abord, puis par date, par client ou par genre", () => {
    const l = [
      { client: "b", quand: 1, genre: "tour_echec", detail: "" },
      { client: "a", quand: 3, genre: "plafond", detail: "" },
      { client: "c", quand: 2, genre: "ecart", detail: "" },
      { client: "a", quand: 4, genre: "tour_echec", detail: "" },
    ];
    expect(trierAlertes(l, "quand").map((x) => `${x.client}${x.quand}`)).toEqual(["c2", "a4", "a3", "b1"]);
    expect(trierAlertes(l, "client").map((x) => `${x.client}${x.quand}`)).toEqual(["c2", "a4", "a3", "b1"]);
    expect(trierAlertes(l, "genre").map((x) => `${x.client}${x.quand}`)).toEqual(["c2", "a3", "a4", "b1"]);
    expect(l.map((x) => x.quand)).toEqual([1, 3, 2, 4]); // la liste donnée n'est pas touchée
  });

  it("par client : dans l'ordre du nom montré (l'entreprise), pas de l'identifiant ; un instant inconnu, en dernier", () => {
    const l = [
      { client: "a-zinc", nom: "Zinc SA", quand: 5, genre: "tour_echec", detail: "" },
      { client: "z-atelier", nom: "Atelier du Lac", quand: 1, genre: "tour_echec", detail: "" },
      { client: "z-atelier", nom: "Atelier du Lac", quand: null, genre: "plafond", detail: "" },
    ];
    expect(trierAlertes(l, "client").map((x) => `${x.client}:${x.quand}`)).toEqual(["z-atelier:1", "z-atelier:null", "a-zinc:5"]);
    expect(trierAlertes(l, "quand").map((x) => x.quand)).toEqual([5, 1, null]);
    expect([TA.moment(null), TA.moment(Number.NaN)]).toEqual(["-", "-"]);
  });
});

describe("la zone d'un client", () => {
  it("se lit dans la version en service, sinon dans la dernière ; hors Cloudflare : une zone que la porte ne sert pas", () => {
    const porte = ["europe", "etats-unis"];
    expect([zoneClient({ zone: "client" }, { zone: "europe" }), zoneClient(null, { zone: "suisse" }), zoneClient(null, null),
      zoneClient(undefined, { zone: 3 })]).toEqual(["client", "suisse", null, null]);
    expect([horsCloudflare("client", porte), horsCloudflare("suisse", porte), horsCloudflare("europe", porte),
      horsCloudflare(null, porte), horsCloudflare("client", null)]).toEqual([true, true, false, false, false]);
  });
});

describe("l'état d'un client", () => {
  it("dit le service, l'écart, la main de MEGGA et le conteneur", () => {
    expect(etatClient(client("a", { version_en_service: null }))).toMatchObject({ service: "jamais", ecart: false, tenuParMegga: false });
    expect(etatClient(client("a", { ecart: true, gere_par_megga: true }))).toMatchObject({ service: "en_service", ecart: true, tenuParMegga: true });
    expect([true, false, undefined].map((demarre) =>
      etatClient(client("a", { annuaire: demarre === undefined ? { version: 1 } : { version: 1, conteneur: { demarre } } })).conteneur))
      .toEqual(["demarre", "arrete", "inconnu"]);
    expect(etatClient(client("a", { annuaire: null })).conteneur).toBe("inconnu");
  });
});

describe("les coûts", () => {
  it("se retirent sans couts.voir et restent avec", () => {
    const s = suiviDe("a", 7);
    expect("couts" in sansCouts(s, sansCout)).toBe(false);
    expect(sansCouts(s, sansCout).activite.tours).toBe(10);
    expect(sansCouts(s, tous).couts).toEqual(s.couts);
    expect("couts" in s).toBe(true); // l'original n'est pas touché
  });
});

describe("la lecture de tous les clients", () => {
  it("un membre limité : l'atelier n'est jamais lu pour un autre client, et rien n'en est compté", async () => {
    const limite = acces({ droits: ["clients.voir", "couts.voir"], perimetre: ["a1"] });
    const { l, appels } = lecteur(["a1", "b2"]);
    const { lectures, porte } = await lireTout(limite, 7, l);
    expect(appels.sort()).toEqual(["alertes a1", "suivi a1"]);
    expect([lectures.map((x) => x.client.id), porte]).toEqual([["a1"], true]);
    const v = agreger(lectures, limite);
    expect([v.tuiles.tours, v.tuiles.personnes, v.tuiles.enService, v.tuiles.cout?.total]).toEqual([10, 3, 1, 1.5]);
    expect(v.activite.map((x) => x.client)).toEqual(["a1"]);
    expect(v.aSurveiller.map((x) => x.client)).toEqual(["a1"]);
  });

  it("jamais plus de 4 lectures en même temps", async () => {
    const ids = Array.from({ length: 10 }, (_, i) => `c${i}`);
    const { l, appels, max } = lecteur(ids);
    const { lectures } = await lireTout(tous, 30, l);
    expect(lectures.map((x) => x.client.id)).toEqual(ids);
    expect(appels).toHaveLength(20);
    expect(max()).toBe(4);
    const deux = lecteur(ids);
    await lireTout(tous, 30, deux.l, 2);
    expect(deux.max()).toBe(2);
  });

  it("un client dont le suivi ne répond pas : injoignable, mais ses alertes sont lues et ses soucis comptés", async () => {
    const { l, appels } = lecteur(["a1", "b2", "c3"], { echec: "b2" });
    const { lectures } = await lireTout(tous, 7, l);
    const b2 = lectures.find((x) => x.client.id === "b2")!;
    expect([b2.erreur, b2.suivi, b2.alertes?.map((x) => x.genre)]).toEqual([TA.atelierLent, undefined,
      ["tour_echec", "conteneur_transmission", "conteneur_injoignable"]]);
    expect(appels.filter((x) => x.endsWith("b2"))).toEqual(["suivi b2", "alertes b2"]); // l'un après l'autre
    const v = agreger(lectures, tous);
    expect(v.injoignables).toEqual(["b2"]);
    expect(v.activite.map((x) => x.client)).toEqual(["a1", "c3"]);
    expect([v.tuiles.tours, v.tuiles.enService, v.tuiles.soucisEnCours]).toEqual([20, 3, 4]);
    expect(v.aSurveiller.map((x) => x.client)).toEqual(["b2", "a1", "c3"]); // le plus en danger en tête
  });

  it("un client muet (ni suivi ni alertes) : injoignable, sans soucis inventés", async () => {
    const { l } = lecteur(["a1", "b2"], { muet: "b2" });
    const { lectures } = await lireTout(tous, 7, l);
    expect(lectures[1]).toEqual({ client: client("b2"), erreur: TA.atelierLent });
    const v = agreger(lectures, tous);
    expect([v.injoignables, v.aSurveiller.map((x) => x.client), v.tuiles.soucisEnCours]).toEqual([["b2"], ["a1"], 1]);
  });

  it("un client jamais mis en service n'est pas lu : ni panne, ni injoignable, ni activité", async () => {
    const { l, appels } = lecteur(["a1", "j1"], { jamais: ["j1"] });
    const { lectures } = await lireTout(tous, 7, l);
    expect(appels.some((x) => x.endsWith("j1"))).toBe(false);
    expect(lectures[1]).toEqual({ client: client("j1", { version_en_service: null }) });
    const v = agreger(lectures, tous);
    expect([v.injoignables, v.aSurveiller.map((x) => x.client), v.activite.map((x) => x.client), v.tuiles.enService])
      .toEqual([[], ["a1"], ["a1"], 1]);
  });

  it("l'écran Alertes ne lit que les alertes, des seuls clients en service", async () => {
    const { l, appels } = lecteur(["a1", "b2", "j1"], { echec: "b2", jamais: ["j1"] });
    const { lectures, porte } = await lireAlertes(tous, 30, l);
    expect(appels.sort()).toEqual(["alertes a1", "alertes b2"]);
    expect([porte, lectures.map((x) => [x.client.id, x.alertes?.length ?? null, x.erreur ?? null])])
      .toEqual([true, [["a1", 2, null], ["b2", 3, null], ["j1", null, null]]]);
    const limite = acces({ droits: ["clients.voir"], perimetre: ["a1"] });
    const seul = lecteur(["a1", "b2"]);
    await lireAlertes(limite, 7, seul.l);
    expect(seul.appels).toEqual(["alertes a1"]);
  });

  it("les coûts : retirés sans couts.voir ; avec, le total des clients lus, la devise, les modèles sans tarif", async () => {
    const { l } = lecteur(["a1", "b2"], { sansTarif: { a1: ["voix", "deepseek-v4-pro"], b2: ["deepseek-v4-pro", "ecoute"] } });
    const sans = agreger((await lireTout(sansCout, 7, l)).lectures, sansCout);
    expect("cout" in sans.tuiles).toBe(false);
    expect(sans.activite.every((x) => !("cout" in x))).toBe(true);
    const lues = (await lireTout(tous, 7, l)).lectures;
    expect(lues.every((x) => x.suivi?.couts)).toBe(true);
    const avec = agreger(lues, tous);
    expect(avec.tuiles.cout).toEqual({ devise: "USD", total: 3, sansTarif: ["deepseek-v4-pro", "ecoute", "voix"] });
    expect(avec.activite.map((x) => x.cout)).toEqual([1.5, 1.5]);
    // Même si une lecture avait gardé ses coûts, agreger ne les montre pas sans le droit.
    expect("cout" in agreger(lues, sansCout).tuiles).toBe(false);
  });

  it("la vue d'ensemble : les soucis en cours comptés, à surveiller le plus grave d'abord", async () => {
    const { l } = lecteur(["a1", "b2"]);
    const v = agreger((await lireTout(tous, 7, l)).lectures, tous);
    expect(v.tuiles.soucisEnCours).toBe(2);
    expect(v.aSurveiller.map((x) => x.client)).toEqual(["a1", "b2"]);
    expect(v.activite[0]).toMatchObject({ client: "a1", entreprise: "Entreprise a1", tours: 10, personnes: 3, echecs: 2, secours: 1 });
  });
});
