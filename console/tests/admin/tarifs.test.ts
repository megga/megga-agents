import type { DatabaseSync } from "node:sqlite";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PUT } from "@/app/api/admin/tarifs/route";
import { RefusChamps } from "@/lib/admin/atelier";
import { lireJournal } from "@/lib/admin/journal";
import { TA } from "@/lib/admin/textes";
import { acces, dbEssai, membre } from "./aides";

// La route des tarifs, appelée comme Next.js l'appelle : la session vient de l'en-tête x-essai-qui, la base est celle de
// l'essai, l'atelier est simulé. La garde (droit, origine) a ses essais ailleurs (garde.test.ts, routes.test.ts).

const etat = vi.hoisted(() => ({ db: undefined as unknown as DatabaseSync }));
vi.mock("@/lib/base", async (original) => ({ ...(await original<typeof import("@/lib/base")>()), base: () => etat.db }));
vi.mock("@/lib/auth", async (original) => ({
  ...(await original<typeof import("@/lib/auth")>()),
  sessionDe: async (r: Request) => {
    const qui = r.headers.get("x-essai-qui");
    return qui ? { user: { id: qui, email: `${qui}@megga.test`, name: qui } } : null;
  },
}));

const reglerTarifs = vi.hoisted(() => vi.fn());
vi.mock("@/lib/admin/atelier", async (original) => {
  const vrai = await original<typeof import("@/lib/admin/atelier")>();
  return { ...vrai, atelier: { ...vrai.atelier, reglerTarifs } };
});

// Des montants qu'aucune autre valeur de l'essai ne contient : le journal ne doit en garder aucun.
const TARIFS = {
  devise: "USD",
  modeles: { "deepseek-v4-pro": { entree: 0.5551, sortie: 2.1919 }, "claude-sonnet-5-5": { entree: 3.1415, sortie: 27.1828, cache_lecture: 0.4242, cache_ecriture: 9.8765 } },
  voix_par_1000_caracteres: 0.1818,
  par_vocal_entendu: null,
};
const MONTANTS = ["0.5551", "2.1919", "3.1415", "27.1828", "0.4242", "9.8765", "0.1818"];
/** Ce que le journal garde d'un réglage : ce qui a été réglé, sans aucun montant. */
const RESUME = { devise: "USD", modeles: ["claude-sonnet-5-5", "deepseek-v4-pro"], voix: true, ecoute: false };
const tableJournal = () => JSON.stringify(etat.db.prepare("SELECT * FROM admin_journal").all());

function regler(qui: string, corps: string) {
  return PUT(new Request("http://localhost/api/admin/tarifs", { method: "PUT", headers: { origin: "http://localhost", "x-essai-qui": qui }, body: corps }),
    { params: Promise.resolve({}) });
}

const journal = () => lireJournal(etat.db, acces({ superadmin: true }), { page: 1 }).lignes;

beforeEach(async () => {
  reglerTarifs.mockReset();
  etat.db = await dbEssai();
  membre(etat.db, { utilisateur: "finance", role: "finance" });
});

describe("régler les tarifs", () => {
  it("un membre Finance : le corps part tel quel à l'atelier, les tarifs gardés sont rendus, le geste est noté sans montant", async () => {
    const gardes = { ...TARIFS, modeles: { ...TARIFS.modeles, "deepseek-v4-pro": { entree: 0.5, sortie: 2, cache_lecture: 0, cache_ecriture: 0 } } };
    reglerTarifs.mockResolvedValue(gardes);
    const r = await regler("finance", JSON.stringify(TARIFS));
    expect([r.status, await r.json()]).toEqual([200, gardes]);
    expect(reglerTarifs.mock.calls).toEqual([[TARIFS]]);
    const [ligne] = journal();
    expect(ligne).toMatchObject({ qui: "finance", action: "tarifs.regler", cible: null, resultat: "ok", detail: RESUME });
    for (const m of MONTANTS) expect(tableJournal(), m).not.toContain(m);
  });

  it("un refus 422 de l'atelier rend sa phrase et ses messages champ par champ, noté refusé sans montant", async () => {
    const champs = [{ champ: "modeles.deepseek-v4-pro.entree", message: "La valeur doit être d'au moins 0." }];
    reglerTarifs.mockRejectedValue(new RefusChamps(422, "tarifs invalides", champs));
    const r = await regler("finance", JSON.stringify({ ...TARIFS, devise: "usd", modeles: { "deepseek-v4-pro": { entree: -1.2345, sortie: 2.1919 } },
      par_vocal_entendu: 0.4242 }));
    expect([r.status, await r.json()]).toEqual([422, { erreur: "tarifs invalides", champs }]);
    expect(journal().map((l) => [l.action, l.resultat, l.detail])).toEqual([["tarifs.regler", "refuse 422",
      { devise: "usd", modeles: ["deepseek-v4-pro"], voix: true, ecoute: true }]]);
    for (const m of [...MONTANTS, "1.2345"]) expect(tableJournal(), m).not.toContain(m);
  });

  it("refusé à un membre sans tarifs.regler, le geste est noté sans montant", async () => {
    membre(etat.db, { utilisateur: "lecteur", role: "lecture" });
    expect((await regler("lecteur", JSON.stringify(TARIFS))).status).toBe(403);
    expect(journal().map((l) => [l.qui, l.resultat, l.detail])).toEqual([["lecteur", "refuse 403", RESUME]]);
    for (const m of MONTANTS) expect(tableJournal(), m).not.toContain(m);
    expect(reglerTarifs).not.toHaveBeenCalled();
  });

  it("un corps qui n'est pas un objet est refusé avant l'atelier", async () => {
    for (const corps of ["null", "[]", '"USD"', "pas du json"]) {
      const r = await regler("finance", corps);
      expect([r.status, await r.json()], corps).toEqual([400, { erreur: TA.tarifsInvalides }]);
    }
    expect(reglerTarifs).not.toHaveBeenCalled();
    expect(journal().map((l) => l.detail)).toEqual([null, null, null, null]);
  });
});
