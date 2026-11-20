import { execFileSync } from "node:child_process";
import { join } from "node:path";
import { crc32, deflateSync } from "node:zlib";
import { expect, test, type Browser, type BrowserContext, type Page } from "@playwright/test";
import { DROITS_EXTERNE } from "../src/lib/admin/droits";
import { TA } from "../src/lib/admin/textes";
import { T } from "../src/lib/textes";
import { EXTERNE_ESSAI, ORDINAIRE_ESSAI, SUPERADMIN_ESSAI } from "./compte";

// Les parcours de l'admin, joués en série sur la même base (playwright.config.ts) : le superadmin du premier sert aux suivants,
// le compte ordinaire du troisième au quatrième. L'atelier d'essai (agents/atelier_essai.py) fournit les clients.

test.describe.configure({ mode: "serial", timeout: 120_000 });

// Une adresse de client à ces parcours, comme la transmettrait un relais. Sans elle, en production, Better Auth compte les
// connexions de tout le monde ensemble (trois en dix secondes par chemin) : ces parcours épuisaient le compte de ceux de la
// console, joués juste après sur le même serveur.
const ADRESSE = { "x-forwarded-for": "198.51.100.65" };
test.use({ extraHTTPHeaders: ADRESSE });

type Session = Awaited<ReturnType<BrowserContext["storageState"]>>;
/**
 * La session du superadmin, gardée à la fin du premier parcours : les suivants la reprennent au lieu de se reconnecter. En
 * production, Better Auth n'admet que trois connexions en dix secondes d'une même adresse, et le quatrième parcours en fait trois.
 */
let sessionChef: Session | undefined;

/** Un navigateur à part (les réglages de playwright.config.ts), avec une session gardée s'il en faut une. */
const navigateur = (browser: Browser, baseURL: string | undefined, storageState?: Session) =>
  browser.newContext({ baseURL, locale: "fr-FR", viewport: { width: 1440, height: 900 }, storageState, extraHTTPHeaders: ADRESSE });

/** Le superadmin du premier parcours, déjà connecté, sur la vue d'ensemble. */
async function superadmin(browser: Browser, baseURL: string | undefined): Promise<{ contexte: BrowserContext; page: Page }> {
  expect(sessionChef, "la session du premier parcours").toBeDefined();
  const contexte = await navigateur(browser, baseURL, sessionChef);
  const page = await contexte.newPage();
  await page.goto("/admin");
  await expect(page.getByRole("heading", { name: TA.vueEnsemble, level: 1, exact: true })).toBeVisible();
  return { contexte, page };
}

/** La base de la console des essais (playwright.config.ts), où la commande écrit l'invitation du premier superadmin. */
const BASE_ESSAI = ".donnees/e2e.sqlite";
/** Les clients fictifs de l'atelier d'essai (CLIENTS dans agents/atelier_essai.py). */
const BOULANGERIE = { id: "boulangerie-essai", entreprise: "Boulangerie des Essais" };
const GARAGE = { id: "garage-essai", entreprise: "Garage des Essais" };
const CHALET = { id: "chalet-essai", entreprise: "Chalet des Essais" };
/** Le titre de la page introuvable de la racine (src/app/not-found.tsx) : l'admin s'efface comme une adresse inconnue. */
const INTROUVABLE = T.pageIntrouvable;
/** Le modèle d'essai de l'atelier répond ainsi (ModeleEssai, agents/serveur.py). */
const REPONSE_ESSAI = "Bien reçu";

/** Les requêtes de la page hors de la console (ni localhost ni 127.0.0.1) : il ne doit y en avoir aucune. */
function requetesAilleurs(page: Page): string[] {
  const ailleurs: string[] = [];
  page.on("request", (r) => {
    const h = new URL(r.url()).hostname;
    if (!["localhost", "127.0.0.1"].includes(h) && !r.url().startsWith("data:")) ailleurs.push(r.url());
  });
  return ailleurs;
}

/** Se connecte par /connexion et arrive dans la console. */
async function connecter(page: Page, compte: { courriel: string; motDePasse: string }) {
  await page.goto("/connexion");
  await page.getByLabel(T.courriel).fill(compte.courriel);
  await page.getByLabel(T.motDePasse).fill(compte.motDePasse);
  await page.getByRole("button", { name: T.seConnecter }).click();
  await expect(page).toHaveURL(/\/$/);
}

