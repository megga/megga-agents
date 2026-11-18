// Les comptes d'essai des tests de bout en bout et des captures : seulement en local, sur une base jetable.
export const COMPTE_ESSAI = {
  entreprise: "Agence Soleil",
  courriel: "essai@megga.test",
  motDePasse: "essai-console-2026",
};

// L'admin : le premier superadmin (invité par npm run admin:inviter), un invité externe, un compte de la console sans admin.
export const SUPERADMIN_ESSAI = { nom: "Chef Essai", courriel: "chef@megga.test", motDePasse: "essai-admin-2026" };
export const EXTERNE_ESSAI = { nom: "Partenaire Essai", courriel: "externe@partenaire.test", motDePasse: "essai-externe-2026" };
export const ORDINAIRE_ESSAI = { entreprise: "Atelier Ordinaire", courriel: "ordinaire@megga.test", motDePasse: "essai-ordinaire-2026" };
