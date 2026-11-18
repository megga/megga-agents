import type { DatabaseSync } from "node:sqlite";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PUT } from "@/app/api/admin/tarifs/route";
import { RefusChamps } from "@/lib/admin/atelier";
import { lireJournal } from "@/lib/admin/journal";
import { TA } from "@/lib/admin/textes";
import { acces, baseEssai, membre } from "./aides";

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

const TARIFS = {
  devise: "USD",
  modeles: { "claude-sonnet-5-5": { entree: 3, sortie: 15, cache_lecture: 0.3, cache_ecriture: 3.75 }, "deepseek-v4-pro": { entree: 0.5, sortie: 2 } },
  voix_par_1000_caracteres: 0.18,
  par_vocal_entendu: null,
};

function regler(qui: string, corps: string) {
  return PUT(new Request("http://localhost/api/admin/tarifs", { method: "PUT", headers: { origin: "http://localhost", "x-essai-qui": qui }, body: corps }),
    { params: Promise.resolve({}) });
}

const journal = () => lireJournal(etat.db, acces({ superadmin: true }), { page: 1 }).lignes;

beforeEach(async () => {
  reglerTarifs.mockReset();
  etat.db = await baseEssai();
  membre(etat.db, { utilisateur: "finance", role: "finance" });
});

describe("régler les tarifs", () => {
  it("un membre Finance : le corps part tel quel à l'atelier, les tarifs gardés sont rendus, le geste est noté", async () => {
    const gardes = { ...TARIFS, modeles: { ...TARIFS.modeles, "deepseek-v4-pro": { entree: 0.5, sortie: 2, cache_lecture: 0, cache_ecriture: 0 } } };
    reglerTarifs.mockResolvedValue(gardes);
    const r = await regler("finance", JSON.stringify(TARIFS));
    expect([r.status, await r.json()]).toEqual([200, gardes]);
    expect(reglerTarifs.mock.calls).toEqual([[TARIFS]]);
    const [ligne] = journal();
    expect(ligne).toMatchObject({ qui: "finance", action: "tarifs.regler", cible: null, resultat: "ok", detail: TARIFS });
  });

  it("un refus 422 de l'atelier rend sa phrase et ses messages champ par champ, noté refusé", async () => {
    const champs = [{ champ: "modeles.deepseek-v4-pro.entree", message: "La valeur doit être d'au moins 0." }];
    reglerTarifs.mockRejectedValue(new RefusChamps(422, "tarifs invalides", champs));
    const r = await regler("finance", JSON.stringify({ ...TARIFS, modeles: { "deepseek-v4-pro": { entree: -1, sortie: 2 } } }));
    expect([r.status, await r.json()]).toEqual([422, { erreur: "tarifs invalides", champs }]);
    expect(journal().map((l) => `${l.action} ${l.resultat}`)).toEqual(["tarifs.regler refuse 422"]);
  });

  it("un corps qui n'est pas un objet est refusé avant l'atelier", async () => {
    for (const corps of ["null", "[]", '"USD"', "pas du json"]) {
      const r = await regler("finance", corps);
      expect([r.status, await r.json()], corps).toEqual([400, { erreur: TA.tarifsInvalides }]);
    }
    expect(reglerTarifs).not.toHaveBeenCalled();
  });
});
