// Le joueur d'Alix pour le banc de parité : joue les cas neutres (parite/cas.json) sur Alix entière, telle que son
// banc noté la fait tourner (test/simulation-banc.js de son dépôt : la vraie gestion du site sur sa donnée, WhatsApp,
// GitHub et l'horloge simulés, le vrai Claude), et écrit une trace par cas. La notation est commune (parite/noter.py).
// Rien n'est modifié dans le dépôt d'Alix : il est seulement lu.
//
//   node --import <dépôt>/alix/test/bouchons/enregistrer.js parite/alix.mjs <dépôt> <sortie> [--cas G01,V03] [--modele …] [--effort …]
//
// La clé Anthropic se lit dans ANTHROPIC_API_KEY ou ~/.config/alix-essai/anthropic.key, jamais affichée.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const [depot, sortie] = process.argv.slice(2);
const arg = (nom, defaut) => (process.argv.includes(`--${nom}`) ? process.argv[process.argv.indexOf(`--${nom}`) + 1] : defaut);
const MODELE = arg("modele", "claude-sonnet-5-5");
const EFFORT = arg("effort", "medium");
const CHOIX = arg("cas", null)?.split(",");
const CLE = process.env.ANTHROPIC_API_KEY || fs.readFileSync(path.join(os.homedir(), ".config", "alix-essai", "anthropic.key"), "utf8").trim();
const ici = path.dirname(fileURLToPath(import.meta.url));
const { cas: CAS, greg: GREG } = JSON.parse(fs.readFileSync(path.join(ici, "cas.json"), "utf8"));

const vraiFetch = globalThis.fetch;
const alix = (f) => pathToFileURL(path.join(depot, "alix", f)).href;
const { banc, avancer } = await import(alix("test/simulation-banc.js"));
const { espace } = await import(alix("test/bouchons/espaces.js"));
const { ConversationVisiteur } = await import(alix("src/visiteurs/conversation.js"));

async function jouer(c) {
  const b = banc({ approuves: ["fsp_demande_information"], modeles: { MODELE_DEMANDE: "fsp_demande_information" } });
  const env = b.env;
  Object.assign(env, { ANTHROPIC_API_KEY: CLE, MODELE_CONVERSATION: MODELE, CLAUDE_EFFORT: EFFORT,
    SITE_MARBELLA: "https://fsp-marbella.pages.dev", SITE_DUBAI: "https://fsp-dubai.pages.dev" });
  env.CONVERSATIONS_VISITEURS = espace(ConversationVisiteur, env);
  b.entrants.set(GREG, Date.now());
  const outils = [], resultats = [], gestion = [];
  let appels = 0;
  const fauxFetch = globalThis.fetch;
  globalThis.fetch = async (url, o = {}) => {
    const u = String(url instanceof Request ? url.url : url);
    if (u.startsWith("https://api.anthropic.com/")) {
      appels++;
      try {
        const dernier = JSON.parse(o.body).messages?.at(-1);
        if (dernier?.role === "user" && Array.isArray(dernier.content)) {
          for (const x of dernier.content) if (x.type === "tool_result") resultats.push(String(typeof x.content === "string" ? x.content : JSON.stringify(x.content)).slice(0, 1500));
        }
      } catch { /* corps illisible */ }
      const r = await vraiFetch(url, o);
      try {
        for (const bloc of (await r.clone().json()).content ?? []) if (bloc.type === "tool_use") outils.push({ nom: bloc.name, entree: bloc.input });
      } catch { /* réponse illisible */ }
      return r;
    }
    if (u.startsWith("https://fourseasonsproperties.ch/")) {
      gestion.push({ methode: (o.method || (url instanceof Request ? url.method : "GET")).toUpperCase(), chemin: u.slice("https://fourseasonsproperties.ch".length) });
    }
    return fauxFetch(url, o);
  };
  const tourner = b.laisserTourner;
  b.laisserTourner = async () => {
    for (let i = 0; i < 6; i++) {
      await tourner();
      const v = [...env.CONVERSATIONS_VISITEURS.instances.values()].filter((a) => a.taches.some((t) => t.callback === "lireAttente"));
      if (!v.length) return;
      for (const a of v) {
        const dues = a.taches.filter((t) => t.callback === "lireAttente");
        a.taches = a.taches.filter((t) => !dues.includes(t));
        for (const t of dues) await a.lireAttente(t.payload, t);
      }
    }
  };
  let erreur = null, marque = null;
  try {
    for (const e of c.etapes) {
      if (e.avancer) {
        marque = b.journal.length;
        avancer(e.avancer);
      } else await b.ecrit(e.de === "greg" ? GREG : e.de, e.texte);
    }
  } catch (e) {
    erreur = e.message;
  }
  globalThis.fetch = fauxFetch;
  const journal = b.journal.map((x) => ({ de: x.de === "Alix" ? "agent" : x.de, a: x.a, numero: x.numero ?? null, texte: x.texte || "", touche: x.touche ?? null }));
  return { id: c.id, plateforme: "alix", modele: MODELE, journal, outils, resultats, gestion, appels, erreur, marque };
}

fs.mkdirSync(sortie, { recursive: true });
for (const c of CAS.filter((x) => !CHOIX || CHOIX.includes(x.id))) {
  const t = await jouer(c);
  fs.writeFileSync(path.join(sortie, `${c.id}.json`), JSON.stringify(t, null, 1));
  console.log(`${c.id} joué sur Alix : ${t.outils.length} outil(s), ${t.appels} appel(s)${t.erreur ? `, erreur : ${t.erreur}` : ""}`);
}
