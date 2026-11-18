// Les premiers superadmins : npm run admin:inviter -- <courriel>, lancé sur le serveur de la console.
// Imprime un lien d'invitation superadmin (valable 7 jours, une fois), à envoyer soi-même.
// Pas de liste de courriels dans l'environnement : l'inscription est ouverte et les courriels ne sont pas vérifiés.
import { inviterSuperadmin } from "@/lib/admin/invitations";
import { TA } from "@/lib/admin/textes";
import { Refus } from "@/lib/agents";
import { base } from "@/lib/base";

const courriel = process.argv[2];
if (!courriel) {
  console.error(TA.usageCommande);
  process.exit(1);
}

try {
  console.log(inviterSuperadmin(base(), courriel, process.env.BETTER_AUTH_URL || "http://localhost:3000"));
} catch (e) {
  if (!(e instanceof Refus)) throw e;
  console.error(e.message);
  process.exit(1);
}
