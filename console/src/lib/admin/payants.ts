import { voitClient, type Acces } from "./acces";
import type { LignePayant, StatutAbonnement, TotauxPayants, VuePayants } from "./atelier";
import { TA } from "./textes";

// Les clients payants, bornés au périmètre du membre (20.11.2026) : l'atelier les rend tous, la console retire ceux que le
// membre ne voit pas et refait les totaux sur ceux qui restent. Fonctions pures.

const STATUTS: readonly StatutAbonnement[] = ["essai", "actif", "retard", "parti"];
const arrondi = (n: number) => Math.round(n * 100) / 100;

export function totauxDe(lignes: readonly LignePayant[], margeConnue: boolean): TotauxPayants {
  const compte = Object.fromEntries(STATUTS.map((s) => [s, lignes.filter((l) => l.abonnement.statut === s).length])) as Record<StatutAbonnement, number>;
  const revenu = arrondi(lignes.reduce((n, l) => n + l.revenu, 0));
  // Le coût de tous les abonnés, essais compris, comme l'atelier : un essai coûte sans rapporter.
  const cout = arrondi(lignes.reduce((n, l) => n + l.cout, 0));
  return { ...compte, revenu, cout, marge: margeConnue ? arrondi(revenu - cout) : null, proches: lignes.filter((l) => l.proche).length };
}

/** La vue du membre : ses clients seulement, les plus proches de l'enveloppe vide d'abord, puis par revenu. */
export function bornerPayants(a: Acces, v: VuePayants): VuePayants {
  const clients = v.clients
    .filter((l) => voitClient(a, l.client))
    .sort((x, y) => Number(y.proche) - Number(x.proche) || y.revenu - x.revenu || x.client.localeCompare(y.client));
  return { ...v, clients, totaux: totauxDe(clients, v.devise === v.devise_couts) };
}

/** La part consommée de l'enveloppe, en % arrondi ; null sans enveloppe. */
export const partConsommee = (l: LignePayant) => (l.enveloppe > 0 ? Math.round((l.consommees / l.enveloppe) * 100) : null);

export const ONGLETS_PAYANTS = [
  { href: "/admin/payants", texte: TA.clientsPayants },
  { href: "/admin/payants/forfaits", texte: TA.forfaits },
];
