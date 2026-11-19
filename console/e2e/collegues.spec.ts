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
});
