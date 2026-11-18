import { TA } from "./textes";

// Les treize droits de l'admin, fixés dans le code : un rôle ne peut cocher que ceux-là (conception, « Les droits »).

export const DROITS = [
  "clients.voir",
  "couts.voir",
  "conversations.lire",
  "clients.creer",
  "versions.preparer",
  "clients.piloter",
  "acces.gerer",
  "installations.gerer",
  "tarifs.regler",
  "comptes.voir",
  "comptes.gerer",
  "equipe.gerer",
  "journal.voir",
] as const;

export type Droit = (typeof DROITS)[number];

const CONNUS: ReadonlySet<string> = new Set(DROITS);

export function estDroit(x: unknown): x is Droit {
  return typeof x === "string" && CONNUS.has(x);
}

/** Les droits cochés par groupe, à l'écran des rôles ; chaque droit est dans un seul groupe. */
export const GROUPES_DE_DROITS: readonly { titre: string; droits: readonly Droit[] }[] = [
  { titre: TA.groupeClients, droits: ["clients.voir", "clients.creer", "conversations.lire"] },
  { titre: TA.groupeVersions, droits: ["versions.preparer", "clients.piloter", "acces.gerer", "installations.gerer"] },
  { titre: TA.groupeCouts, droits: ["couts.voir", "tarifs.regler"] },
  { titre: TA.groupeComptes, droits: ["comptes.voir", "comptes.gerer"] },
  { titre: TA.groupeEquipe, droits: ["equipe.gerer", "journal.voir"] },
];

/** Ce qu'un externe garde, quels que soient les droits de son rôle (décision 5 de Thomas). */
export const DROITS_EXTERNE: readonly Droit[] = ["clients.voir", "conversations.lire", "versions.preparer"];

/** Le rôle fixe : tous les droits, aucun périmètre, ni modifiable ni retirable. */
export const SUPERADMIN = "superadmin";

/** Les quatre rôles de départ, modifiables à l'écran. */
export const ROLES_DE_DEPART: readonly { id: string; nom: string; description: string; droits: readonly Droit[] }[] = [
  { id: "administration", nom: TA.roleAdministration, description: TA.roleAdministrationDescription, droits: DROITS },
  {
    id: "exploitation",
    nom: TA.roleExploitation,
    description: TA.roleExploitationDescription,
    droits: ["clients.voir", "conversations.lire", "versions.preparer", "clients.piloter", "acces.gerer", "installations.gerer",
      "clients.creer", "comptes.voir", "comptes.gerer"],
  },
  { id: "finance", nom: TA.roleFinance, description: TA.roleFinanceDescription, droits: ["clients.voir", "couts.voir", "tarifs.regler", "comptes.voir"] },
  { id: "lecture", nom: TA.roleLecture, description: TA.roleLectureDescription, droits: ["clients.voir", "comptes.voir"] },
];
