// Un message champ par champ, tel que l'atelier le donne dans un refus ({ champ, message }). Un module neutre, ni serveur ni
// navigateur : le client de l'atelier (atelier.ts) et l'envoi des gestes (components/admin/envoyer.ts) le partagent.

export type ChampErreur = { champ: string; message: string };

export const estChamp = (d: unknown): d is ChampErreur =>
  !!d && typeof d === "object" && typeof (d as ChampErreur).champ === "string" && typeof (d as ChampErreur).message === "string";
