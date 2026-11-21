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

/**
 * Le courriel d'alerte mis en forme, sur le modèle des notifications de l'ERP de MEGGA : un fond gris clair, une carte
 * blanche de 590 pixels, le sujet en titre (il ouvre les alertes de la console), un filet, le texte, un filet et la
 * signature. Des tableaux et des styles en ligne : ce que lisent toutes les messageries. Le texte brut part à côté.
 */
export function courrielHtml(sujet, texte) {
  const lignes = texte.split("\n").filter((l) => l.trim())
    .map((l) => `<p style="margin: 0 0 12px 0; font-size: 14px; line-height: 21px;">${echapper(l)}</p>`).join("");
  const filet = (marge) =>
    `<hr width="100%" style="background-color: #CCCCCC; border: none; display: block; font-size: 0; min-height: 1px; line-height: 0; margin: ${marge};"/>`;
  return `<!doctype html><html lang="fr"><head><meta http-equiv="Content-Type" content="text/html; charset=UTF-8"/></head><body style="margin: 0;">
<table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="padding-top: 16px; background-color: #F1F1F1; font-family: Verdana, Arial, sans-serif; color: #454748; border-collapse: separate;"><tr><td align="center">
<table role="presentation" border="0" cellpadding="0" cellspacing="0" width="590" style="max-width: 590px; padding: 24px; background-color: #FFFFFF; color: #454748; border-collapse: separate;">
<tr><td>
<span style="font-size: 10px;">Alerte de la console</span><br/>
<a href="${CONSOLE_ALERTES}" style="color: #454748; text-decoration: none;"><span style="font-size: 20px; font-weight: bold;">${echapper(sujet)}</span></a>
${filet("4px 0 32px 0")}
</td></tr>
<tr><td>${lignes}</td></tr>
<tr><td align="center" style="font-size: 11px;">
${filet("16px 0 4px 0")}
<b>MEGGA</b><br/>
<a href="${CONSOLE_ALERTES}" style="color: #999999; text-decoration: none;">console.megga.ai</a>
</td></tr>
</table>
</td></tr><tr><td style="height: 16px;"></td></tr></table>
</body></html>`;
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
    await env.COURRIEL.send({ to: corps.a, from: { email: env.COURRIEL_DE, name: "MEGGA" }, subject: corps.sujet, text: corps.texte,
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
