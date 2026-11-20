// Le relevé chiffré de chaque agent (20.11.2026). À l'alarme, au plus tous les quarts d'heure, l'objet d'un client lit
// le relevé de son conteneur (/interne/releve) et le range dans l'annuaire (D1), avec son état. La console de MEGGA
// lit ensuite tous les clients d'un coup (GET /admin/releves), sans réveiller aucun conteneur.
//
// Rien de privé ne passe : le relevé est reconstruit champ par champ (nettoyer). Ce qui n'est pas un nombre ou un nom
// de la liste permise (fournisseur, genre du journal, version de l'image) est écarté, quoi qu'envoie le conteneur ; un
// modèle au nom non permis garde ses jetons sous « inconnu », que les coûts signalent sans tarif.

export const RELEVE_MS = 15 * 60 * 1000;
// Un an et un mois d'historique, puis les jours les plus anciens s'effacent.
const JOURS_GARDES = 400;
// La lecture : un trimestre au plus, par pages de 50 clients (au plus 4 600 rangs, quelques Mo).
export const JOURS_LUS_MAX = 92;
export const CLIENTS_PAR_PAGE = 50;
// Le rattrapage : après une absence, le relevé redemande les jours manqués, deux semaines au plus (noyau/suivi.py).
export const JOURS_RELEVE_MAX = 14;
const TAILLE_MAX = 256 * 1024;
const JOUR = /^\d{4}-\d{2}-\d{2}$/;
const NOM_MODELE = /^[A-Za-z0-9][A-Za-z0-9._:/-]{0,79}$/;
const NOM_COURT = /^[A-Za-z0-9][A-Za-z0-9 ._-]{0,39}$/;
const GENRE = /^[a-z][a-z0-9_]{0,29}$/;
const REVISION = /^[0-9a-f]{7,40}$/;

const nombre = (v) => (typeof v === "number" && Number.isFinite(v) && v >= 0 ? v : 0);
const ou = (v, motif) => (typeof v === "string" && motif.test(v) ? v : null);
const objet = (v) => (v && typeof v === "object" && !Array.isArray(v) ? v : {});

function nettoyerJour(j) {
  j = objet(j);
  const modeles = {};
  for (const [id, m] of Object.entries(objet(j.modeles)).slice(0, 20)) {
    const x = objet(m);
    const cle = NOM_MODELE.test(id) && id !== "inconnu" ? id : "inconnu";
    const e = (modeles[cle] ??= { fournisseur: null, tours: 0, entree: 0, sortie: 0, cache_lecture: 0, cache_ecriture: 0 });
    if (cle !== "inconnu") e.fournisseur = ou(x.fournisseur, NOM_COURT);
    for (const k of ["tours", "entree", "sortie", "cache_lecture", "cache_ecriture"]) e[k] += nombre(x[k]);
  }
  const journal = {};
  for (const [g, v] of Object.entries(objet(j.journal)).slice(0, 60)) {
    if (GENRE.test(g)) journal[g] = { nombre: nombre(objet(v).nombre), quantite: nombre(objet(v).quantite) };
  }
  const d = objet(j.delais);
  const delai = (x) => ({ nombre: nombre(objet(x).nombre), moyenne: objet(x).moyenne == null ? null : nombre(objet(x).moyenne) });
  return { tours: nombre(j.tours), tours_api: nombre(j.tours_api), tours_en_echec: nombre(j.tours_en_echec), secours: nombre(j.secours),
    personnes: nombre(j.personnes), modeles, journal, delais: { lecture: delai(d.lecture), reponse: delai(d.reponse), lentes: nombre(d.lentes) } };
}

/** Le relevé tel qu'il est rangé : seulement des nombres et des noms permis. Rend null s'il n'a pas la forme attendue. */
export function nettoyer(brut) {
  const r = objet(brut);
  if (r.forme !== 1) return null;
  const jours = {};
  for (const [jour, j] of Object.entries(objet(r.jours)).slice(0, JOURS_RELEVE_MAX)) if (JOUR.test(jour)) jours[jour] = nettoyerJour(j);
  if (!Object.keys(jours).length) return null;
  const image = objet(r.image);
  return {
    image: { version: ou(image.version, NOM_COURT), revision: ou(image.revision, REVISION) },
    rappels_en_attente: nombre(r.rappels_en_attente),
    derniere_activite: r.derniere_activite == null ? null : nombre(r.derniere_activite),
    jours,
  };
}

/** L'état rangé avec le relevé : conteneur démarré, pannes en cours et récentes (genre et heures, sans message). */
export function etatRange(etat, releve, maintenant) {
  const alertes = Array.isArray(etat?.alertes) ? etat.alertes : [];
  return {
    demarre: Boolean(etat?.demarre),
    pannes_en_cours: alertes.filter((a) => !a.resolue).map((a) => ({ quoi: String(a.quoi).slice(0, 20), quand: nombre(a.quand) })),
    pannes_24h: alertes.filter((a) => nombre(a.quand) > maintenant - 24 * 3600 * 1000).length,
    image: releve.image,
    rappels_en_attente: releve.rappels_en_attente,
    derniere_activite: releve.derniere_activite,
  };
}

