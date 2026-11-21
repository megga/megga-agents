"""L'agent d'un client, construit d'après sa configuration.

Claude d'abord ; si Claude échoue (panne, délai, refus), le modèle de secours
reprend le tour (FallbackConfig d'Agno). La mémoire est rangée par personne
(user_id = son numéro), l'historique par conversation (session_id).
"""

from __future__ import annotations

from agno.agent import Agent
from agno.models.base import Model
from agno.models.fallback import FallbackConfig

from .config import Config, Role
from .garde import crochet_secrets
from .typographie import crochet_typographie

REGLES = (
    "Tu réponds sur WhatsApp : des messages courts et clairs, sans tableaux ni titres Markdown (#) ; le gras s'écrit avec une seule étoile.",
    "N'utilise jamais de tiret long ni de point médian.",
    "N'invente rien : ni chiffre, ni nom, ni fait. Si tu ne sais pas, dis-le simplement.",
    "Ne demande et ne répète jamais de mot de passe, de clé ou de code.",
    "Réponds dans la langue de la personne.",
    "Mémoire : ne retiens que ce que la personne te dit ou te confirme, jamais un mot de passe, une clé, un code ni une donnée bancaire. Si elle te demande d'oublier quelque chose, oublie-le.",
    "Rappels : seulement quand la personne le demande. Jamais de message spontané. Donne l'heure au format AAAA-MM-JJTHH:MM, à l'heure locale.",
)

# Le marqueur de cache d'Anthropic (5 minutes) : modele().
CACHE = {"type": "ephemeral"}

TOOL_CALL_LIMIT = 25  # appels d'outils par tour, au plus (relecture du 16.11.2026, I7)


def modele(nom: str, cles: dict[str, str], jetons: int = 4096, reflexion: bool = False, effort: str | None = None,
           temperature: float | None = None, cache: bool = False) -> Model:
    """Un modèle d'après son nom : « claude-… » chez Anthropic, « deepseek-… » chez DeepSeek. Pour Claude : `jetons` par
    réponse, la réflexion adaptative et son effort (Modeles.jetons, reflexion, effort ; parité D8). `temperature` : celle
    de la réécriture pour l'oral (Modeles.temperature_oral) ; jamais avec la réflexion, que Claude refuse. `cache` : seulement
    pour l'agent principal, dont un tour fait plusieurs appels ; un appel unique (l'oral, le fil, le juge) écrirait le cache
    sans jamais le relire, 25 % plus cher."""
    if nom.startswith("claude-"):
        from agno.models.anthropic import Claude

        # Le cache d'Anthropic (21.11.2026) : sans marque, rien n'est gardé, et chaque appel d'un tour renvoyait tout au prix
        # plein (Four Seasons : 2,4 millions de jetons d'entrée par jour, aucun lu en cache). Le marqueur automatique se pose
        # sur la fin de chaque requête : l'appel suivant du même tour (après un outil) relit tout ce début au dixième du prix.
        # Les outils ont leur propre marque, les consignes aussi : ni l'un ni l'autre ne change d'un tour à l'autre, puisque
        # l'heure et le Contexte passent dans le message du tour (construire). Le tour suivant relit donc les outils, les
        # consignes et l'historique tant que la fenêtre ne glisse pas ; quand elle glisse, les outils et les consignes.
        return Claude(id=nom, api_key=cles.get("ANTHROPIC_API_KEY"), max_tokens=jetons,
                      thinking={"type": "adaptive"} if reflexion else None,
                      output_config={"effort": effort} if effort else None,
                      temperature=None if reflexion else temperature,
                      cache_tools=cache, cache_system_prompt=cache,
                      request_params={"cache_control": CACHE} if cache else None)
    if nom.startswith("deepseek-"):
        from agno.models.deepseek import DeepSeek

        return DeepSeek(id=nom, api_key=cles.get("DEEPSEEK_API_KEY"), temperature=temperature)
    raise ValueError(f"modèle inconnu : {nom}")


def memoire_du_role(config: Config, role: Role | None = None) -> bool:
    """La mémoire par ses outils (retenir, oublier, souvenirs) : sans rôles, pour tous ; avec des rôles, pour ceux qui ont
    le groupe « memoire » seulement (dans l'ancienne Alix, Greg et Julien, jamais un partenaire ni un visiteur)."""
    return bool(config.memoire.outils) and (role is None or "memoire" in role.outils)


