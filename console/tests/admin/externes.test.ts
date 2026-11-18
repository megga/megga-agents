import { describe, expect, it } from "vitest";
import { changementsExterne, corpsVersion } from "@/lib/admin/externes";
import { TA } from "@/lib/admin/textes";
import { acces, refus } from "./aides";

// Le brouillon d'un externe : seulement les réglages simples du catalogue (champs_client), comme atelier/regles.py (appliquer)
// les tient pour le rôle client ; la console les filtre elle-même avant d'appeler l'atelier avec le jeton de MEGGA.

const CAT = { metiers: { general: [], immobilier: ["immobilier"] }, champs_client: ["metier", "nom_agent", "voix", "ton", "outils"] };
const BASE = { id: "garage-essai", metier: "immobilier", outils: ["immobilier"], consignes: "Sur mesure", voix: { voix: "v0", stabilite: 0.5 } };

describe("les changements d'un externe", () => {
  it("un externe ne règle que les champs simples du catalogue", () => {
    expect(changementsExterne({ ton: "chaleureux", nom_agent: "Max" }, BASE, CAT)).toEqual({ ton: "chaleureux", nom_agent: "Max" });
    const r = refus(() => changementsExterne({ whatsapp: {}, consignes: "x" }, BASE, CAT));
    expect(r).toMatchObject({ statut: 403, message: TA.reglagesReserves("consignes, whatsapp") });
    expect(refus(() => changementsExterne({ ton: "x" }, BASE, { ...CAT, champs_client: ["metier"] })).statut).toBe(403);
    expect([refus(() => changementsExterne([], BASE, CAT)).statut, refus(() => changementsExterne("x", BASE, CAT)).statut]).toEqual([400, 400]);
  });

  it("refuse tout réglage tenu par MEGGA, même mêlé à des réglages simples, et un corps qui n'est pas un objet", () => {
    for (const interdit of ["modeles", "id", "zone", "whatsapp", "consignes", "gestion", "roles", "catalogue", "__proto__"]) {
      const ch = JSON.parse(`{"ton": "x", "${interdit}": {}}`) as unknown;
      expect(refus(() => changementsExterne(ch, BASE, CAT)), interdit).toMatchObject({ statut: 403, message: TA.reglagesReserves(interdit) });
    }
    for (const ch of [null, undefined, 3, true]) expect(refus(() => changementsExterne(ch, BASE, CAT)), String(ch)).toMatchObject({ statut: 400, message: TA.changementsObjet });
    expect(changementsExterne({}, BASE, CAT)).toEqual({});
  });

  it("la voix se donne par son identifiant ; changer de métier retire les outils qu'il ne permet pas", () => {
    expect(changementsExterne({ voix: "v1" }, BASE, CAT)).toEqual({ voix: { voix: "v1" } });
    expect(changementsExterne({ voix: null }, BASE, CAT)).toEqual({ voix: { voix: null } });
    expect(refus(() => changementsExterne({ voix: { stabilite: 1 } }, BASE, CAT))).toMatchObject({ statut: 400, message: TA.voixIdentifiant });
    expect(refus(() => changementsExterne({ voix: 3 }, BASE, CAT)).statut).toBe(400);
    expect(changementsExterne({ metier: "general" }, BASE, CAT)).toEqual({ metier: "general", outils: [] });
    expect(changementsExterne({ metier: "general", outils: ["x"] }, BASE, CAT)).toEqual({ metier: "general", outils: ["x"] });
  });

  it("changer de métier garde les outils qu'il permet ; un métier inconnu n'en permet aucun", () => {
    expect(changementsExterne({ metier: "immobilier" }, BASE, CAT)).toEqual({ metier: "immobilier", outils: ["immobilier"] });
    expect(changementsExterne({ metier: "constructor" }, BASE, CAT)).toEqual({ metier: "constructor", outils: [] });
    expect(changementsExterne({ metier: "immobilier" }, { id: "garage-essai" }, CAT)).toEqual({ metier: "immobilier", outils: [] });
  });

  it("ne change pas l'objet reçu", () => {
    const ch = { voix: "v1", metier: "general" };
    changementsExterne(ch, BASE, CAT);
    expect(ch).toEqual({ voix: "v1", metier: "general" });
  });
});

describe("le corps d'une version", () => {
  it("un externe ne prépare pas d'après un modèle par métier", () => {
    const ext = acces({ externe: true, droits: ["versions.preparer"], perimetre: ["garage-essai"] });
    expect(refus(() => corpsVersion(ext, { gabarit: "immobilier" }, BASE, CAT))).toMatchObject({ statut: 403, message: TA.gabaritReserve });
    expect(corpsVersion(ext, { base: 2, changements: { ton: "x" }, forcer: true }, BASE, CAT)).toEqual({ base: 2, changements: { ton: "x" } });
    expect(corpsVersion(acces({ superadmin: true }), { gabarit: "immobilier" }, BASE, CAT)).toEqual({ gabarit: "immobilier" });
  });

  it("un externe : ses changements filtrés, sans base quand il n'en donne pas ; un modèle même vide est refusé", () => {
    const ext = acces({ externe: true, droits: ["versions.preparer"], perimetre: ["garage-essai"] });
    expect(corpsVersion(ext, { changements: { voix: "v1" } }, BASE, CAT)).toEqual({ changements: { voix: { voix: "v1" } } });
    expect(refus(() => corpsVersion(ext, { changements: { consignes: "x" } }, BASE, CAT)).statut).toBe(403);
    expect(refus(() => corpsVersion(ext, { gabarit: null, changements: {} }, BASE, CAT)).statut).toBe(403);
    expect(refus(() => corpsVersion(ext, {}, BASE, CAT))).toMatchObject({ statut: 400, message: TA.changementsObjet });
  });

  it("un membre interne : le corps tel quel ; un corps qui n'est pas un objet est refusé à tous", () => {
    const interne = acces({ droits: ["versions.preparer"] });
    const corps = { base: 1, changements: { consignes: "Nouvelles", whatsapp: { numero_id: "1" } } };
    expect(corpsVersion(interne, corps, BASE, CAT)).toEqual(corps);
    for (const a of [interne, acces({ externe: true, droits: ["versions.preparer"], perimetre: ["garage-essai"] })]) {
      for (const c of [null, [], "x"]) expect(refus(() => corpsVersion(a, c, BASE, CAT)).statut).toBe(400);
    }
  });
});