/** Range le relevé d'un client : un rang par jour, son état, et l'effacement des jours trop anciens. */
export async function ranger(db, client, releve, etat, maintenant = Date.now()) {
  const limite = new Date(maintenant - JOURS_GARDES * 86400 * 1000).toISOString().slice(0, 10);
  const ecritures = Object.entries(releve.jours).map(([jour, chiffres]) =>
    db.prepare(
      "INSERT INTO releves (client, jour, chiffres, maj_le) VALUES (?, ?, ?, ?) " +
        "ON CONFLICT(client, jour) DO UPDATE SET chiffres = excluded.chiffres, maj_le = excluded.maj_le",
    ).bind(client, jour, JSON.stringify(chiffres), maintenant),
  );
  ecritures.push(
    db.prepare("INSERT INTO etats (client, etat, maj_le) VALUES (?, ?, ?) ON CONFLICT(client) DO UPDATE SET etat = excluded.etat, maj_le = excluded.maj_le")
      .bind(client, JSON.stringify(etatRange(etat, releve, maintenant)), maintenant),
    db.prepare("DELETE FROM releves WHERE client = ? AND jour < ?").bind(client, limite),
  );
  await (db.batch ? db.batch(ecritures) : Promise.all(ecritures.map((e) => e.run())));
}

/** Les jours à relire : aujourd'hui et hier, plus ceux manqués depuis le dernier relevé rangé (deux semaines au plus). */
export function joursARelire(reussi, maintenant) {
  if (!reussi) return JOURS_RELEVE_MAX; // le premier relevé reprend l'historique
  const jour = (t) => Math.floor(t / 86400000);
  return Math.max(2, Math.min(jour(maintenant) - jour(reussi) + 1, JOURS_RELEVE_MAX));
}

/**
 * À l'alarme de l'objet d'un client : un relevé si le dernier essai date de plus d'un quart d'heure. Le conteneur tourne
 * déjà (l'alarme vient de le réveiller). Rien n'est levé : un échec est gardé à part (releve_echec, rendu par etat()),
 * jamais parmi les pannes du conteneur, pour ne pas les chasser ni les faire croire réparées. La console voit l'agent
 * silencieux à l'heure de son dernier relevé rangé (etats.maj_le). Rend vrai si un relevé a été rangé.
 */
export async function releverSiDu(objetClient, port, jeton, maintenant = Date.now()) {
  const stock = objetClient.ctx.storage;
  if (maintenant - ((await stock.get("releve_le")) ?? 0) < RELEVE_MS) return false;
  // L'essai compte, réussi ou non : un conteneur qui ne rend pas son relevé n'est pas relancé à chaque alarme.
  await stock.put("releve_le", maintenant);
  try {
    const jours = joursARelire(await stock.get("releve_reussi"), maintenant);
    const r = await port.fetch(`http://container/interne/releve?jours=${jours}`, { headers: { "x-megga-interne": jeton }, signal: AbortSignal.timeout(20_000) });
    const texte = await r.text();
    if (!r.ok) throw new Error(`relevé ${r.status}`);
    if (texte.length > TAILLE_MAX) throw new Error("relevé trop gros");
    const releve = nettoyer(JSON.parse(texte));
    if (!releve) throw new Error("relevé mal formé");
    await ranger(objetClient.env.ANNUAIRE, objetClient.ctx.id.name, releve, await objetClient.etat(), maintenant);
    await stock.put("releve_reussi", maintenant);
    await stock.delete("releve_echec");
    return true;
  } catch (e) {
    const avant = (await stock.get("releve_echec").catch(() => null)) ?? { depuis: maintenant, essais: 0 };
    await stock.put("releve_echec", { depuis: avant.depuis, essais: avant.essais + 1, quand: maintenant, message: String(e?.message ?? e).slice(0, 200) }).catch(() => {});
    return false;
  }
}

/**
 * Les relevés des clients de l'annuaire sur les `jours` derniers jours (1 à 92), une page de 50 clients après `apres`
 * (dans l'ordre des identifiants) ; `suivant` donne la page suivante, null à la dernière.
 */
export async function lireReleves(db, jours, apres = "", maintenant = Date.now()) {
  if (!Number.isInteger(jours) || jours < 1 || jours > JOURS_LUS_MAX) throw new RangeError(`jours : de 1 à ${JOURS_LUS_MAX}`);
  const depuis = new Date(maintenant - (jours - 1) * 86400 * 1000).toISOString().slice(0, 10);
  const { results: page = [] } = await db
    .prepare("SELECT id, zone, actif, version FROM clients WHERE id > ? ORDER BY id LIMIT ?")
    .bind(apres, CLIENTS_PAR_PAGE + 1)
    .all();
  const clients = page.slice(0, CLIENTS_PAR_PAGE);
  const suivant = page.length > CLIENTS_PAR_PAGE ? clients.at(-1).id : null;
  if (!clients.length) return { depuis, jours, clients: [], suivant };
  const ids = clients.map((c) => c.id);
  const places = ids.map(() => "?").join(", ");
  const [etats, lignes] = await Promise.all([
    db.prepare(`SELECT client, etat, maj_le FROM etats WHERE client IN (${places})`).bind(...ids).all(),
    db.prepare(`SELECT client, jour, chiffres FROM releves WHERE client IN (${places}) AND jour >= ? ORDER BY jour`).bind(...ids, depuis).all(),
  ]);
  const parClient = new Map(clients.map((c) => [c.id, { ...c, actif: Boolean(c.actif), etat: null, releve_le: null, jours: {} }]));
  for (const e of etats.results ?? []) {
    const c = parClient.get(e.client);
    if (c) Object.assign(c, { etat: JSON.parse(e.etat), releve_le: e.maj_le });
  }
  for (const l of lignes.results ?? []) {
    const c = parClient.get(l.client);
    if (c) c.jours[l.jour] = JSON.parse(l.chiffres);
  }
  return { depuis, jours, clients: [...parClient.values()], suivant };
}
