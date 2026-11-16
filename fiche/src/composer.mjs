// Le service de fiche PDF de l'image : l'agent (packs/immobilier/fiche.py) l'appelle comme un processus.
// Il lit sur l'entrée une demande JSON et écrit le PDF sur la sortie ; une erreur sur la sortie d'erreur.
//
//   { "modele": "four-seasons-properties", "fiche": {…}, "photos": ["<base64>", …],
//     "version": "marque" | "anonyme", "sans_prix": false, "serif": "instrument", "marque": "Nom de l'agence" }
//
// Rien ne sort du conteneur : ni réseau, ni fichier. Le modèle choisit les polices et le logo
// (modeles/<modèle>/ressources.js), la mise en page est la même pour tous.
import { composerFiche } from "./pdf.js";

const MODELE = /^[a-z0-9][a-z0-9-]{0,62}$/;

async function lireEntree() {
  const morceaux = [];
  for await (const m of process.stdin) morceaux.push(m);
  return JSON.parse(Buffer.concat(morceaux).toString("utf8"));
}

try {
  const d = await lireEntree();
  if (!MODELE.test(String(d.modele ?? ""))) throw new Error("modèle de fiche");
  const ressources = await import(new URL(`../modeles/${d.modele}/ressources.js`, import.meta.url));
  const photos = (d.photos ?? []).map((b) => new Uint8Array(Buffer.from(String(b), "base64")));
  const octets = await composerFiche(d.fiche, photos, {
    version: d.version === "anonyme" ? "anonyme" : "marque",
    sansPrix: Boolean(d.sans_prix),
    serif: d.serif === "gambetta" ? "gambetta" : "instrument",
    ressources,
    marque: String(d.marque ?? ""),
  });
  process.stdout.write(Buffer.from(octets));
} catch (e) {
  process.stderr.write(String(e?.message ?? e).slice(0, 500));
  process.exitCode = 1;
}
