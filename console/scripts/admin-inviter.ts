// Les premiers superadmins : npm run admin:inviter -- <courriel>, lancé sur le serveur de la console.
// Imprime un lien d'invitation superadmin (valable 7 jours, une fois), à envoyer soi-même, et note le geste au journal.
// Pas de liste de courriels dans l'environnement : l'inscription est ouverte et les courriels ne sont pas vérifiés.
import { inviterSuperadmin, lireInvitation } from "@/lib/admin/invitations";
import { noter } from "@/lib/admin/journal";
import { TA } from "@/lib/admin/textes";
import { Refus } from "@/lib/agents";
import { base, pret } from "@/lib/base";

const courriel = process.argv[2];
if (!courriel) {
  console.error(TA.usageCommande);
  process.exit(1);
}

try {
  await pret();
  const db = base();
  const lien = inviterSuperadmin(db, courriel, process.env.BETTER_AUTH_URL || "http://localhost:3000");
  const invitation = lireInvitation(db, lien.slice(lien.lastIndexOf("/") + 1))!;
  noter(db, { qui: null, courriel: null, action: "invitations.commande", cible: `invitation:${invitation.id}`, resultat: "ok",
    detail: { courriel: invitation.courriel } });
  console.log(lien);
} catch (e) {
  if (!(e instanceof Refus)) throw e;
  console.error(e.message);
  process.exit(1);
}
