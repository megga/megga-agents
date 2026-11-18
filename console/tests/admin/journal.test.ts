import type { DatabaseSync } from "node:sqlite";
import { beforeEach, describe, expect, it } from "vitest";
import { filtresDe, LIGNES_PAR_PAGE, lireJournal, nettoyer, noter } from "@/lib/admin/journal";
import { TA } from "@/lib/admin/textes";
import { acces, baseEssai, T0 } from "./aides";

let db: DatabaseSync;
beforeEach(async () => {
  db = await baseEssai();
});

const geste = (qui: string, action: string, cible: string | null, detail: unknown = null) =>
  ({ qui, courriel: `${qui}@megga.test`, action, cible, resultat: "ok", detail });

const minute = (n: number) => new Date(T0.getTime() + n * 60_000);

describe("le journal", () => {
  it("ne garde aucun secret, et réduit un numéro à ses quatre derniers chiffres", () => {
    expect(nettoyer({ jeton: "j", cle: "mk_1", cle_publique: "p", motDePasse: "x", password: "y", Authorization: "Bearer z",
      changements: { ton: "chaleureux" }, personne: "+41791234567", liste: [{ token: "t" }] }))
      .toEqual({ jeton: "[masqué]", cle: "[masqué]", cle_publique: "[masqué]", motDePasse: "[masqué]", password: "[masqué]",
        Authorization: "[masqué]", changements: { ton: "chaleureux" }, personne: "…4567", liste: [{ token: "[masqué]" }] });
    expect(nettoyer({ secret_client: { a: 1 }, CLE: 3, n: "12345", m: "123456", tel: "+12345678901234567890", long: "123456789012345678901" }))
      .toEqual({ secret_client: "[masqué]", CLE: "[masqué]", n: "12345", m: "123456", tel: "…7890", long: "123456789012345678901" });
    expect([nettoyer("+41791234567"), nettoyer(null), nettoyer(undefined), nettoyer(7)]).toEqual(["…4567", null, undefined, 7]);
  });

  it("ne réduit un numéro que sous la clé personne, ou sous sa forme internationale : un client tout en chiffres reste entier", () => {
    expect(nettoyer({ perimetre: ["1234567"], client: "1234567", n: "0041791234567", personne: "0041791234567",
      liste: [{ personne: ["0041791234567"] }], tel: "+41791234567" }))
      .toEqual({ perimetre: ["1234567"], client: "1234567", n: "0041791234567", personne: "…4567", liste: [{ personne: ["…4567"] }], tel: "…4567" });
    expect([nettoyer("0041791234567"), nettoyer("1234567")]).toEqual(["0041791234567", "1234567"]);
  });

  it("rend le plus récent d'abord, avec un détail nettoyé même si l'appelant ne l'a pas fait", () => {
    const s = acces({ utilisateur: "s", superadmin: true });
    noter(db, geste("s", "acces.jeton_cree", "client:a1", { jeton: "secret", personne: "+41791234567" }), minute(0));
    noter(db, { qui: null, courriel: null, action: "invitations.accepter", cible: "membre:x", resultat: "refuse 404", detail: undefined }, minute(1));
    const { lignes, pages } = lireJournal(db, s, { page: 1 });
    expect(pages).toBe(1);
    expect(lignes.map((l) => l.action)).toEqual(["invitations.accepter", "acces.jeton_cree"]);
    expect(lignes[1]).toMatchObject({ quand: minute(0).toISOString(), qui: "s", courriel: "s@megga.test", cible: "client:a1", resultat: "ok",
      detail: { jeton: "[masqué]", personne: "…4567" } });
    expect(lignes[0]).toMatchObject({ qui: null, courriel: null, resultat: "refuse 404", detail: null });
    expect(JSON.stringify(db.prepare("SELECT * FROM admin_journal").all())).not.toContain("secret");
  });

  it("nettoie aussi la cible : un numéro réduit, un secret masqué", () => {
    const s = acces({ utilisateur: "s", superadmin: true });
    for (const cible of ["personne:+41791234567", "cle:mk_1", "jeton:abc", "client:a1", "+41791234567", "role:ro_1:2", null]) {
      noter(db, geste("s", "essai", cible), T0);
    }
    expect(lireJournal(db, s, { page: 1 }).lignes.map((l) => l.cible).reverse())
      .toEqual(["personne:…4567", "cle:[masqué]", "jeton:[masqué]", "client:a1", "…4567", "role:ro_1:2", null]);
    expect(JSON.stringify(db.prepare("SELECT cible FROM admin_journal").all())).not.toMatch(/41791234567|mk_1|abc/);
  });

  it("ne réduit le numéro d'une cible que pour une personne : un client tout en chiffres reste entier", () => {
    const s = acces({ utilisateur: "s", superadmin: true });
    for (const cible of ["client:1234567", "compte:00123456", "membre:9876543", "personne:0041791234567"]) noter(db, geste("s", "essai", cible), T0);
    expect(lireJournal(db, s, { page: 1 }).lignes.map((l) => l.cible).reverse())
      .toEqual(["client:1234567", "compte:00123456", "membre:9876543", "personne:…4567"]);
  });

  it("borne un détail à 2048 caractères, rendu alors tel quel", () => {
    const s = acces({ utilisateur: "s", superadmin: true });
    const gros = { liste: Array.from({ length: 500 }, (_, i) => `élément ${i}`) };
    noter(db, geste("s", "essai", null, gros), T0);
    expect((db.prepare("SELECT length(detail) AS n FROM admin_journal").get() as { n: number }).n).toBe(2048);
    expect(lireJournal(db, s, { page: 1 }).lignes[0].detail).toBe(JSON.stringify(gros).slice(0, 2048));
    noter(db, geste("s", "essai", null, { court: "oui" }), minute(1));
    expect(lireJournal(db, s, { page: 1 }).lignes[0].detail).toEqual({ court: "oui" });
  });

  it("se lit par pages de cinquante", () => {
    const s = acces({ utilisateur: "s", superadmin: true });
    for (let i = 0; i < 120; i++) noter(db, geste("s", `geste.${i}`, null), minute(i));
    expect(LIGNES_PAR_PAGE).toBe(50);
    expect(lireJournal(db, s, { page: 1 })).toMatchObject({ pages: 3 });
    expect(lireJournal(db, s, { page: 1 }).lignes[0].action).toBe("geste.119");
    const p3 = lireJournal(db, s, { page: 3 });
    expect(p3.lignes).toHaveLength(20);
    expect(p3.lignes.at(-1)!.action).toBe("geste.0");
    expect(lireJournal(db, s, { page: 1 }).lignes).toHaveLength(50);
  });

  it("ramène une page demandée trop loin à la dernière", () => {
    const s = acces({ utilisateur: "s", superadmin: true });
    expect(lireJournal(db, s, { page: 4 })).toEqual({ lignes: [], pages: 1, page: 1 });
    for (let i = 0; i < 120; i++) noter(db, geste("s", `geste.${i}`, null), minute(i));
    const loin = lireJournal(db, s, { page: 9 });
    expect([loin.page, loin.pages, loin.lignes.length, loin.lignes.at(-1)!.action]).toEqual([3, 3, 20, "geste.0"]);
    expect(lireJournal(db, s, { page: 2 }).page).toBe(2);
  });

  it("un membre limité à une liste ne voit que ses gestes et ceux qui touchent ses clients", () => {
    const m = acces({ utilisateur: "m", droits: ["journal.voir"], perimetre: ["a1"] });
    noter(db, geste("m", "roles.creer", "role:r1"), minute(0));
    noter(db, geste("x", "clients.activer", "client:a1"), minute(1));
    noter(db, geste("x", "clients.activer", "client:b2"), minute(2));
    noter(db, geste("x", "roles.modifier", "role:x"), minute(3));
    noter(db, geste("x", "comptes.suspendu", "compte:c1"), minute(4));
    expect(lireJournal(db, m, { page: 1 }).lignes.map((l) => `${l.qui} ${l.cible}`)).toEqual(["x client:a1", "m role:r1"]);
    expect(lireJournal(db, m, { client: "b2", page: 1 }).lignes).toEqual([]);
    expect(lireJournal(db, acces({ utilisateur: "t", droits: ["journal.voir"] }), { page: 1 }).lignes).toHaveLength(5);
  });

  it("se trie par membre, action, client et période (jours de Zurich, inclus)", () => {
    const s = acces({ utilisateur: "s", superadmin: true });
    noter(db, geste("a", "clients.activer", "client:a1"), new Date("2026-11-16T22:59:59Z")); // le 16 à 23:59:59 à Zurich
    noter(db, geste("b", "clients.activer", "client:b2"), new Date("2026-11-16T23:00:00Z")); // le 17 à 00:00
    noter(db, geste("a", "clients.reprise", "client:b2"), new Date("2026-11-18T22:59:59.999Z")); // le 18 à 23:59:59.999
    noter(db, geste("b", "roles.creer", "role:r"), new Date("2026-11-18T23:00:00Z")); // le 19 à 00:00
    const actions = (f: Parameters<typeof lireJournal>[2]) => lireJournal(db, s, f).lignes.map((l) => `${l.qui} ${l.action} ${l.cible}`);
    expect(actions({ membre: "a", page: 1 })).toEqual(["a clients.reprise client:b2", "a clients.activer client:a1"]);
    expect(actions({ action: "clients.activer", page: 1 })).toEqual(["b clients.activer client:b2", "a clients.activer client:a1"]);
    expect(actions({ client: "b2", page: 1 })).toEqual(["a clients.reprise client:b2", "b clients.activer client:b2"]);
    expect(actions({ depuis: "2026-11-17", jusqua: "2026-11-18", page: 1 })).toEqual(["a clients.reprise client:b2", "b clients.activer client:b2"]);
    expect(actions({ membre: "b", depuis: "2026-11-18", page: 1 })).toEqual(["b roles.creer role:r"]);
  });

  it("garde un geste dans le jour où l'écran le montre, à Zurich, en hiver comme en été", () => {
    const s = acces({ utilisateur: "s", superadmin: true });
    const instants = {
      "hiver.veille": "2027-01-04T22:59:59.999Z", "hiver.nuit": "2027-01-04T23:30:00Z", "hiver.soir": "2027-01-05T22:59:59.999Z",
      "hiver.lendemain": "2027-01-05T23:00:00Z", "ete.veille": "2027-07-04T21:59:59.999Z", "ete.nuit": "2027-07-04T22:30:00Z",
      "ete.soir": "2027-07-05T21:59:59.999Z", "ete.lendemain": "2027-07-05T22:00:00Z",
    };
    for (const [action, quand] of Object.entries(instants)) noter(db, geste("a", action, null), new Date(quand));
    expect([TA.instant(instants["hiver.nuit"]), TA.instant(instants["ete.nuit"])]).toEqual(["05.01.2027 00:30", "05.07.2027 00:30"]);
    const jour = (j: string) => lireJournal(db, s, { depuis: j, jusqua: j, page: 1 }).lignes.map((l) => l.action).reverse();
    expect(jour("2027-01-05")).toEqual(["hiver.nuit", "hiver.soir"]);
    expect(jour("2027-07-05")).toEqual(["ete.nuit", "ete.soir"]);
    expect(lireJournal(db, s, { depuis: "2027-01-05", page: 1 }).lignes.at(-1)!.action).toBe("hiver.nuit");
    expect(lireJournal(db, s, { jusqua: "2027-01-04", page: 1 }).lignes.map((l) => l.action)).toEqual(["hiver.veille"]);
  });

  it("lit ses filtres dans l'adresse, sans erreur sur une valeur mal formée", () => {
    expect(filtresDe({ page: "abc" }).page).toBe(1);
    expect(filtresDe({ page: "0" }).page).toBe(1);
    expect(filtresDe({ page: "2.5" }).page).toBe(1);
    expect(filtresDe({})).toEqual({ page: 1 });
    expect(filtresDe({ page: "3", membre: " a ", action: "roles.creer", client: "a1", depuis: "2026-11-01", jusqua: "2026-11-30" }))
      .toEqual({ page: 3, membre: "a", action: "roles.creer", client: "a1", depuis: "2026-11-01", jusqua: "2026-11-30" });
    expect(filtresDe({ page: ["2", "5"], depuis: "hier", jusqua: "2026-13-40", membre: "" })).toEqual({ page: 2 });
  });
});
