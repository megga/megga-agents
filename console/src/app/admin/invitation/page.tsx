import { Reprise } from "./reprise";

// /admin/invitation, sans jeton : le retour de la connexion (retourSur). Le jeton n'est jamais dans l'adresse de retour ;
// la page du lien l'a rangé dans cet onglet, Reprise l'y relit. Rien n'est lu côté serveur ici.
export default function PageReprise() {
  return <Reprise />;
}
