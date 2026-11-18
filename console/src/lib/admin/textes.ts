// Tous les textes visibles de l'admin, au même endroit pour que Julien les relise avant qu'ils ne soient figés.
// Ceux que la conception fixe sont repris tels quels ; les autres sont des propositions.
// Règles de textes.ts : français, courts, ni point médian, ni tiret long ou demi-cadratin,
// espace insécable avant « ? : ! ; » et après « « » (test : textes.test.ts).
import type { Droit } from "./droits";

const INSTANT = new Intl.DateTimeFormat("fr-CH", {
  timeZone: "Europe/Zurich",
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

/** Un jour AAAA-MM-JJ s'écrit JJ.MM.AAAA, sans fuseau ; autre chose reste tel quel. */
function jour(v: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(v);
  return m ? `${m[3]}.${m[2]}.${m[1]}` : v;
}

/** Un instant ISO s'écrit JJ.MM.AAAA HH:MM, à l'heure de Zurich ; autre chose reste tel quel. */
function instant(v: string): string {
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? v : INSTANT.format(d);
}

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

  // Les dates
  jour,
  instant,

  // L'équipe
  membre: "Membre",
  role: "Rôle",
  statut: "Statut",
  interne: "Interne",
  externe: "Externe",
  perimetre: "Périmètre",
  tousLesClients: "Tous les clients",
  uneListe: "Une liste de clients",
  aucunClient: "Aucun client",
  nClients: (n: number) => (n === 1 ? "1 client" : `${n} clients`),
  etAutres: (n: number) => (n === 1 ? "et 1 autre" : `et ${n} autres`),
  perimetreAide: "Les identifiants des clients, séparés par des virgules.",
  finAcces: "Fin d'accès",
  sansFin: "Sans fin",
  finAccesAide: "Vide : un accès sans fin.",
  derniereConnexion: "Dernière connexion",
  pasEncoreNotee: "Pas encore notée",
  modifier: "Modifier",
  enregistrer: "Enregistrer",
  retirer: "Retirer",
  creer: "Créer",
  videMembres: "Aucun membre.",
  titreModifier: (nom: string) => `Modifier ${nom}`,
  retirerMembreTitre: "Retirer ce membre ?",
  retirerMembreEffet: (nom: string) => `${nom} perd l'accès à l'admin dès sa prochaine requête. Son compte de la console reste.`,
  externeCase: "Externe, limité à des clients nommés",
  externeGarde: "Un externe ne garde que ces droits, quel que soit son rôle :",
  nouvelleInvitation: "Nouvelle invitation",
  inviter: "Inviter",
  enAttente: "En attente",
  valableJusqua: "Valable jusqu'au",
  videInvitations: "Aucune invitation en attente.",
  retirerInvitationTitre: "Retirer cette invitation ?",
  retirerInvitationEffet: (courriel: string) => `Le lien envoyé à ${courriel} ne vaudra plus rien.`,
  nouveauRole: "Nouveau rôle",
  nomDuRole: "Nom du rôle",
  description: "Description",
  droits: "Droits",
  aucunDroit: "Aucun droit",
  nombreMembres: (n: number) => (n === 1 ? "1 membre" : `${n} membres`),
  roleFixeMarque: "Fixe",
  retirerRoleTitre: "Retirer ce rôle ?",
  retirerRoleEffet: (nom: string) => `Le rôle ${nom} disparaît. Aucun membre ne le porte, aucune invitation ne le nomme.`,
  nomsDroits: {
    "clients.voir": "Voir les clients",
    "couts.voir": "Voir les coûts et les tarifs",
    "conversations.lire": "Lire les conversations",
    "clients.creer": "Créer un client",
    "versions.preparer": "Préparer une version",
    "clients.piloter": "Mettre en service, reprendre la main",
    "acces.gerer": "Les jetons et les clés d'un client",
    "installations.gerer": "Piloter une installation",
    "tarifs.regler": "Changer les tarifs",
    "comptes.voir": "Voir les comptes de la console",
    "comptes.gerer": "Suspendre un compte",
    "equipe.gerer": "Gérer l'équipe",
    "journal.voir": "Lire le journal",
  } satisfies Record<Droit, string>,

  // Le journal
  quand: "Quand",
  qui: "Qui",
  quoi: "Quoi",
  surQuoi: "Sur quoi",
  resultat: "Résultat",
  detail: "Détail",
  reussi: "Réussi",
  refuse: (statut: string) => `Refusé (${statut})`,
  erreur: "Erreur",
  leServeur: "Le serveur",
  videJournal: "Aucun geste noté.",
  depuis: "Depuis le",
  jusqua: "Jusqu'au",
  filtrer: "Filtrer",
  effacerFiltres: "Effacer les filtres",
  filtrerSur: "Ne montrer que ces gestes",
  filtreMembre: "Membre",
  filtreAction: "Action",
  filtreClient: "Client",
  filtreSur: (quoi: string, valeur: string) => `${quoi} : ${valeur}`,
  pageSur: (page: number, pages: number) => `Page ${page} sur ${pages}`,
  pagePrecedente: "Page précédente",
  pageSuivante: "Page suivante",
  actionsJournal: {
    "membres.modifier": "Modifier un membre",
    "membres.retirer": "Retirer un membre",
    "invitations.creer": "Inviter",
    "invitations.retirer": "Retirer une invitation",
    "invitations.accepter": "Rejoindre par une invitation",
    "invitations.commande": "Inviter un superadmin, par la commande",
    "roles.creer": "Créer un rôle",
    "roles.modifier": "Modifier un rôle",
    "roles.retirer": "Retirer un rôle",
  } as Record<string, string>,

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

  // Les alertes du moteur, dites en clair (suivi.ts, GENRES_CONNUS)
  genres: {
    ecart: "Écart de version",
    porte_injoignable: "Porte injoignable",
    conteneur_injoignable: "Conteneur injoignable",
    installation_silencieuse: "Installation silencieuse",
    installation_revoquee: "Installation révoquée",
    installation_absente: "Aucune installation enregistrée",
    agent_en_panne: "Agent en panne",
    licence_expiree: "Licence expirée",
    licence_hors_delai: "Licence hors délai",
    tour_echec: "Tour en échec",
    envoi_echec: "Envoi en échec",
    vocal_illisible: "Vocal illisible",
    voix_echec: "Voix en échec",
    rappel_echec: "Rappel en échec",
    mise_a_jour_bloquee: "Mise à jour bloquée",
    envoi_refuse: "Envoi refusé par Meta",
    message_ancien: "Message reçu trop tard",
    plafond: "Plafond du jour atteint",
    conteneur_demarrage: "Panne au démarrage du conteneur",
    conteneur_transmission: "Panne de transmission au conteneur",
    conteneur_rappels: "Panne des rappels du conteneur",
    ordre_refuse: "Ordre refusé par l'installation",
    ordre_echec: "Ordre en échec",
    ordre_expire: "Ordre expiré",
  } as Record<string, string>,
  genreInconnu: (genre: string) => `Autre alerte (${genre})`,

  // L'atelier (le moteur)
  moteurNonBranche: "Le moteur n'est pas branché à cette console.",
  atelierInjoignable: "L'atelier ne répond pas. Réessayez dans un instant.",
  atelierLent: "L'atelier n'a pas répondu à temps. Réessayez.",
  atelierRefus: "L'atelier a refusé cette demande.",
} as const;
