import { Refus } from "@/lib/agents";
import type { Acces } from "./acces";
import type { Catalogue } from "./atelier";
import { TA } from "./textes";

// Le brouillon d'un externe : seulement les réglages simples d'un client (les champs_client du catalogue de l'atelier).
// L'atelier, appelé avec le jeton de MEGGA, accepterait tout : la console tient donc elle-même la règle qu'atelier/regles.py
// (appliquer) tient pour le rôle client, avant tout appel. La voix se donne par son identifiant ; changer de métier retire
// les outils qu'il ne permet pas. Un modèle par métier, appliqué au nom de MEGGA, remplacerait les consignes sur mesure :
// un externe ne s'en sert pas.

type CatalogueSimple = Pick<Catalogue, "metiers" | "champs_client">;

const estObjet = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);

/** Les changements d'un externe, tels qu'ils partent à l'atelier ; un réglage hors des champs simples : 403, rien ne part. */
export function changementsExterne(changements: unknown, base: Record<string, unknown>, catalogue: CatalogueSimple): Record<string, unknown> {
  if (!estObjet(changements)) throw new Refus(400, TA.changementsObjet);
  const ch: Record<string, unknown> = { ...changements };
  const interdits = Object.keys(ch).filter((k) => !catalogue.champs_client.includes(k)).sort();
  if (interdits.length) throw new Refus(403, TA.reglagesReserves(interdits.join(", ")));
  if (Object.hasOwn(ch, "voix")) {
    if (ch.voix !== null && typeof ch.voix !== "string") throw new Refus(400, TA.voixIdentifiant);
    ch.voix = { voix: ch.voix };
  }
  if (Object.hasOwn(ch, "metier") && !Object.hasOwn(ch, "outils")) {
    const permis = typeof ch.metier === "string" && Object.hasOwn(catalogue.metiers, ch.metier) ? catalogue.metiers[ch.metier] : [];
    const outils: unknown[] = Array.isArray(base.outils) ? base.outils : [];
    ch.outils = outils.filter((o) => typeof o === "string" && permis.includes(o));
  }
  return ch;
}

/**
 * Le corps d'une version (valider, préparer) tel qu'il part à l'atelier. Un membre interne : tel quel. Un externe : ni modèle
 * par métier, ni forcer, ni rien d'autre que { base?, changements }, ses changements filtrés d'après la base qu'il prend.
 */
export function corpsVersion(a: Acces, corps: unknown, base: Record<string, unknown>, catalogue: CatalogueSimple): Record<string, unknown> {
  if (!estObjet(corps)) throw new Refus(400, TA.corpsObjet);
  if (!a.externe) return corps;
  if (Object.hasOwn(corps, "gabarit")) throw new Refus(403, TA.gabaritReserve);
  return { ...(Object.hasOwn(corps, "base") ? { base: corps.base } : {}), changements: changementsExterne(corps.changements, base, catalogue) };
}