/** Ouvre un lien d'invitation, crée le compte (le courriel est celui de l'invitation) et rejoint l'admin. */
async function rejoindre(page: Page, lien: string, compte: { nom: string; courriel: string; motDePasse: string }) {
  await page.goto(lien);
  await expect(page.getByRole("heading", { name: TA.invitationTitre })).toBeVisible();
  await expect(page.getByText(TA.invitationPour(compte.courriel))).toBeVisible();
  await page.getByLabel(TA.votreNom).fill(compte.nom);
  await page.getByLabel(TA.motDePasse).fill(compte.motDePasse);
  await page.getByRole("button", { name: TA.creerEtRejoindre }).click();
  await expect(page).toHaveURL(/\/admin$/);
}

const rail = (page: Page) => page.getByRole("navigation", { name: TA.railAdmin });
const titre = (page: Page, nom: string) => page.getByRole("heading", { name: nom, level: 1, exact: true });

/** La page ne défile pas de côté : ni le document, ni la zone de la page à droite du rail. */
const deborde = (page: Page) =>
  page.evaluate(
    () =>
      document.documentElement.scrollWidth > document.documentElement.clientWidth ||
      [...document.querySelectorAll("main")].some((m) => m.scrollWidth > m.clientWidth),
  );

/** Les tableaux qui défilent de côté dans leur cadre (components/admin/tableau.tsx), par leurs en-têtes : à 800 px, aucun. */
const tableauxQuiDefilent = (page: Page) =>
  page.evaluate(() =>
    [...document.querySelectorAll("main .overflow-x-auto")]
      .filter((cadre) => cadre.querySelector("table") && cadre.scrollWidth > cadre.clientWidth + 1)
      .map((cadre) => [...cadre.querySelectorAll("th")].map((th) => th.textContent).join(" / ")),
  );

