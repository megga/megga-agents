// Tous les textes visibles de l'admin, au même endroit pour que Julien les relise avant qu'ils ne soient figés.
// Ceux que la conception fixe sont repris tels quels ; les autres sont des propositions.
// Règles de textes.ts : français, courts, ni point médian, ni tiret long ou demi-cadratin,
// espace insécable avant « ? : ! ; » et après « « » (test : textes.test.ts).

export const TA = {
  // L'entrée dans l'admin (menu du compte) et la sortie
  administration: "Administration",
  retourConsole: "Retour à la console",

  // Le rail
  vueEnsemble: "Vue d'ensemble",
  clients: "Clients",
  alertes: "Alertes",
  installations: "Installations",
  comptes: "Comptes",
  tarifs: "Tarifs",
  equipe: "Équipe",
  journal: "Journal",

  // La coquille
  railAdmin: "L'admin MEGGA",

  // La page d'une invitation
  invitationTitre: "Rejoindre l'admin",
  invitationPour: (courriel: string) => `Une invitation pour ${courriel}.`,
  rejoindre: "Rejoindre",
  votreNom: "Votre nom",
  courriel: "Courriel",
  motDePasse: "Mot de passe",
  creerEtRejoindre: "Créer mon compte et rejoindre",
  dejaUnCompte: "Déjà un compte ?",
  seConnecter: "Se connecter",
  seDeconnecter: "Se déconnecter",
  motDePasseCourt: "Le mot de passe fait 8 caractères au moins.",
  courrielDejaInscrit: "Ce courriel a déjà un compte : connectez-vous.",

  // Les pièces communes
  annuler: "Annuler",
  fermer: "Fermer",
  copier: "Copier",
  copie: "Copié",
  secretTitre: "À copier maintenant",
  secretUneFois: "Il ne sera plus jamais montré. Copiez-le avant de fermer.",

  // Les onglets d'un client
  suivi: "Suivi",
  conversations: "Conversations",
  versions: "Versions",
  acces: "Accès",
  installation: "Installation",

  // Les onglets de l'équipe
  membres: "Membres",
  invitations: "Invitations",
  roles: "Rôles",

  // Les périodes
  periode24h: "24 heures",
  periode7j: "7 jours",
  periode30j: "30 jours",

  // Les tuiles et les blocs de la vue d'ensemble
  clientsEnService: "Clients en service",
  soucisEnCours: "Soucis en cours",
  tours: "Tours",
  personnes: "Personnes",
  cout: "Coût",
  agents: "Agents",
  messages: "Messages",
  aSurveiller: "À surveiller",
  activiteParClient: "Activité par client",
  console: "Console",

  // Les gestes
  nouveauClient: "Nouveau client",
  valider: "Valider",
  mettreEnService: "Mettre en service",

  // Les groupes de droits
  groupeClients: "Clients",
  groupeVersions: "Versions et pilotage",
  groupeCouts: "Coûts",
  groupeComptes: "Comptes",
  groupeEquipe: "Équipe",

  // Les rôles fixes et de départ
  roleSuperadmin: "Superadmin",
  roleSuperadminDescription: "Tous les droits, sur tous les clients. Ne se modifie pas.",
  roleAdministration: "Administration",
  roleAdministrationDescription: "Tous les droits.",
  roleExploitation: "Exploitation",
  roleExploitationDescription: "Suivre et piloter les clients, leurs accès et leurs installations, et les comptes de la console.",
  roleFinance: "Finance",
  roleFinanceDescription: "Les clients, les coûts et les tarifs, et les comptes de la console.",
  roleLecture: "Lecture",
  roleLectureDescription: "Les clients et les comptes de la console, en lecture.",

  // Les refus
  connectezVous: "Connectez-vous.",
  introuvable: "Introuvable.",
  sansDroit: "Votre rôle ne permet pas ce geste.",
  origineRefusee: "Requête refusée : elle ne vient pas de la console.",
  escalade: "Ce geste dépasse vos propres droits.",
  roleFixe: "Le rôle Superadmin ne se modifie pas.",
  rolePorte: "Ce rôle est encore porté par un membre.",
  nomPris: "Ce nom est déjà pris.",
  nomManquant: "Donnez un nom au rôle.",
  droitInconnu: "Droit inconnu.",
  roleInconnu: "Rôle inconnu.",
  membreInconnu: "Membre inconnu.",
  dernierSuperadmin: "Il faut garder au moins un superadmin.",
  externePerimetre: "Un externe suit au moins un client, nommé un par un.",
  externeSuperadmin: "Un externe ne peut pas être superadmin.",
  perimetreInvalide: "Périmètre invalide : tous les clients, ou une liste d'identifiants de clients.",
  finAccesInvalide: "Fin d'accès invalide : une date au format AAAA-MM-JJ.",
  courrielInvalide: "Courriel invalide.",
  invitationInvalide: "Cette invitation n'est plus valable.",
  autreCourriel: "Cette invitation est pour un autre courriel. Connectez-vous avec celui qui a été invité.",
  dejaMembre: "Ce compte est déjà membre de l'admin.",
  usageCommande: "Usage : npm run admin:inviter -- <courriel>",
  erreurInterne: "Un souci est survenu. Réessayez.",
} as const;
