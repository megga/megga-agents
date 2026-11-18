import { Refus } from "@/lib/agents";
import type { Acces } from "./acces";
import type { Catalogue } from "./atelier";
import { estObjet } from "./champs";
import { TA } from "./textes";
import { numeroVersion } from "./versions";

// Le brouillon d'un externe : seulement les réglages simples d'un client (les champs_client du catalogue de l'atelier).
// L'atelier, appelé avec le jeton de MEGGA, accepterait tout : la console tient donc elle-même la règle qu'atelier/regles.py
// (appliquer) tient pour le rôle client, avant tout appel. La voix se donne par son identifiant ; changer de métier retire
// les outils qu'il ne permet pas. Un modèle par métier, appliqué au nom de MEGGA, remplacerait les consignes sur mesure :
// un externe ne s'en sert pas. Il ne choisit pas non plus sa base : une version ancienne remettrait d'anciens réglages de MEGGA
// (consignes, numéro, modèles), que l'atelier ne compare pas pour MEGGA (reglages_de_megga).

type CatalogueSimple = Pick<Catalogue, "metiers" | "champs_client">;

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

/** Ce que corpsPourAtelier lit de l'atelier (atelier.ts) : remplaçable dans les essais. */
type Lecteur = {
  client: (id: string) => Promise<{ version_en_service: number | null; derniere_version: number | null }>;
  version: (id: string, n: number) => Promise<{ config?: Record<string, unknown> }>;
  catalogue: () => Promise<CatalogueSimple>;
};

const SANS_CATALOGUE: CatalogueSimple = { metiers: {}, champs_client: [] };

/**
 * Le corps d'une version prêt pour l'atelier (valider, préparer), qui nomme toujours sa base : celle qui a servi au filtre et à
 * l'aperçu, jamais « la dernière » de l'atelier au moment de l'écriture. Un interne nomme la sienne, sinon la dernière version.
 * Un externe ne la choisit pas : la version en service, sinon la dernière ; en nommer une autre est refusé (403), rien ne part.
 * Un corps que corpsVersion refuse d'emblée (pas un objet ; un externe qui demande un modèle par métier) : rien n'est lu.
 * Rend le corps et la base qu'il porte, que la route précise au journal (detailVersion).
 */
export async function corpsPourAtelier(a: Acces, id: string, corps: unknown, l: Lecteur): Promise<{ corps: Record<string, unknown>; base: number }> {
  const pret = await corpsAvecBase(a, id, corps, l);
  return { corps: pret, base: pret.base as number };
}

/** Le corps prêt, qui porte toujours base: n (chaque chemin qui ne lève pas la pose). */
async function corpsAvecBase(a: Acces, id: string, corps: unknown, l: Lecteur): Promise<Record<string, unknown>> {
  if (!estObjet(corps) || (a.externe && Object.hasOwn(corps, "gabarit"))) return corpsVersion(a, corps, {}, SANS_CATALOGUE);
  const nommee = typeof corps.base === "number" ? numeroVersion(corps.base) : null;
  if (!a.externe) {
    if (corps.base != null && nommee === null) throw new Refus(400, TA.baseInvalide);
    const n = nommee ?? (await l.client(id)).derniere_version;
    if (n === null) throw new Refus(404, TA.introuvable); // aucune version : l'atelier n'aurait pas de base non plus
    return { ...corps, base: n };
  }
  const c = await l.client(id);
  const n = c.version_en_service ?? c.derniere_version;
  if (n === null) throw new Refus(404, TA.introuvable);
  if (corps.base != null && nommee !== n) throw new Refus(403, TA.baseImposee);
  const [v, catalogue] = await Promise.all([l.version(id, n), l.catalogue()]);
  return { ...corpsVersion(a, corps, v.config ?? {}, catalogue), base: n };
}