def consignes(config: Config, role: Role | None = None) -> list[str]:
    base = [
        f"Tu es {config.nom_agent}, et tu travailles pour {config.entreprise}.",
        f"Ton ton : {config.ton}. Langue par défaut : {config.langue}.",
        *REGLES,
    ]
    if config.consignes.strip():
        base.append(config.consignes.strip())
    if role is not None and role.consignes.strip():  # ce qui vaut pour les personnes de ce rôle (noyau/roles.py)
        base.append(role.consignes.strip())
    if memoire_du_role(config, role):  # la mémoire par ses outils (noyau/memoire.py)
        from .memoire import CONSIGNES as CONSIGNES_MEMOIRE

        base.append(CONSIGNES_MEMOIRE)
    if role is not None and set(role.outils) - {"rappels", "memoire", "immobilier"}:  # la façon de se servir des outils du pack
        from packs.immobilier.relations import consignes_des_groupes

        base += consignes_des_groupes(role.outils, config, role)
    return base


def heure(fuseau: str | None) -> str:
    """L'heure du tour, à la façon d'Agno (add_datetime_to_context), dans le fuseau du client."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    try:
        tz = ZoneInfo(fuseau) if fuseau else None
    except Exception:
        tz = None
    return f"The current time is {datetime.now(tz) if tz else datetime.now()}."


def contexte_du_tour(fuseau: str | None, contexte=None):
    """Ce qui change à chaque tour : l'heure, et le Contexte (`contexte` : async f(personne) -> texte) lu pour la personne
    qui parle (ses demandes en cours, les questions ouvertes). Il part dans le message du tour, pas dans les consignes :
    les consignes restent les mêmes d'un tour à l'autre, et le cache d'Anthropic les relit avec l'historique au dixième du
    prix (21.11.2026). L'historique garde chaque message avec son Contexte d'alors : il ne bouge plus, il se relit aussi.
    Une panne du Contexte n'arrête pas le tour."""

    async def tour(run_context=None) -> str:
        lignes = [heure(fuseau)]
        personne = getattr(run_context, "user_id", None)
        if contexte is not None and personne:
            try:
                extra = await contexte(personne)
            except Exception as e:
                import logging

                logging.getLogger("megga").warning("contexte illisible : %s", str(e)[:200])
                extra = ""
            if extra:
                lignes.append(extra)
        return "\n\n".join(lignes)

    tour.contexte = contexte  # le Contexte branché, lisible sans tour (essais)
    return tour


def construire(config: Config, db, cles: dict[str, str], principal: Model | None = None, secours: Model | None = None,
               outils: list | None = None, role: Role | None = None, nom_role: str | None = None, contexte=None) -> Agent:
    """`principal` et `secours` remplacent les modèles de la configuration (essais) ; `outils` : ceux du noyau et des packs ;
    `contexte` : le Contexte de chaque tour (contexte_du_tour)."""
    m = config.modeles
    principal = principal or modele(m.principal, cles, m.jetons, m.reflexion, m.effort, cache=True)
    if secours is None and config.modeles.secours:
        secours = modele(config.modeles.secours, cles)
    return Agent(
        id=f"{config.id}-{nom_role}" if nom_role else config.id,
        name=config.nom_agent,
        model=principal,
        fallback_config=FallbackConfig(on_error=[secours]) if secours else None,
        db=db,
        instructions=consignes(config, role),
        # L'heure et le Contexte, à la fin du message du tour (« additional context ») : contexte_du_tour.
        dependencies={"tour": contexte_du_tour(config.fuseau, contexte)},
        add_dependencies_to_context=True,
        add_history_to_context=True,
        num_history_runs=config.historique.tours,
        # La mémoire par l'agent lui-même (outil d'Agno), pour ne retenir que ce qui est dit ou confirmé ; ou par les outils
        # du noyau (Memoire.outils), ses souvenirs utiles dans le Contexte de chaque tour.
        enable_agentic_memory=not config.memoire.outils,
        add_memories_to_context=not config.memoire.outils,
        tools=list(outils or []),
        # Un tour n'appelle pas plus d'outils que cela : une boucle (ou une consigne glissée) ne fait pas exploser la facture.
        tool_call_limit=TOOL_CALL_LIMIT,
        timezone_identifier=config.fuseau,
        post_hooks=[crochet_secrets, crochet_typographie],
        markdown=False,
        telemetry=False,
        # Les photos reçues sont montrées au modèle, jamais gardées dans l'historique (la base).
        store_media=False,
    )
