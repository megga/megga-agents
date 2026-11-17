// Les huit métiers du lot 10 de Thomas (atelier/gabarits/, branche megga/lot-10-modeles, PR 53).
// L'identifiant est celui du gabarit ; le nom et la ligne d'aide sont ceux de la maquette validée.
// Une fois le lot 10 fusionné, la console les lira à GET /atelier/gabarits (test : metiers.test.ts).

export type Metier = { id: string; nom: string; sous: string; qui: string };

export const METIERS: readonly Metier[] = [
  { id: "generaliste", nom: "Généraliste", sous: "Pour tout type d'entreprise", qui: "à l'accueil de votre entreprise" },
  { id: "immobilier", nom: "Immobilier", sous: "Achat, vente et location", qui: "à l'accueil de votre agence" },
  { id: "sante", nom: "Santé", sous: "L'accueil d'un cabinet", qui: "à l'accueil de votre cabinet" },
  { id: "hotellerie", nom: "Hôtellerie et restauration", sous: "Hôtels et restaurants", qui: "à l'accueil de votre établissement" },
  { id: "juridique", nom: "Juridique", sous: "Le premier contact d'une étude", qui: "au premier contact de votre étude" },
  { id: "commerce", nom: "Commerce", sous: "Retours et service après-vente", qui: "au service après-vente de votre boutique" },
  { id: "fiduciaire", nom: "Fiduciaire", sous: "Pièces, échéances et demandes", qui: "à l'accueil de votre fiduciaire" },
  { id: "garage", nom: "Garage", sous: "La prise en charge des véhicules", qui: "à l'accueil de votre garage" },
];

export const IDS_METIERS = METIERS.map((m) => m.id);

export function metier(id: string): Metier | undefined {
  return METIERS.find((m) => m.id === id);
}
