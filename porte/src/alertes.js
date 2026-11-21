// Les alertes envoyées (20.11.2026). Toutes les 5 minutes, le déclencheur de la porte demande à l'atelier d'évaluer
// les règles (POST /atelier/alertes/evaluer) ; l'atelier envoie lui-même vers Slack et les adresses web, et confie les
// courriels à la porte (POST /admin/courriel), qui les envoie par Cloudflare Email Service (liaison COURRIEL).
// Un courriel ne porte que des chiffres et le nom d'une entreprise : jamais une conversation.

const ADRESSE = /^[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9-]{1,63}(\.[A-Za-z0-9-]{1,63})+$/;
const SUJET_MAX = 200;
const TEXTE_MAX = 4000;

/** Le corps d'un courriel d'alerte, vérifié : une adresse, un sujet d'une ligne, un texte borné. Rend null sinon. */
export function courrielValide(corps) {
  const { a, sujet, texte } = corps ?? {};
  if (typeof a !== "string" || !ADRESSE.test(a)) return null;
  if (typeof sujet !== "string" || !sujet.trim() || sujet.length > SUJET_MAX || /[\r\n]/.test(sujet)) return null;
  if (typeof texte !== "string" || !texte.trim() || texte.length > TEXTE_MAX) return null;
  return { a, sujet, texte };
}

const echapper = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const CONSOLE_ALERTES = "https://console.megga.ai/admin/alertes";
const IMAGES = "https://megga.ch/images/email/";
const POLICE = "'Inter Tight', Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif";
const TEXTE = "color:#c4c4cc;font-size:16px;line-height:1.6;";

/** La typographie française : une espace insécable devant : ; ! ? et à l'intérieur des guillemets. */
export const francais = (t) =>
  t.replace(/[ \u00a0]*([:;!?»])/g, "\u00a0$1").replace(/«[ \u00a0]*/g, "«\u00a0").replace(/^\u00a0/, "");

/**
 * Le courriel d'alerte au dessin des courriels de MEGGA (megga-erp, cloudflare/rendez-vous/src/lib/server/email/detail.ts) :
 * un bloc bleu foncé #03030f au centre d'une page blanche, tout aligné à gauche, le logo, le sujet en titre, le texte,
 * le bouton vers les alertes de la console, et en bas le dégradé du pied de page. Les images sont celles de megga.ch
 * (un courriel ne lit ni SVG ni dégradé CSS). Tableaux et styles en ligne ; les fonds passent aussi par bgcolor, que
 * certaines messageries lisent seul. Le texte brut part à côté.
 */
export function courrielHtml(sujet, texte) {
  const ligne = (padding, style, contenu) =>
    `<tr><td bgcolor="#03030f" style="background-color:#03030f;padding:${padding};font-family:${POLICE};${style}">${contenu}</td></tr>`;
  // Des textes harmonisés : le titre une fois (le texte ne le répète pas), puis une seule taille, un seul écart entre
  // les lignes, et l'espace insécable de la typographie française devant : ; ! ? et à l'intérieur des guillemets.
  const titre = francais(sujet.trim());
  const lignes = texte.split("\n").map((l) => francais(l.trim())).filter((l) => l && l.replace(/\.$/, "") !== titre)
    .map((l, i) => ligne(`${i ? 8 : 24}px 40px 0`, TEXTE, echapper(l))).join("\n");
  return `<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<title>${echapper(sujet)}</title>
</head>
<body bgcolor="#ffffff" style="margin:0;padding:0;background-color:#ffffff;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#ffffff" style="background-color:#ffffff;">
<tr><td align="center" style="padding:24px 12px;">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" bgcolor="#03030f" style="width:100%;max-width:600px;background-color:#03030f;border-radius:24px;overflow:hidden;">
${ligne("40px 40px 0", "", `<img src="${IMAGES}megga-logo-blanc.png" width="110" alt="MEGGA" style="display:block;width:110px;height:auto;border:0;">`)}
${ligne("40px 40px 0", "color:#ffffff;font-size:24px;line-height:1.25;font-weight:600;letter-spacing:-0.01em;", echapper(titre))}
${lignes}
<tr><td bgcolor="#03030f" style="background-color:#03030f;padding:28px 40px 0;"><table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr><td bgcolor="#ffffff" style="background-color:#ffffff;border-radius:999px;"><a href="${CONSOLE_ALERTES}" style="display:inline-block;padding:14px 28px;border-radius:999px;background-color:#ffffff;color:#03030f;font-family:${POLICE};font-size:16px;font-weight:600;line-height:1;text-decoration:none;">Voir les alertes</a></td></tr></table></td></tr>
<tr><td bgcolor="#03030f" style="background-color:#03030f;padding:32px 0 0;font-size:0;line-height:0;"><img src="${IMAGES}pied.jpg" width="600" alt="" style="display:block;width:100%;height:auto;border:0;"></td></tr>
</table>
</td></tr>
</table>
</body>
</html>`;
}

/** POST /admin/courriel (jeton ADMIN_TOKEN, vérifié par l'appelant). */
export async function envoyerCourriel(requete, env) {
  if (!env.COURRIEL || !env.COURRIEL_DE) return Response.json({ erreur: "envoi de courriel non réglé" }, { status: 503 });
  let corps;
  try {
    corps = courrielValide(await requete.json());
  } catch {
    corps = null;
  }
  if (!corps) return Response.json({ erreur: "courriel : a, sujet d'une ligne, texte de 4 000 caractères au plus" }, { status: 400 });
  try {
    await env.COURRIEL.send({ to: corps.a, from: { email: env.COURRIEL_DE, name: "MEGGA" }, subject: corps.sujet, text: corps.texte.split("\n").map(francais).join("\n"),
      html: courrielHtml(corps.sujet, corps.texte) });
    return Response.json({ envoye: true });
  } catch (e) {
    // Ni l'adresse ni le texte ne sont journalisés.
    console.error("courriel en échec :", String(e?.code ?? e?.name ?? "erreur").slice(0, 60));
    return Response.json({ erreur: "envoi refusé" }, { status: 502 });
  }
}

/** Le déclencheur : l'atelier évalue les règles. Un échec est journalisé, la prochaine passe réessaie. */
export async function evaluerAlertes(env, atelier) {
  if (!atelier || !env.ADMIN_TOKEN) return null;
  try {
    const r = await atelier.fetch(
      new Request("https://atelier/atelier/alertes/evaluer", { method: "POST", headers: { authorization: `Bearer ${env.ADMIN_TOKEN}` } }),
    );
    if (!r.ok) console.error("évaluation des alertes :", r.status);
    return r.status;
  } catch (e) {
    console.error("évaluation des alertes injoignable :", String(e?.message ?? e).slice(0, 120));
    return 0;
  }
}

/** Toutes les 5 minutes aussi, après les alertes : l'atelier prélève une recharge pour chaque client sous son seuil (Stripe). */
export async function evaluerRecharges(env, atelier) {
  if (!atelier || !env.ADMIN_TOKEN) return null;
  try {
    const r = await atelier.fetch(
      new Request("https://atelier/atelier/recharges/evaluer", { method: "POST", headers: { authorization: `Bearer ${env.ADMIN_TOKEN}` } }),
    );
    if (!r.ok) console.error("recharges :", r.status);
    return r.status;
  } catch (e) {
    console.error("recharges injoignables :", String(e?.message ?? e).slice(0, 120));
    return 0;
  }
}
