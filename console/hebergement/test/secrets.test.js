// secrets.sh, avec un faux npx : il note les commandes de wrangler et ce que chaque « secret put » reçoit sur son entrée.
// Aucun appel à Cloudflare. Ce que le script affiche ne doit jamais contenir une valeur de secret.
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { chmodSync, existsSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

const SCRIPT = new URL("../secrets.sh", import.meta.url).pathname;
const BASE = "postgres://console:mot-de-passe-de-la-base@ep-essai.eu-central-1.aws.neon.tech/console?sslmode=require";
const JETON = "jeton-atelier-de-l-essai";

const FAUX_NPX = `#!/usr/bin/env bash
[ "$1" = wrangler ] || exit 9
shift
echo "$*" >> "$DOSSIER/journal"
case "$1 $2" in
  "secret list") [ -n "\${LISTE_EN_PANNE-}" ] && exit 1; printf '%s' "\${EXISTANTS:-[]}" ;;
  "secret put") cat > "$DOSSIER/put-$3"; echo "Success! Uploaded secret $3" ;;
  *) exit 8 ;;
esac
`;

function lancer({ args = [], env = {}, entree = "", trace = false } = {}) {
  const dossier = mkdtempSync(join(tmpdir(), "secrets-console-"));
  writeFileSync(join(dossier, "npx"), FAUX_NPX);
  chmodSync(join(dossier, "npx"), 0o755);
  const r = spawnSync("bash", [...(trace ? ["-x"] : []), SCRIPT, ...args], {
    input: entree,
    encoding: "utf8",
    env: { PATH: `${dossier}:${process.env.PATH}`, HOME: dossier, DOSSIER: dossier, ...env },
  });
  const poses = Object.fromEntries(readdirSync(dossier).filter((f) => f.startsWith("put-")).map((f) => [f.slice(4), readFileSync(join(dossier, f), "utf8")]));
  const journal = existsSync(join(dossier, "journal")) ? readFileSync(join(dossier, "journal"), "utf8") : "";
  rmSync(dossier, { recursive: true, force: true });
  return { statut: r.status, sortie: r.stdout + r.stderr, poses, journal };
}

/** Rien de ce qui a été posé ne paraît à l'écran. */
function rienAffiche(r) {
  for (const [nom, valeur] of Object.entries(r.poses)) assert.ok(!r.sortie.includes(valeur), `${nom} affiché`);
  assert.ok(!r.sortie.includes(BASE) && !r.sortie.includes("mot-de-passe") && !r.sortie.includes(JETON));
}

test("pose un BETTER_AUTH_SECRET tiré au hasard, et les secrets repris de l'environnement", () => {
  const r = lancer({ env: { CONSOLE_BASE_URL: BASE, ATELIER_JETON: JETON } });
  assert.equal(r.statut, 0, r.sortie);
  assert.match(r.poses.BETTER_AUTH_SECRET, /^[A-Za-z0-9+/]{43}=$/); // 32 octets en base64, sans retour à la ligne
  assert.equal(r.poses.CONSOLE_BASE_URL, BASE);
  assert.equal(r.poses.ATELIER_JETON, JETON);
  assert.match(r.sortie, /CONSOLE_BASE_URL repris de l'environnement et posé/);
  assert.ok(!r.journal.includes(BASE) && !r.journal.includes(JETON)); // jamais en argument de commande
  rienAffiche(r);
});

test("un champ vide passe son tour", () => {
  const r = lancer({ env: { CONSOLE_BASE_URL: BASE } });
  assert.equal(r.statut, 0, r.sortie);
  assert.deepEqual(Object.keys(r.poses).sort(), ["BETTER_AUTH_SECRET", "CONSOLE_BASE_URL"]);
  assert.match(r.sortie, /ATELIER_JETON : rien posé, passé/);
});

test("lit les valeurs sur son entrée, une ligne chacune, sans les afficher", () => {
  const r = lancer({ entree: `${BASE}\n` });
  assert.equal(r.statut, 0, r.sortie);
  assert.equal(r.poses.CONSOLE_BASE_URL, BASE);
  assert.equal(r.poses.ATELIER_JETON, undefined);
  rienAffiche(r);
});

test("garde le BETTER_AUTH_SECRET déjà posé, sauf avec --nouveau-secret", () => {
  const EXISTANTS = JSON.stringify([{ name: "BETTER_AUTH_SECRET", type: "secret_text" }]);
  const garde = lancer({ env: { EXISTANTS, CONSOLE_BASE_URL: BASE } });
  assert.equal(garde.statut, 0, garde.sortie);
  assert.equal(garde.poses.BETTER_AUTH_SECRET, undefined);
  assert.match(garde.sortie, /déjà posé : gardé/);
  const remplace = lancer({ args: ["--nouveau-secret"], env: { EXISTANTS } });
  assert.equal(remplace.statut, 0, remplace.sortie);
  assert.match(remplace.poses.BETTER_AUTH_SECRET, /^[A-Za-z0-9+/]{43}=$/);
});

test("s'arrête sans rien poser s'il ne lit pas les secrets du Worker", () => {
  const r = lancer({ env: { LISTE_EN_PANNE: "1", CONSOLE_BASE_URL: BASE } });
  assert.equal(r.statut, 1);
  assert.deepEqual(r.poses, {});
  assert.match(r.sortie, /déployez-le d'abord/);
});

test("refuse un argument inconnu", () => {
  const r = lancer({ args: ["--autre"] });
  assert.equal(r.statut, 2);
  assert.equal(r.journal, "");
});

test("même lancé avec bash -x, aucune valeur ne s'affiche", () => {
  const r = lancer({ trace: true, env: { CONSOLE_BASE_URL: BASE, ATELIER_JETON: JETON } });
  assert.equal(r.statut, 0, r.sortie);
  assert.equal(Object.keys(r.poses).length, 3);
  rienAffiche(r);
});
