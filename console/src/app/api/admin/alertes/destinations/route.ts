import { Refus } from "@/lib/agents";
import { peutReglerAlertes } from "@/lib/admin/acces";
import { atelier } from "@/lib/admin/atelier";
import { estObjet } from "@/lib/admin/champs";
import { garde } from "@/lib/admin/garde";
import { TA } from "@/lib/admin/textes";

// Ajouter une destination d'alerte : {id, genre, adresse}, validée par l'atelier. L'adresse d'un webhook est un secret :
// le journal ne garde que l'identifiant et le genre. La clé de signature d'une adresse web revient une fois, ici.

const ID = /^[a-z0-9][a-z0-9-]{1,39}$/;
const GENRES = ["courriel", "slack", "web"];

const resume = (corps: unknown) =>
  estObjet(corps)
    ? { id: typeof corps.id === "string" && ID.test(corps.id) ? corps.id : null, genre: GENRES.includes(String(corps.genre)) ? corps.genre : null }
    : null;

export const POST = garde({ droit: "alertes.regler", action: "alertes.destination_ajoutee", detail: resume }, async ({ acces, corps }) => {
  if (!peutReglerAlertes(acces)) throw new Refus(403, TA.sansDroit);
  if (!estObjet(corps)) throw new Refus(400, TA.destinationInvalide);
  return atelier.ajouterDestination({ id: corps.id, genre: corps.genre, adresse: corps.adresse });
});
