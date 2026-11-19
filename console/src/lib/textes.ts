// Tous les textes visibles de la console, au même endroit pour que Julien les relise avant qu'ils ne soient figés.
// Repris de la maquette quand elle les donne ; les autres sont marqués « nouveau ».
// Règles : français, courts, ni point médian, ni tiret long ou demi-cadratin (test : textes.test.ts).

export const T = {
  // Connexion (nouveau)
  connexionTitre: "Connexion",
  inscriptionTitre: "Créer un compte",
  entreprise: "Nom de votre entreprise",
  courriel: "Courriel",
  motDePasse: "Mot de passe",
  seConnecter: "Se connecter",
  creerCompte: "Créer mon compte",
  avecGoogle: "Continuer avec Google",
  avecMicrosoft: "Continuer avec Microsoft",
  ou: "ou",
  pasDeCompte: "Pas encore de compte ?",
  dejaUnCompte: "Déjà un compte ?",
  erreurIdentifiants: "Courriel ou mot de passe incorrect.",
  erreurDejaInscrit: "Ce courriel a déjà un compte.",
  erreurMotDePasse: "Le mot de passe fait 8 caractères au moins.",
  erreurGenerale: "Un souci est survenu. Réessayez.",
  inscriptionSurInvitation: "Un compte se crée depuis un lien d'invitation.", // nouveau
  compteSuspendu: "Ce compte est suspendu : il ne peut plus se connecter. Contactez MEGGA pour en savoir plus.", // nouveau
  pageIntrouvable: "Page introuvable", // nouveau
  retourAccueil: "Retour à l'accueil", // nouveau

  // Rail (maquette)
  chercherAgent: "Chercher un agent",
  nouvelAgent: "Nouvel agent",
  epingles: "Épinglés",
  conversations: "Conversations",
  videEpingles: "Clic droit sur un agent, puis « Épingler en haut ».",
  epinglerEnHaut: "Épingler en haut",
  desepingler: "Désépingler",
  compteEtReglages: "Compte et réglages",
  seDeconnecter: "Se déconnecter",
  chercherPlaceholder: "Chercher un agent ou un groupe",
  aucunResultat: "Aucun agent trouvé", // nouveau

  // Thème, dans le menu du compte (nouveau, d'après les réglages d'aperçu de la maquette)
  theme: "Thème",
  themeClair: "Clair",
  themeSombre: "Sombre",
  themeAppareil: "Comme l'appareil",

  // Fil et saisie (maquette)
  aujourdhui: "Aujourd'hui",
  envoyer: "Envoyer",
  ecrireA: (prenom: string) => `Écrivez à ${prenom}`,
  accueil: (prenom: string) =>
    `Bonjour, je suis ${prenom}. Essayez-moi : écrivez-moi comme le ferait un de vos clients, et dites-moi ce que je dois changer.`,
  apercuAccueil: (prenom: string, qui: string) => `Bonjour, je suis ${prenom}, ${qui}.`,
  sansReponse: "Pas de réponse pour l'instant. Réessayez dans un instant.", // nouveau

  // Sans agent : la mascotte et ce bouton (nouveau)
  creerUnAgent: "Créer un agent",

  // Studio (maquette)
  sonPrenom: "Son prénom",
  prenomAgent: "Prénom de l'agent",
  choisirMetier: "Choisir un métier",
  creer: "Créer",
  fermer: "Fermer",
  couleur: "Couleur",
  yeux: "Yeux",
  metier: "Métier",
  reglages: "Réglages",
  apercuAgent: "Aperçu de l'agent",

  // Bulles (maquette, sauf « n'est plus épinglé »)
  estEpingle: (prenom: string) => `${prenom} est épinglé en haut`,
  plusEpingle: (prenom: string) => `${prenom} n'est plus épinglé`, // nouveau
  troisEpingles: "3 agents épinglés au maximum. Désépinglez-en un d'abord.",

  // Erreurs renvoyées par la console (nouveau)
  prenomManquant: "Donnez-lui un prénom.",
  prenomTropLong: (n: number) => `Le prénom fait ${n} caractères au plus.`,
  metierManquant: "Choisissez un métier.",
  agentIntrouvable: "Agent introuvable.",
  connectezVous: "Connectez-vous.",
  serviceIndisponible: "Le service ne répond pas. Réessayez dans un instant.",
  agentsNonBranches: "L'équipe d'agents n'est pas encore branchée.",
} as const;
