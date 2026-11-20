import { filtrerClients, peut, type Acces } from "./acces";
import type { Releves } from "./releves";

// L'écran Analyses (21.11.2026), d'après le relevé chiffré : jour par jour, par modèle, par client ; une conversation est une
// personne servie sur une journée (l'unité des forfaits). Fonction pure : le périmètre filtre les clients avant tout calcul,
// et les coûts disparaissent sans couts.voir. Jamais une conversation lue : seulement des chiffres.

export type JourAnalyse = { jour: string; tours: number; conversations: number; cout: number; vocaux: number };
export type ModeleAnalyse = { modele: string; tours: number; entree: number; sortie: number; cacheLecture: number; cout?: number | null };
export type ClientAnalyse = { client: string; entreprise: string | null; tours: number; conversations: number; cout?: number;
  coutParConversation?: number | null };
export type VueAnalyses = {
  tuiles: { conversations: number; tours: number; toursApi: number; vocauxEntendus: number; vocauxDits: number;
    cout?: { devise: string; total: number; parConversation: number | null } };
  parJour: JourAnalyse[];
  modeles: ModeleAnalyse[];
  /** La voix et l'écoute : leur coût sur la période, avec couts.voir. */
  autresPostes: { poste: string; cout: number }[];
  clients: ClientAnalyse[];
};

const arrondi = (n: number, d = 4) => Math.round(n * 10 ** d) / 10 ** d;
const parConversation = (cout: number, n: number) => (n > 0 ? arrondi(cout / n, 2) : null);

export function analyser(r: Releves, a: Acces): VueAnalyses {
  const voitCouts = peut(a, "couts.voir");
  const clients = filtrerClients(a, r.clients).filter((c) => c.actif);
  const jours = new Map<string, JourAnalyse>();
  const modeles = new Map<string, ModeleAnalyse & { cout: number }>();
  const tarifes = new Set<string>(); // les modèles dont un coût a été compté : un modèle sans tarif n'a pas un coût nul, il est inconnu
  const postes = new Map<string, number>();
  let toursApi = 0, vocauxEntendus = 0, vocauxDits = 0;
  const lignes: ClientAnalyse[] = clients.map((c) => {
    let conversations = 0;
    for (const [jour, j] of Object.entries(c.jours)) {
      conversations += j.personnes;
      toursApi += j.tours_api ?? 0;
      vocauxEntendus += j.journal?.vocal_entendu?.nombre ?? 0;
      vocauxDits += j.journal?.voix_caracteres?.nombre ?? 0; // un par vocal dit (noyau/autour.py)
      const t = jours.get(jour) ?? { jour, tours: 0, conversations: 0, cout: 0, vocaux: 0 };
      t.tours += j.tours;
      t.conversations += j.personnes;
      t.cout += j.cout ?? 0;
      t.vocaux += (j.journal?.vocal_entendu?.nombre ?? 0) + (j.journal?.voix_caracteres?.nombre ?? 0);
      jours.set(jour, t);
      for (const [nom, m] of Object.entries(j.modeles ?? {})) {
        const e = modeles.get(nom) ?? { modele: nom, tours: 0, entree: 0, sortie: 0, cacheLecture: 0, cout: 0 };
        e.tours += m.tours ?? 0;
        e.entree += m.entree ?? 0;
        e.sortie += m.sortie ?? 0;
        e.cacheLecture += m.cache_lecture ?? 0;
        modeles.set(nom, e);
      }
      for (const [poste, cout] of Object.entries(j.postes ?? {})) {
        postes.set(poste, (postes.get(poste) ?? 0) + cout);
        const e = modeles.get(poste);
        if (e) {
          e.cout += cout;
          tarifes.add(poste);
        }
      }
    }
    const ligne: ClientAnalyse = { client: c.id, entreprise: c.entreprise, tours: c.totaux.tours, conversations };
    if (voitCouts) Object.assign(ligne, { cout: c.totaux.cout, coutParConversation: parConversation(c.totaux.cout, conversations) });
    return ligne;
  });
  const conversations = lignes.reduce((n, l) => n + l.conversations, 0);
  const total = arrondi(clients.reduce((n, c) => n + c.totaux.cout, 0));
  const tuiles: VueAnalyses["tuiles"] = { conversations, tours: lignes.reduce((n, l) => n + l.tours, 0), toursApi, vocauxEntendus, vocauxDits };
  if (voitCouts) tuiles.cout = { devise: r.devise, total, parConversation: parConversation(total, conversations) };
  return {
    tuiles,
    parJour: [...jours.values()].sort((x, y) => x.jour.localeCompare(y.jour)).map((j) => ({ ...j, cout: voitCouts ? arrondi(j.cout) : 0 })),
    modeles: [...modeles.values()]
      .sort((x, y) => y.tours - x.tours || x.modele.localeCompare(y.modele))
      .map(({ cout, ...m }) => (voitCouts ? { ...m, cout: tarifes.has(m.modele) ? arrondi(cout) : null } : m)),
    autresPostes: voitCouts ? [...postes.entries()].filter(([p]) => !modeles.has(p)).map(([poste, cout]) => ({ poste, cout: arrondi(cout) })) : [],
    clients: lignes.sort((x, y) => y.conversations - x.conversations || y.tours - x.tours || x.client.localeCompare(y.client)),
  };
}
