import "server-only";
import { randomUUID } from "node:crypto";
import type { Base } from "./donnees/base";
import { COULEURS, YEUX } from "./mascotte/couleurs";
import { IDS_METIERS } from "./metiers";
import { T } from "./textes";

export type Agent = {
  id: string;
  prenom: string;
  metier: string;
  couleur: number;
  yeux: number;
  epingle: boolean;
  creeLe: string;
};

export const PRENOM_MAX = 20;
export const EPINGLES_MAX = 3;

export class Refus extends Error {
  constructor(public statut: number, message: string) {
    super(message);
  }
}

type Ligne = { id: string; prenom: string; metier: string; couleur: number; yeux: number; epingle: number; cree_le: string };

function versAgent(l: Ligne): Agent {
  return { id: l.id, prenom: l.prenom, metier: l.metier, couleur: l.couleur, yeux: l.yeux, epingle: !!l.epingle, creeLe: l.cree_le };
}

/** Ce que la création accepte : un prénom et un métier ; couleur et yeux facultatifs. */
export function valider(corps: unknown): { prenom: string; metier: string; couleur: number; yeux: number } {
  const c = (corps && typeof corps === "object" ? corps : {}) as Record<string, unknown>;
  const prenom = typeof c.prenom === "string" ? c.prenom.trim().replace(/\s+/g, " ") : "";
  if (!prenom) throw new Refus(400, T.prenomManquant);
  if ([...prenom].length > PRENOM_MAX) throw new Refus(400, T.prenomTropLong(PRENOM_MAX));
  const metier = typeof c.metier === "string" ? c.metier : "";
  if (!IDS_METIERS.includes(metier)) throw new Refus(400, T.metierManquant);
  const entier = (v: unknown, n: number) => (Number.isInteger(v) && (v as number) >= 0 && (v as number) < n ? (v as number) : 0);
  return { prenom, metier, couleur: entier(c.couleur, COULEURS.length), yeux: entier(c.yeux, YEUX.length) };
}

export async function lister(b: Base, utilisateur: string): Promise<Agent[]> {
  const lignes = await b.tous<Ligne>("SELECT * FROM agent WHERE utilisateur = ? ORDER BY cree_le DESC, id DESC", utilisateur);
  return lignes.map(versAgent);
}

export async function trouver(b: Base, utilisateur: string, id: string): Promise<Agent | undefined> {
  const l = await b.un<Ligne>("SELECT * FROM agent WHERE utilisateur = ? AND id = ?", utilisateur, id);
  return l && versAgent(l);
}

export async function creer(b: Base, utilisateur: string, corps: unknown, maintenant = new Date()): Promise<Agent> {
  const v = valider(corps);
  const id = "ag_" + randomUUID().replace(/-/g, "").slice(0, 20);
  await b.ecrire("INSERT INTO agent (id, utilisateur, prenom, metier, couleur, yeux, epingle, cree_le) VALUES (?, ?, ?, ?, ?, ?, 0, ?)",
    id, utilisateur, v.prenom, v.metier, v.couleur, v.yeux, maintenant.toISOString());
  return (await trouver(b, utilisateur, id))!;
}

export async function retirer(b: Base, utilisateur: string, id: string): Promise<void> {
  await b.ecrire("DELETE FROM agent WHERE utilisateur = ? AND id = ?", utilisateur, id);
}

/** Trois épinglés au plus : le compte et l'écriture dans une même transaction. */
export function epingler(b: Base, utilisateur: string, id: string, oui: boolean): Promise<Agent> {
  return b.transaction(async (tx) => {
    const a = await trouver(tx, utilisateur, id);
    if (!a) throw new Refus(404, T.agentIntrouvable);
    if (oui && !a.epingle) {
      const { n } = (await tx.un<{ n: number }>("SELECT COUNT(*) AS n FROM agent WHERE utilisateur = ? AND epingle = 1", utilisateur))!;
      if (n >= EPINGLES_MAX) throw new Refus(409, T.troisEpingles);
    }
    await tx.ecrire("UPDATE agent SET epingle = ? WHERE utilisateur = ? AND id = ?", oui ? 1 : 0, utilisateur, id);
    return (await trouver(tx, utilisateur, id))!;
  });
}
