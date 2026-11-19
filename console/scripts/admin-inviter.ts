// Les premiers superadmins : npm run admin:inviter -- <courriel>, lancé sur le serveur de la console.
// Imprime un lien d'invitation superadmin (valable 7 jours, une fois), à envoyer soi-même, et note le geste au journal.
// Pas de liste de courriels dans l'environnement : en ligne, un compte ne se crée qu'avec ce lien.
import { inviterSuperadmin, lireInvitation } from "@/lib/admin/invitations";
import { noter } from "@/lib/admin/journal";
import { TA } from "@/lib/admin/textes";
import { Refus } from "@/lib/agents";
import { pret } from "@/lib/base";

const courriel = process.argv[2];
if (!courriel) {
  console.error(TA.usageCommande);
  process.exit(1);
}

// La base de la console : Postgres si CONSOLE_BASE_URL est posée, sinon le fichier SQLite (pret, src/lib/base.ts).
const b = await pret();
try {
  const lien = await inviterSuperadmin(b, courriel, process.env.BETTER_AUTH_URL || "http://localhost:3000");
  const invitation = (await lireInvitation(b, lien.slice(lien.lastIndexOf("/") + 1)))!;
  await noter(b, { qui: null, courriel: null, action: "invitations.commande", cible: `invitation:${invitation.id}`, resultat: "ok",
    detail: { courriel: invitation.courriel } });
  console.log(lien);
} catch (e) {
  if (!(e instanceof Refus)) throw e;
  console.error(e.message);
  process.exitCode = 1;
} finally {
  await b.fermer(); // les connexions de Postgres ne retiennent pas la commande
}
