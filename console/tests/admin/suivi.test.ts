import { describe, expect, it } from "vitest";
import { RefusChamps, type Alerte, type ClientAtelier, type Jours, type Lecteur, type Suivi } from "@/lib/admin/atelier";
import {
  estEnCours,
  etatClient,
  GENRES_CONNUS,
  GENRES_DE_L_INSTANT,
  horsCloudflare,
  joursDe,
  lireAlertes,
  lireSuivis,
  modelesSansTarif,
  sansCouts,
  type LectureClient,
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

  it("les modèles sans tarif : l'union triée des lectures, sans la voix ni l'écoute, un { erreur } ou un client sans suivi ignoré", () => {
    const sansSesCouts = suiviDe("e5", 7);
    delete sansSesCouts.couts;
    const lectures: LectureClient[] = [
      { client: client("a1"), suivi: suiviDe("a1", 7, 1, ["voix", "mistral-large", "deepseek-v4-pro", "ecoute"]) },
      { client: client("b2"), suivi: { ...suiviDe("b2", 7), couts: { erreur: "activité illisible" } } },
      { client: client("c3"), suivi: suiviDe("c3", 7, 1, ["deepseek-v4-pro"]) },
      { client: client("d4"), erreur: TA.atelierLent },
      { client: client("e5"), suivi: sansSesCouts },
      { client: client("j1", { version_en_service: null }) },
    ];
    expect(modelesSansTarif(lectures)).toEqual(["deepseek-v4-pro", "mistral-large"]);
    expect(modelesSansTarif([])).toEqual([]);
  });
});

describe("la lecture de tous les clients", () => {

  it("jamais plus de 4 lectures en même temps", async () => {
    const ids = Array.from({ length: 10 }, (_, i) => `c${i}`);
    const { l, appels, max } = lecteur(ids);
    const { lectures } = await lireSuivis(tous, 30, l);
    expect(lectures.map((x) => x.client.id)).toEqual(ids);
    expect(appels).toHaveLength(10);
    expect(max()).toBe(4);
    const deux = lecteur(ids);
    await lireSuivis(tous, 30, deux.l, 2);
    expect(deux.max()).toBe(2);
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

  it("la lecture des seuls suivis (l'écran Tarifs) : aucune alerte lue, le périmètre et les clients jamais mis en service tenus", async () => {
    const { l, appels, max } = lecteur(["a1", "b2", "j1", "c3", "d4", "e5"], { echec: "b2", jamais: ["j1"] });
    const { lectures, porte } = await lireSuivis(tous, 30, { clients: l.clients, suivi: l.suivi });
    expect(appels.sort()).toEqual(["suivi a1", "suivi b2", "suivi c3", "suivi d4", "suivi e5"]);
    expect(max()).toBeLessThanOrEqual(4);
    expect([porte, lectures.map((x) => [x.client.id, !!x.suivi, x.alertes ?? null, x.erreur ?? null])]).toEqual([true, [
      ["a1", true, null, null], ["b2", false, null, TA.atelierLent], ["j1", false, null, null], ["c3", true, null, null],
      ["d4", true, null, null], ["e5", true, null, null]]]);
    const seul = lecteur(["a1", "b2"]);
    await lireSuivis(acces({ droits: ["clients.voir", "couts.voir"], perimetre: ["a1"] }), 7, seul.l);
    expect(seul.appels).toEqual(["suivi a1"]);
  });
});