test("un superadmin invité par la commande pilote un client et le retrouve au journal", async ({ page, baseURL }) => {
  const ailleurs = requetesAilleurs(page);
  // La commande, lancée sur le serveur de la console, imprime le lien d'invitation superadmin.
  const env: NodeJS.ProcessEnv = { ...process.env, CONSOLE_BASE: BASE_ESSAI, BETTER_AUTH_URL: baseURL };
  delete env.NODE_OPTIONS; // rien du chargeur des essais dans la commande, lancée comme sur le serveur
  const sortie = execFileSync("npm", ["run", "-s", "admin:inviter", "--", SUPERADMIN_ESSAI.courriel], {
    cwd: join(__dirname, ".."),
    env,
    encoding: "utf8",
  });
  const lien = sortie.trim().split("\n").at(-1) ?? "";
  expect(lien.startsWith(`${baseURL}/admin/invitation/`)).toBe(true);
  await rejoindre(page, lien, SUPERADMIN_ESSAI);

  // La vue d'ensemble, d'après le relevé chiffré : les tuiles, dont le coût ; la santé de chaque client, la pire d'abord.
  await expect(titre(page, TA.vueEnsemble)).toBeVisible();
  await expect(page.getByText(TA.clientsEnService, { exact: true })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText(TA.cout, { exact: true }).first()).toBeVisible();
  // Le coût se lit en entier, devise comprise : la tuile passe à la ligne plutôt que de le couper.
  const valeurCout = page.getByText(TA.cout, { exact: true }).first().locator("xpath=following-sibling::b");
  await expect(valeurCout).toContainText(/\d/);
  expect(await valeurCout.evaluate((b) => b.scrollWidth <= b.clientWidth)).toBe(true);
  const sante = page.getByRole("table").filter({ has: page.getByRole("columnheader", { name: TA.sante, exact: true }) });
  const ligneGarage = sante.getByRole("row").filter({ has: page.getByRole("link", { name: GARAGE.entreprise, exact: true }) });
  await expect(ligneGarage.getByText(TA.santes.panne, { exact: true })).toBeVisible(); // une panne de transmission dure
  await expect(sante.getByRole("row").filter({ hasText: "Fleuriste des Essais" }).getByText(TA.santes.silencieux, { exact: true })).toBeVisible();
  await page.screenshot({ path: "captures/admin-vue.png", fullPage: true });

  // La boulangerie : sa fiche, puis ses versions.
  await rail(page).getByRole("link", { name: TA.clients, exact: true }).click();
  await expect(titre(page, TA.clients)).toBeVisible();
  await page.getByRole("link", { name: BOULANGERIE.entreprise, exact: true }).click();
  await expect(titre(page, BOULANGERIE.entreprise)).toBeVisible();
  await page.screenshot({ path: "captures/admin-client.png", fullPage: true });
  await page.getByRole("link", { name: TA.versions, exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/admin/clients/${BOULANGERIE.id}/versions$`));

  // Un brouillon d'après la version en service : valider montre ce qui changerait, puis le créer l'ouvre.
  await expect(page.getByText(TA.dApresEnService(1))).toBeVisible();
  await page.getByLabel(TA.changements, { exact: true }).fill(TA.exempleChangements);
  await page.getByRole("button", { name: TA.valider, exact: true }).click();
  await expect(page.getByText(TA.resultatValide(1))).toBeVisible();
  await page.getByRole("button", { name: TA.creerBrouillon }).click();
  await page.getByRole("dialog").getByRole("button", { name: TA.creerBrouillon, exact: true }).click(); // chaque geste se confirme
  await expect(page).toHaveURL(/\/versions\?v=2$/);

  // Jamais essayé, il ne se met en service qu'en forçant ; un essai, et « Mettre en service » vient.
  await expect(page.getByRole("button", { name: TA.forcer })).toBeVisible();
  await expect(page.getByText(TA.essaiConsomme)).toBeVisible();
  await page.getByLabel(TA.votreMessage).fill("Bonjour, vous livrez le dimanche ?");
  await page.getByRole("button", { name: TA.envoyer, exact: true }).click();
  await expect(page.getByRole("listitem").filter({ hasText: TA.envoye })).toContainText(REPONSE_ESSAI, { timeout: 30_000 });
  await expect(page.getByRole("button", { name: TA.forcer })).toHaveCount(0);
  await page.screenshot({ path: "captures/admin-versions.png", fullPage: true });

  // Mettre en service : une confirmation qui dit son effet (le conteneur redémarre).
  await page.getByRole("button", { name: TA.mettreEnService, exact: true }).click();
  const confirmation = page.getByRole("dialog");
  await expect(confirmation).toContainText(TA.mettreEnServiceTitre(2));
  await expect(confirmation).toContainText(TA.effetActiver(2));
  await page.screenshot({ path: "captures/admin-confirmation.png" });
  await confirmation.getByRole("button", { name: TA.mettreEnService, exact: true }).click();
  await expect(page.getByText(TA.enServiceFait(2))).toBeVisible({ timeout: 30_000 });
  const ligne = (n: number) => page.getByRole("row").filter({ has: page.getByRole("link", { name: TA.versionNumero(n), exact: true }) });
  await expect(ligne(2)).toContainText(TA.enService);
  await expect(ligne(1)).not.toContainText(TA.enService);

  // Le journal garde la mise en service, réussie, sur la boulangerie, avec le courriel du superadmin.
  await rail(page).getByRole("link", { name: TA.journal, exact: true }).click();
  await expect(titre(page, TA.journal)).toBeVisible();
  const trace = page
    .getByRole("row")
    .filter({ hasText: `client:${BOULANGERIE.id}` })
    .filter({ hasText: TA.actionsJournal["clients.activer"] });
  await expect(trace).toHaveCount(1);
  await expect(trace).toContainText(TA.reussi);
  await expect(trace).toContainText(SUPERADMIN_ESSAI.courriel);
  await page.screenshot({ path: "captures/admin-journal.png", fullPage: true });

  // Le menu du compte : de l'admin à la console, et retour par « Administration ».
  await page.getByRole("button", { name: T.compteEtReglages }).click();
  await page.getByRole("menuitem", { name: TA.retourConsole }).click();
  await expect(page).toHaveURL(/\/$/);
  await page.getByRole("button", { name: T.compteEtReglages }).click();
  await page.getByRole("menuitem", { name: TA.administration }).click();
  await expect(titre(page, TA.vueEnsemble)).toBeVisible();
  expect(ailleurs).toEqual([]);
  sessionChef = await page.context().storageState();
});

test("un externe ne voit que son client", async ({ browser, baseURL }) => {
  const { contexte: chef, page } = await superadmin(browser, baseURL);
  const ailleurs = requetesAilleurs(page);
  await rail(page).getByRole("link", { name: TA.equipe, exact: true }).click();
  await expect(titre(page, TA.equipe)).toBeVisible();
  await page.getByRole("link", { name: TA.invitations, exact: true }).click();
  await expect(page).toHaveURL(/\/admin\/equipe\/invitations$/);

  // Le rôle proposé d'abord est le plus étroit ; l'externe est invité au rôle Exploitation, limité au garage.
  const role = page.getByLabel(TA.role, { exact: true });
  await expect(role.locator("option:checked")).toHaveText(TA.roleLecture);
  await page.getByLabel(TA.courriel, { exact: true }).fill(EXTERNE_ESSAI.courriel);
  await role.selectOption({ label: TA.roleExploitation });
  await page.getByLabel(TA.externeCase).check();
  await expect(page.getByText(TA.externeGarde)).toBeVisible();
  for (const d of DROITS_EXTERNE) await expect(page.getByText(TA.nomsDroits[d], { exact: true })).toBeVisible();
  await page.getByRole("textbox", { name: TA.uneListe }).fill(GARAGE.id);
  await page.screenshot({ path: "captures/admin-equipe.png", fullPage: true });
  await page.getByRole("button", { name: TA.inviter, exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: TA.inviter, exact: true }).click(); // chaque geste se confirme

  // Le lien, montré une fois : ni Échap ni un clic au-dehors ne le ferment, seulement « Fermer » ; ensuite il n'est plus nulle part.
  const secret = page.getByRole("dialog");
  await expect(secret).toContainText(TA.secretTitre);
  const lien = (await secret.getByText(/\/admin\/invitation\/\S+/).innerText()).trim();
  expect(lien.startsWith(`${baseURL}/admin/invitation/`)).toBe(true);
  await page.keyboard.press("Escape");
  await expect(secret).toBeVisible();
  await secret.getByRole("button", { name: TA.fermer, exact: true }).click();
  await expect(secret).toBeHidden();
  await expect(page.getByText(lien)).toHaveCount(0);
  const enAttente = page.getByRole("row").filter({ hasText: EXTERNE_ESSAI.courriel });
  await expect(enAttente).toContainText(TA.externe);
  await expect(enAttente).toContainText(GARAGE.id);
  // À 800 px, l'invitation en attente se lit sans défilement de côté : ses colonnes secondaires se replient sous le courriel.
  await page.setViewportSize({ width: 800, height: 900 });
  await expect(enAttente).toContainText(GARAGE.id);
  expect(await tableauxQuiDefilent(page)).toEqual([]);
  await page.setViewportSize({ width: 1440, height: 900 });

  // L'externe, dans son propre navigateur : il rejoint par le lien.
  const contexte = await navigateur(browser, baseURL);
  const externe = await contexte.newPage();
  const ailleursExterne = requetesAilleurs(externe);
  await rejoindre(externe, lien, EXTERNE_ESSAI);

  // Son rail : la vue d'ensemble et les clients, ni Comptes, ni Tarifs, ni Équipe, ni Journal. Aucun coût nulle part.
  await expect(rail(externe).getByRole("link")).toHaveText([TA.vueEnsemble, TA.clients, TA.alertes, TA.installations]);
  await expect(externe.getByText(TA.clientsEnService, { exact: true })).toBeVisible({ timeout: 15_000 });
  await expect(externe.getByRole("main")).not.toContainText(TA.cout);
  await expect(externe.getByRole("heading", { name: TA.console, exact: true })).toHaveCount(0);
  await externe.screenshot({ path: "captures/admin-externe.png", fullPage: true });

  // Clients : le garage seul.
  await rail(externe).getByRole("link", { name: TA.clients, exact: true }).click();
  await expect(titre(externe, TA.clients)).toBeVisible();
  await expect(externe.getByRole("table").getByRole("link")).toHaveText([GARAGE.entreprise]);
  await externe.getByRole("link", { name: GARAGE.entreprise, exact: true }).click();
  await expect(titre(externe, GARAGE.entreprise)).toBeVisible();
  await expect(externe.getByRole("heading", { name: TA.parModele, level: 2 })).toBeVisible();
  await expect(externe.getByRole("main")).not.toContainText(TA.cout);

  // Un autre client, l'équipe : la page introuvable, comme si l'admin n'existait pas.
  for (const adresse of [`/admin/clients/${BOULANGERIE.id}`, "/admin/equipe"]) {
    await externe.goto(adresse);
    await expect(titre(externe, INTROUVABLE)).toBeVisible();
    await expect(rail(externe)).toHaveCount(0);
    await expect(externe.getByText(BOULANGERIE.entreprise)).toHaveCount(0);
  }

  // Ses conversations : l'adresse d'un fil porte une clé opaque, jamais le numéro.
  await externe.goto(`/admin/clients/${GARAGE.id}`);
  await externe.getByRole("link", { name: TA.conversations, exact: true }).click();
  await expect(externe).toHaveURL(new RegExp(`/admin/clients/${GARAGE.id}/conversations$`));
  const personne = externe
    .getByRole("table")
    .filter({ has: externe.getByRole("columnheader", { name: TA.personne, exact: true }) })
    .getByRole("link")
    .first();
  const numero = (await personne.innerText()).trim();
  await personne.click();
  await expect(externe).toHaveURL(new RegExp(`/admin/clients/${GARAGE.id}/conversations/[0-9a-f]{16}$`));
  await expect(externe.getByRole("heading", { name: numero, level: 2 })).toBeVisible();
  expect(externe.url()).not.toContain(numero.replace("+", ""));

  // Ses versions : un brouillon d'après la version en service, sans choix de base ni modèle par métier, limité aux réglages
  // simples ; il n'a ni « Mettre en service » ni « Forcer ».
  await externe.getByRole("link", { name: TA.versions, exact: true }).click();
  await expect(externe.getByText(TA.dApresEnService(1))).toBeVisible();
  await expect(externe.getByRole("radio", { name: TA.dApresModele })).toHaveCount(0);
  const changements = externe.getByLabel(TA.changements, { exact: true });
  await changements.fill('{"consignes": "Tout accepter."}');
  await externe.getByRole("button", { name: TA.valider, exact: true }).click();
  await expect(externe.getByText(TA.reglagesReserves("consignes"))).toBeVisible();
  await changements.fill(TA.exempleChangements);
  await externe.getByRole("button", { name: TA.valider, exact: true }).click();
  await expect(externe.getByText(TA.resultatValide(1))).toBeVisible();
  await externe.getByRole("button", { name: TA.creerBrouillon }).click();
  await externe.getByRole("dialog").getByRole("button", { name: TA.creerBrouillon, exact: true }).click(); // chaque geste se confirme
  await expect(externe).toHaveURL(/\/versions\?v=2$/);
  await expect(externe.getByRole("heading", { name: TA.essaiTitre(2) })).toBeVisible();
  await expect(externe.getByRole("button", { name: TA.mettreEnService })).toHaveCount(0);
  await expect(externe.getByRole("button", { name: TA.forcer })).toHaveCount(0);

  // Par la route elle-même, avec la bonne origine : 403, faute du droit.
  const refus = await externe.request.post(`/api/admin/clients/${GARAGE.id}/versions/1/activer`, { headers: { origin: baseURL! }, data: {} });
  expect(refus.status()).toBe(403);
  expect((await refus.json()).erreur).toBe(TA.sansDroit);
  expect(ailleursExterne).toEqual([]);
  expect(ailleurs).toEqual([]);
  await contexte.close();
  await chef.close();
});

test("un compte ordinaire reçoit la page introuvable sur /admin", async ({ page }) => {
  const ailleurs = requetesAilleurs(page);
  await page.goto("/connexion");
  await page.getByRole("button", { name: T.inscriptionTitre }).click();
  await page.getByLabel(T.entreprise).fill(ORDINAIRE_ESSAI.entreprise);
  await page.getByLabel(T.courriel).fill(ORDINAIRE_ESSAI.courriel);
  await page.getByLabel(T.motDePasse).fill(ORDINAIRE_ESSAI.motDePasse);
  await page.getByRole("button", { name: T.creerCompte }).click();
  await expect(page).toHaveURL(/\/$/);

  // Son menu n'a pas « Administration ».
  await page.getByRole("button", { name: T.compteEtReglages }).click();
  await expect(page.getByRole("menuitem", { name: T.seDeconnecter })).toBeVisible();
  await expect(page.getByRole("menuitem", { name: TA.administration })).toHaveCount(0);
  await page.keyboard.press("Escape");

  // /admin : la page introuvable (en production, son statut peut être 200 : c'est le contenu qui compte).
  await page.goto("/admin");
  await expect(titre(page, INTROUVABLE)).toBeVisible();
  await expect(rail(page)).toHaveCount(0);
  await expect(titre(page, TA.vueEnsemble)).toHaveCount(0);
  expect(ailleurs).toEqual([]);
});

test("un compte suspendu ne se connecte plus", async ({ browser, baseURL }) => {
  const motif = "Essai de suspension";
  // Le compte ordinaire, connecté dans son propre navigateur : ses requêtes passent. Ses trois connexions sont les seules
  // de ce fichier (sessionChef).
  const contexte = await navigateur(browser, baseURL);
  const ordinaire = await contexte.newPage();
  await connecter(ordinaire, ORDINAIRE_ESSAI);
  expect((await ordinaire.request.get("/api/agents")).status()).toBe(200);

  // Le superadmin le suspend, avec un motif, derrière une confirmation qui dit l'effet.
  const { contexte: chef, page } = await superadmin(browser, baseURL);
  await rail(page).getByRole("link", { name: TA.comptes, exact: true }).click();
  await expect(titre(page, TA.comptes)).toBeVisible();
  await page.screenshot({ path: "captures/admin-comptes.png", fullPage: true });
  await page.getByRole("link", { name: ORDINAIRE_ESSAI.entreprise, exact: true }).click();
  await expect(titre(page, ORDINAIRE_ESSAI.entreprise)).toBeVisible();
  await page.getByLabel(TA.motif, { exact: true }).fill(motif);
  await page.getByRole("button", { name: TA.suspendre, exact: true }).click();
  const confirmation = page.getByRole("dialog");
  await expect(confirmation).toContainText(TA.effetSuspendre);
  await confirmation.getByRole("button", { name: TA.suspendre, exact: true }).click();
  await expect(page.getByText(TA.compteSuspenduFait)).toBeVisible();
  await expect(page.getByText(TA.motifSuspension(motif))).toBeVisible();

  // Ses sessions sont fermées tout de suite ; il ne se reconnecte pas, et lit pourquoi.
  expect((await ordinaire.request.get("/api/agents")).status()).toBe(401);
  await ordinaire.goto("/connexion");
  await ordinaire.getByLabel(T.courriel).fill(ORDINAIRE_ESSAI.courriel);
  await ordinaire.getByLabel(T.motDePasse).fill(ORDINAIRE_ESSAI.motDePasse);
  await ordinaire.getByRole("button", { name: T.seConnecter }).click();
  await expect(ordinaire.getByText(T.compteSuspendu)).toBeVisible();

  // Réactivé, il se reconnecte.
  await page.getByRole("button", { name: TA.reactiver, exact: true }).click();
  await expect(confirmation).toContainText(TA.effetReactiver);
  await confirmation.getByRole("button", { name: TA.reactiver, exact: true }).click();
  await expect(page.getByText(TA.compteReactive)).toBeVisible();
  await ordinaire.getByRole("button", { name: T.seConnecter }).click();
  await expect(ordinaire).toHaveURL(/\/$/);
  await contexte.close();
  await chef.close();
});

test("à 390 et à 800 px, en clair et en Nuit douce", async ({ browser, baseURL }) => {
  const { contexte: chef, page } = await superadmin(browser, baseURL);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByText(TA.clientsEnService, { exact: true })).toBeVisible({ timeout: 15_000 });
  expect((await rail(page).boundingBox())?.width).toBeCloseTo(76, 0);
  expect(await deborde(page)).toBe(false);
  const entrees = [TA.vueEnsemble, TA.clients, TA.alertes, TA.installations, TA.comptes, TA.tarifs, TA.equipe, TA.journal];
  await expect(rail(page).getByRole("link")).toHaveText(entrees);

  for (const largeur of [390, 800]) {
    await page.setViewportSize({ width: largeur, height: 844 });
    /** La page ne défile pas de côté ; à 800 px, aucun tableau non plus (ses colonnes secondaires se replient). */
    const sansDefilement = async (ou: string) => {
      expect(await deborde(page), `${ou}, ${largeur} px`).toBe(false);
      if (largeur === 800) expect(await tableauxQuiDefilent(page), `${ou}, ${largeur} px`).toEqual([]);
    };

    // Chaque entrée du rail mène à sa page.
    for (const entree of entrees) {
      await rail(page).getByRole("link", { name: entree, exact: true }).click();
      await expect(titre(page, entree)).toBeVisible({ timeout: 15_000 });
      await sansDefilement(entree);
    }

    // Chaque onglet de la fiche d'un client installé hors Cloudflare se voit (aucun caché hors du cadre) et mène à sa page.
    await page.goto(`/admin/clients/${CHALET.id}`);
    await expect(titre(page, CHALET.entreprise)).toBeVisible();
    for (const onglet of [TA.suivi, TA.alertes, TA.conversations, TA.versions, TA.acces, TA.installation]) {
      const lien = page.getByRole("main").getByRole("link", { name: onglet, exact: true });
      await expect(lien).toBeInViewport();
      await lien.click();
      await expect(lien).toHaveAttribute("aria-current", "page");
      await expect(titre(page, CHALET.entreprise)).toBeVisible();
      await sansDefilement(onglet);
    }
  }

  // La vue d'ensemble à 390 px, en clair puis en Nuit douce (le thème du menu du compte).
  await page.setViewportSize({ width: 390, height: 844 });
  await rail(page).getByRole("link", { name: TA.vueEnsemble, exact: true }).click();
  await expect(page.getByText(TA.clientsEnService, { exact: true })).toBeVisible({ timeout: 15_000 });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  const fond = () => page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  const clair = await fond();
  await page.screenshot({ path: "captures/admin-telephone.png", fullPage: true });
  await page.getByRole("button", { name: T.compteEtReglages }).click();
  await page.getByRole("button", { name: T.themeSombre, exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "douce");
  await page.keyboard.press("Escape");
  expect(await fond()).not.toBe(clair);
  await expect(page.getByText(TA.clientsEnService, { exact: true })).toBeVisible();
  expect(await deborde(page)).toBe(false);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.screenshot({ path: "captures/admin-sombre.png", fullPage: true });
  await chef.close();
});

/** Un PNG fabriqué ici : largeur × hauteur pixels, un dégradé (en paysage, pour que le recadrage au centre ait à faire). */
function png(largeur: number, hauteur: number): Buffer {
  const morceau = (type: string, donnees: Buffer) => {
    const longueur = Buffer.alloc(4);
    longueur.writeUInt32BE(donnees.length);
    const corps = Buffer.concat([Buffer.from(type, "ascii"), donnees]);
    const somme = Buffer.alloc(4);
    somme.writeUInt32BE(crc32(corps));
    return Buffer.concat([longueur, corps, somme]);
  };
  const entete = Buffer.alloc(13);
  entete.writeUInt32BE(largeur, 0);
  entete.writeUInt32BE(hauteur, 4);
  entete.set([8, 2, 0, 0, 0], 8); // 8 bits, RVB
  const lignes = Buffer.alloc((largeur * 3 + 1) * hauteur);
  for (let y = 0; y < hauteur; y++) {
    for (let x = 0; x < largeur; x++) lignes.set([Math.round((255 * x) / largeur), 120, Math.round((255 * y) / hauteur)], y * (largeur * 3 + 1) + 1 + x * 3);
  }
  const signature = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
  return Buffer.concat([signature, morceau("IHDR", entete), morceau("IDAT", deflateSync(lignes)), morceau("IEND", Buffer.alloc(0))]);
}

// Le dernier parcours : il change le mot de passe du superadmin et ferme sa session ; aucun ne reprend sessionChef après lui.
test("le superadmin règle son compte : nom, photo, mot de passe ; le retour au site", async ({ browser, baseURL }) => {
  // Une adresse à lui : le parcours d'un compte suspendu vient de faire trois connexions de l'adresse commune (ADRESSE), et
  // Better Auth n'en admet pas une quatrième dans les dix secondes.
  expect(sessionChef, "la session du premier parcours").toBeDefined();
  const autreAdresse = { "x-forwarded-for": "198.51.100.66" };
  const chef = await browser.newContext({ baseURL, locale: "fr-FR", viewport: { width: 1440, height: 900 }, storageState: sessionChef, extraHTTPHeaders: autreAdresse });
  const page = await chef.newPage();
  await page.goto("/admin");
  await expect(titre(page, TA.vueEnsemble)).toBeVisible();
  const ailleurs = requetesAilleurs(page);
  const menu = () => page.getByRole("button", { name: T.compteEtReglages });

  // Le menu du compte : le retour au site, dans un nouvel onglet ; puis Mon compte.
  await menu().click();
  const site = page.getByRole("menuitem", { name: T.retourSite });
  await expect(site).toHaveAttribute("href", "https://megga.ai");
  await expect(site).toHaveAttribute("target", "_blank");
  await expect(site).toHaveAttribute("rel", "noopener noreferrer");
  await page.getByRole("menuitem", { name: T.monCompte }).click();
  await expect(titre(page, T.monCompte)).toBeVisible();
  await expect(page.getByLabel(TA.courriel, { exact: true })).toHaveValue(SUPERADMIN_ESSAI.courriel);
  await expect(page.getByText(TA.cetAppareil)).toBeVisible();

  // Le nom : le menu le montre aussitôt.
  await page.getByLabel(TA.nomAffiche, { exact: true }).fill("Chef Renommé");
  await page.getByRole("button", { name: TA.enregistrer, exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: TA.enregistrer, exact: true }).click(); // chaque geste se confirme
  await expect(page.getByText(TA.nomEnregistre)).toBeVisible();
  await expect(menu()).toContainText("Chef Renommé");

  // La photo : recadrée et réduite dans le navigateur, puis dans le menu et dans la liste de l'équipe.
  await page.locator("#compte-photo").setInputFiles({ name: "photo.png", mimeType: "image/png", buffer: png(640, 400) });
  await page.getByRole("button", { name: TA.enregistrerPhoto }).click();
  await page.getByRole("dialog").getByRole("button", { name: TA.enregistrerPhoto, exact: true }).click(); // chaque geste se confirme
  await expect(page.getByText(TA.photoEnregistree)).toBeVisible();
  const photoMenu = menu().locator("img");
  await expect(photoMenu).toHaveAttribute("src", /^\/api\/compte\/photo\/[^/?]+\?v=[0-9a-f]{12}$/);
  await expect.poll(() => photoMenu.evaluate((img: HTMLImageElement) => img.naturalWidth)).toBe(256);
  const adresse = (await photoMenu.getAttribute("src")) ?? "";
  await page.screenshot({ path: "captures/admin-mon-compte.png", fullPage: true });
  // Sans session, la photo ne se sert pas.
  const anonyme = await browser.newContext({ baseURL, extraHTTPHeaders: autreAdresse });
  expect((await anonyme.request.get(adresse)).status()).toBe(401);
  await anonyme.close();
  await rail(page).getByRole("link", { name: TA.equipe, exact: true }).click();
  await expect(titre(page, TA.equipe)).toBeVisible();
  await expect(page.getByRole("row").filter({ hasText: SUPERADMIN_ESSAI.courriel }).locator(`img[src="${adresse}"]`)).toBeVisible();

  // Le téléphone, en clair : la page ne défile pas de côté.
  await page.goto("/admin/compte");
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(titre(page, T.monCompte)).toBeVisible();
  expect(await deborde(page)).toBe(false);
  await page.screenshot({ path: "captures/admin-mon-compte-telephone.png", fullPage: true });
  await page.setViewportSize({ width: 1440, height: 900 });

  // Le mot de passe : l'ancien exigé ; puis se déconnecter et revenir avec le nouveau.
  const nouveau = "essai-admin-2026-nouveau";
  await page.getByLabel(TA.motDePasseActuel).fill(SUPERADMIN_ESSAI.motDePasse);
  await page.getByLabel(TA.nouveauMotDePasse).fill(nouveau);
  await page.getByLabel(TA.confirmerMotDePasse).fill(nouveau);
  await page.getByRole("button", { name: TA.changerMotDePasse }).click();
  await page.getByRole("dialog").getByRole("button", { name: TA.changerMotDePasse, exact: true }).click(); // chaque geste se confirme
  await expect(page.getByText(TA.motDePasseChange)).toBeVisible();
  await menu().click();
  await page.getByRole("menuitem", { name: T.seDeconnecter }).click();
  await page.getByRole("dialog").getByRole("button", { name: T.seDeconnecter, exact: true }).click(); // chaque geste se confirme
  await expect(page).toHaveURL(/\/connexion$/);
  await connecter(page, { courriel: SUPERADMIN_ESSAI.courriel, motDePasse: nouveau });
  await page.goto("/admin/compte");
  await expect(titre(page, T.monCompte)).toBeVisible();
  await expect(page.getByLabel(TA.nomAffiche, { exact: true })).toHaveValue("Chef Renommé");
  // L'aperçu de la photo est une adresse blob: du navigateur lui-même, jamais une requête hors de la console.
  expect(ailleurs.filter((url) => !url.startsWith(`blob:${baseURL}/`))).toEqual([]);
  await chef.close();
});
