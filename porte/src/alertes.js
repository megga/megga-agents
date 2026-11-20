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
    await env.COURRIEL.send({ to: corps.a, from: { email: env.COURRIEL_DE, name: "MEGGA" }, subject: corps.sujet, text: corps.texte });
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
