import { describe, expect, it } from "vitest";
import { debut, parJour, tempsForts, type EchangeVu } from "@/components/console/activite-donnees";

const e = (id: string, quand: number, etat: EchangeVu["etat"] = "repondu"): EchangeVu => ({
  id, quand, de: "ag_alix", a: "ag_lea", question: "?", etat, reponse: etat === "repondu" ? "Oui." : null,
});

describe("la page Activité", () => {
  it("met les soucis d'abord, puis un nombre pair d'échanges, quatre au plus", () => {
    const l = [e("a", 6), e("b", 5, "hors_delai"), e("c", 4), e("d", 3), e("f", 2), e("g", 1), e("h", 0, "echec")];
    const { forts, reste } = tempsForts(l);
    expect(forts.map((x) => x.id)).toEqual(["b", "h", "a", "c", "d", "f"]);
    expect(reste.map((x) => x.id)).toEqual(["g"]);
    expect(tempsForts([e("a", 3), e("b", 2), e("c", 1)]).forts.map((x) => x.id)).toEqual(["a", "b"]);
    expect(tempsForts([e("a", 3)]).forts.map((x) => x.id)).toEqual(["a"]);
    expect(tempsForts([])).toEqual({ forts: [], reste: [] });
  });

  it("range le reste par jour, à l'heure locale", () => {
    const midi = new Date(2026, 10, 19, 12).getTime() / 1000;
    const jours = parJour([e("a", midi), e("b", midi - 3600), e("c", midi - 86400)]);
    expect(jours.map(([j, l]) => [j, l.map((x) => x.id)])).toEqual([["2026-11-19", ["a", "b"]], ["2026-11-18", ["c"]]]);
  });

  it("compte les périodes depuis minuit, ou en jours", () => {
    const m = new Date(2026, 10, 19, 15, 30);
    expect(debut("jour", m)).toBe(new Date(2026, 10, 19).getTime() / 1000);
    expect(debut("semaine", m)).toBe(m.getTime() / 1000 - 7 * 86400);
    expect(debut("an", m)).toBe(m.getTime() / 1000 - 365 * 86400);
  });
});
