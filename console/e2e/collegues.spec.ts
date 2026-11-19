import { expect, test } from "@playwright/test";

// Deux agents d'un même compte : Alix pose une question à Léa, et le fil le montre en une ligne qui se déplie.
test("Alix a demandé à Léa", async ({ page }) => {
  await page.goto("/connexion");
  await page.getByRole("button", { name: "Créer un compte" }).click();
  await page.getByLabel("Nom de votre entreprise").fill("Agence des Essais");
  await page.getByLabel("Courriel").fill(`collegues-${Date.now()}@essai.megga.ch`);
  await page.getByLabel("Mot de passe").fill("motdepasse-des-essais");
  await page.getByRole("button", { name: "Créer mon compte" }).click();
  await expect(page).toHaveURL(/\/$/);

  for (const [prenom, metier] of [["Léa", "Fiduciaire"], ["Alix", "Immobilier"]]) {
    await page.getByRole("button", { name: /Créer un agent|Nouvel agent/ }).first().click();
    await page.getByLabel("Prénom de l'agent").fill(prenom);
    await page.getByRole("button", { name: "Métier" }).click();
    await page.getByRole("button", { name: metier, exact: true }).click();
    await page.getByRole("button", { name: "Créer", exact: true }).click();
    await expect(page.getByLabel(`Écrivez à ${prenom}`)).toBeVisible();
  }

  const saisie = page.getByLabel("Écrivez à Alix");
  await saisie.fill("ESSAI-COLLEGUE Le dossier Martin est-il complet ?");
  await saisie.press("Enter");
  const fil = page.getByTestId("fil");
  const echange = fil.getByTestId("echange");
  await expect(echange.locator("summary")).toHaveText("Alix a demandé à Léa");
  await expect(echange.getByText("«\u00a0Le dossier Martin est-il complet ?\u00a0»")).toBeHidden(); // replié
  await expect(fil.getByText("Voici ce que mon collègue m'a répondu.")).toBeVisible();
  await page.screenshot({ path: "captures/echange-replie.png" });

  await echange.locator("summary").click();
  await expect(echange.getByText("« Le dossier Martin est-il complet ? »")).toBeVisible();
  await expect(echange.getByText(/^Bien reçu.*Le dossier Martin est-il complet/)).toBeVisible();
  await page.screenshot({ path: "captures/echange-deplie.png" });

  // La page Activité : l'échange en temps fort, qui se déplie, et ramène à la conversation
  await page.getByRole("button", { name: "Activité" }).click();
  const fort = page.getByTestId("temps-fort");
  await expect(fort).toHaveCount(1);
  // La conversation d'Alix, résumée en une phrase ; sa question à Léa en est une étape, pas une ligne de plus
  await expect(fort.getByRole("button").first()).toContainText("Alix a répondu à «\u00a0Le dossier Martin est-il complet ?\u00a0»");
  const chiffres = page.getByTestId("chiffres");
  // Une conversation (avec Alix) et sa réponse ; la question à Léa est un échange, pas une conversation de plus
  await expect(chiffres).toHaveText("1Conversations1Réponses1Questions entre agents");
  await page.screenshot({ path: "captures/activite.png" });
  await fort.getByRole("button").first().click();
  await expect(fort.getByText("A demandé à Léa")).toBeVisible();
  await expect(fort.getByText(/^Bien reçu.*Le dossier Martin est-il complet/)).toBeVisible();
  await page.screenshot({ path: "captures/activite-deplie.png" });
  await fort.getByRole("button", { name: "Continuer avec Alix" }).click();
  await expect(page.getByLabel("Écrivez à Alix")).toBeVisible();
});

test("sans échange, l'Activité montre une tête endormie", async ({ page }) => {
  await page.goto("/connexion");
  await page.getByRole("button", { name: "Créer un compte" }).click();
  await page.getByLabel("Nom de votre entreprise").fill("Agence Calme");
  await page.getByLabel("Courriel").fill(`calme-${Date.now()}@essai.megga.ch`);
  await page.getByLabel("Mot de passe").fill("motdepasse-des-essais");
  await page.getByRole("button", { name: "Créer mon compte" }).click();
  await page.getByRole("button", { name: "Créer un agent" }).click();
  await page.getByLabel("Prénom de l'agent").fill("Noé");
  await page.getByRole("button", { name: "Métier" }).click();
  await page.getByRole("button", { name: "Garage", exact: true }).click();
  await page.getByRole("button", { name: "Créer", exact: true }).click();
  await page.getByRole("button", { name: "Activité" }).click();
  await expect(page.getByRole("img", { name: "Aucune action" })).toBeVisible();
  await expect(page.getByTestId("temps-fort")).toHaveCount(0);
  await expect(page.getByTestId("chiffres")).toContainText("0Conversations");
  await page.screenshot({ path: "captures/activite-vide.png" });
});
