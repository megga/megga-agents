// Les zones servies par Cloudflare, et la liaison de chacune. La zone suisse
// (Exoscale) et l'installation chez le client ont leur propre adresse de
// webhook : elles ne passent jamais par ici.

export const ZONES = {
  europe: { liaison: "AGENTS_EUROPE", juridiction: "eu" },
  "etats-unis": { liaison: "AGENTS_ETATS_UNIS", juridiction: "us" },
};

/** L'objet d'un client dans sa zone, ou null si la zone n'est pas servie ici. */
export function agentDe(env, client) {
  const z = ZONES[client?.zone];
  if (!z || !env[z.liaison]) return null;
  return env[z.liaison].jurisdiction(z.juridiction).getByName(client.id);
}
