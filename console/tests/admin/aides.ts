// Les aides des essais de l'admin : un accès de membre fabriqué, et la capture d'un refus.
import { droitsEffectifs, type Acces, type Perimetre } from "@/lib/admin/acces";
import { SUPERADMIN, type Droit } from "@/lib/admin/droits";
import { Refus } from "@/lib/agents";

/** Un accès de membre, sans base : les droits passent par droitsEffectifs (plafond d'un externe compris). */
export function acces(p: { utilisateur?: string; role?: string; droits?: readonly Droit[]; externe?: boolean; superadmin?: boolean; perimetre?: Perimetre } = {}): Acces {
  const utilisateur = p.utilisateur ?? "u";
  const superadmin = p.superadmin ?? false;
  const externe = p.externe ?? false;
  const role = superadmin ? SUPERADMIN : (p.role ?? "essai");
  return {
    utilisateur,
    courriel: `${utilisateur}@megga.test`,
    nom: utilisateur,
    role: { id: role, nom: role },
    superadmin,
    externe,
    perimetre: superadmin ? "tous" : (p.perimetre ?? "tous"),
    finAcces: null,
    droits: droitsEffectifs(p.droits ?? [], externe, superadmin),
  };
}

export function refus(f: () => unknown): Refus {
  try {
    f();
  } catch (e) {
    if (e instanceof Refus) return e;
    throw e;
  }
  throw new Error("aucun refus");
}

export async function refusAsync(f: () => Promise<unknown>): Promise<Refus> {
  try {
    await f();
  } catch (e) {
    if (e instanceof Refus) return e;
    throw e;
  }
  throw new Error("aucun refus");
}
