// Chargé avant chaque fichier de test : « cloudflare:workers » devient une classe vide.
import { registerHooks } from "node:module";

const WORKERS = "data:text/javascript,export class DurableObject { constructor(ctx, env) { this.ctx = ctx; this.env = env; } }";

registerHooks({
  resolve: (specifier, context, suivant) =>
    specifier === "cloudflare:workers" ? { url: WORKERS, shortCircuit: true } : suivant(specifier, context),
});
