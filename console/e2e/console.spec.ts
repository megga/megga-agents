import { expect, test } from "@playwright/test";
import { COMPTE_ESSAI } from "./compte";

// Le parcours d'un client : inscription, création d'un agent, une question, sa réponse au fil de l'eau.
test("de l'inscription à la première réponse d'un agent", async ({ page }) => {
  // La page ne parle qu'à la console : ni télémétrie de CopilotKit, ni polices ou scripts d'ailleurs.
  const ailleurs: string[] = [];
  page.on("request", (r) => {
    const h = new URL(r.url()).hostname;
    if (!["localhost", "127.0.0.1"].includes(h) && !r.url().startsWith("data:")) ailleurs.push(r.url());
  });
  await page.goto("/");
  await expect(page).toHaveURL(/\/connexion$/);
  await expect(page.getByRole("heading", { name: "Connexion" })).toBeVisible();
  // Sans clés, ni Google ni Microsoft.
  await expect(page.getByText("Continuer avec Google")).toHaveCount(0);
  await expect(page.getByText("Continuer avec Microsoft")).toHaveCount(0);
  await page.screenshot({ path: "captures/connexion.png" });

  await page.getByRole("button", { name: "Créer un compte" }).click();
  await page.getByLabel("Nom de votre entreprise").fill(COMPTE_ESSAI.entreprise);
  await page.getByLabel("Courriel").fill(COMPTE_ESSAI.courriel);
  await page.getByLabel("Mot de passe").fill(COMPTE_ESSAI.motDePasse);
  await page.getByRole("button", { name: "Créer mon compte" }).click();
  await expect(page).toHaveURL(/\/$/);

  // Le Studio : sans métier, « Créer » ouvre les métiers.
  await page.getByRole("button", { name: "Créer un agent" }).click();
  await page.getByLabel("Prénom de l'agent").fill("Alix");
  await page.getByRole("button", { name: "Créer", exact: true }).click();
  const metiers = ["Généraliste", "Immobilier", "Santé", "Hôtellerie et restauration", "Juridique", "Commerce", "Fiduciaire", "Garage"];
  for (const m of metiers) await expect(page.getByRole("button", { name: m, exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Immobilier", exact: true }).click();
  await page.screenshot({ path: "captures/studio.png" });
  await page.getByRole("button", { name: "Créer", exact: true }).click();

  // En service tout de suite : on lui écrit.
  const saisie = page.getByLabel("Écrivez à Alix");
  await expect(saisie).toBeVisible();
  await expect(page.getByText("Bonjour, je suis Alix. Essayez-moi")).toBeVisible();
  await saisie.fill("Bonjour, je cherche un appartement de 3 pièces à Anglet.");
  await saisie.press("Enter");
  await expect(page.getByTestId("fil").getByText(/Bien reçu.*appartement de 3 pièces à Anglet/)).toBeVisible();

  // Un deuxième agent, épinglé.
  await page.getByRole("button", { name: "Nouvel agent" }).click();
  await page.getByLabel("Prénom de l'agent").fill("Léa");
  await page.getByRole("button", { name: "Couleur" }).click();
  await page.getByRole("button", { name: "Violet" }).click();
  await page.getByRole("button", { name: "Métier" }).click();
  await page.getByRole("button", { name: "Garage", exact: true }).click();
  await page.getByRole("button", { name: "Créer", exact: true }).click();
  await expect(page.getByLabel("Écrivez à Léa")).toBeVisible();
  const ligneAlix = page.getByRole("navigation", { name: "Vos agents" }).locator(".group").filter({ hasText: "Alix" });
  await ligneAlix.hover();
  await ligneAlix.getByRole("button", { name: "Épingler en haut" }).click();
  await expect(page.getByRole("status")).toHaveText("Alix est épinglé en haut");

  // Épinglé, Alix quitte la liste ; retour à Alix : son fil est toujours là.
  const rail = page.getByRole("navigation", { name: "Vos agents" });
  await expect(rail.getByRole("button", { name: /Alix/ })).toHaveCount(1);
  await rail.getByRole("button", { name: "Alix", exact: true }).click();
  await expect(page.getByTestId("fil").getByText(/Bien reçu.*Anglet/)).toBeVisible();
  // Il se souvient de la conversation, même après la création de Léa (CopilotKit a redémarré entre-temps).
  await page.getByLabel("Écrivez à Alix").fill("Avec un balcon, si possible.");
  await expect(page.getByRole("button", { name: "Envoyer" })).toBeEnabled();
  await page.getByLabel("Écrivez à Alix").press("Enter");
  await expect(page.getByTestId("fil").getByText(/Avec un balcon.*C'est votre 2e message\./)).toBeVisible();
  // Une panne du modèle se dit, sans rester muette.
  // La réponse s'affiche avant que l'agent ait fini son tour ; tant qu'il tourne, la console ignore l'envoi (fil.tsx).
  // Le bouton Envoyer, actif seulement quand l'agent est libre, dit quand le message part vraiment.
  await page.getByLabel("Écrivez à Alix").fill("ESSAI-PANNE");
  await expect(page.getByRole("button", { name: "Envoyer" })).toBeEnabled();
  await page.getByLabel("Écrivez à Alix").press("Enter");
  await expect(page.getByText("Pas de réponse pour l'instant. Réessayez dans un instant.")).toBeVisible();
  await page.mouse.move(900, 400);
  await page.waitForTimeout(2000);
  await page.screenshot({ path: "captures/console-clair.png" });

  await page.evaluate(() => {
    localStorage.setItem("theme", "sombre");
    (window as unknown as { __theme: () => void }).__theme();
  });
  await page.waitForTimeout(300);
  await page.screenshot({ path: "captures/console-sombre.png" });

  // Déconnexion, puis connexion.
  await page.getByRole("button", { name: "Compte et réglages" }).click();
  await page.getByRole("menuitem", { name: "Se déconnecter" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Se déconnecter", exact: true }).click(); // chaque geste se confirme
  await expect(page).toHaveURL(/\/connexion$/);
  await page.getByLabel("Courriel").fill(COMPTE_ESSAI.courriel);
  await page.getByLabel("Mot de passe").fill("pas-le-bon-mot");
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "Courriel" })).toHaveText("Courriel ou mot de passe incorrect.");
  await page.getByLabel("Mot de passe").fill(COMPTE_ESSAI.motDePasse);
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(page.getByRole("navigation", { name: "Vos agents" }).getByText("Léa", { exact: true })).toBeVisible();
  expect(ailleurs).toEqual([]);
});

test("sur téléphone, un agent épinglé reste dans la liste", async ({ page }) => {
  await page.goto("/connexion");
  await page.getByLabel("Courriel").fill(COMPTE_ESSAI.courriel);
  await page.getByLabel("Mot de passe").fill(COMPTE_ESSAI.motDePasse);
  await page.getByRole("button", { name: "Se connecter" }).click();
  const rail = page.getByRole("navigation", { name: "Vos agents" });
  await expect(rail.getByRole("button", { name: /Léa/ })).toHaveCount(1);
  await page.setViewportSize({ width: 390, height: 844 });
  // Alix est épinglé (premier essai) : ses tuiles sont masquées, sa ligne réapparaît, une seule fois.
  await expect(rail.getByRole("button", { name: /^Alix/ }).filter({ visible: true })).toHaveCount(1);
  await rail.getByRole("button", { name: /^Alix/ }).filter({ visible: true }).click();
  await expect(page.getByLabel("Écrivez à Alix")).toBeVisible();
  await page.screenshot({ path: "captures/telephone.png" });
});

test("les routes de la console refusent qui n'est pas connecté", async ({ request }) => {
  expect((await request.get("/api/agents")).status()).toBe(401);
  expect((await request.post("/api/agents", { data: { prenom: "X", metier: "garage" } })).status()).toBe(401);
  expect((await request.post("/api/copilotkit/info")).status()).toBe(401);
});
