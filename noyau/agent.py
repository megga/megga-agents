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

TOOL_CALL_LIMIT = 25  # appels d'outils par tour, au plus (relecture du 16.11.2026, I7)


def modele(nom: str, cles: dict[str, str], jetons: int = 4096, reflexion: bool = False, effort: str | None = None) -> Model:
    """Un modèle d'après son nom : « claude-… » chez Anthropic, « deepseek-… » chez DeepSeek. Pour Claude : `jetons` par
    réponse, la réflexion adaptative et son effort (Modeles.jetons, reflexion, effort ; parité D8)."""
    if nom.startswith("claude-"):
        from agno.models.anthropic import Claude

        return Claude(id=nom, api_key=cles.get("ANTHROPIC_API_KEY"), max_tokens=jetons,
                      thinking={"type": "adaptive"} if reflexion else None,
                      output_config={"effort": effort} if effort else None)
    if nom.startswith("deepseek-"):
        from agno.models.deepseek import DeepSeek

        return DeepSeek(id=nom, api_key=cles.get("DEEPSEEK_API_KEY"))
    raise ValueError(f"modèle inconnu : {nom}")


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
    if config.memoire.outils:  # la mémoire par ses outils (noyau/memoire.py)
        from .memoire import CONSIGNES as CONSIGNES_MEMOIRE

        base.append(CONSIGNES_MEMOIRE)
    if role is not None and set(role.outils) - {"rappels", "immobilier"}:  # la façon de se servir des outils du pack
        from packs.immobilier.relations import consignes_des_groupes

        base += consignes_des_groupes(role.outils, config, role)
    return base


def instructions_du_tour(base: list[str], contexte):
    """Les consignes, et le Contexte du tour (`contexte` : async f(personne) -> texte) lu à chaque tour pour la
    personne qui parle : ses demandes en cours, les questions ouvertes. Une panne du Contexte n'arrête pas le tour."""
    if contexte is None:
        return base

    async def instructions(run_context=None) -> list[str]:
        personne = getattr(run_context, "user_id", None)
        try:
            extra = await contexte(personne) if personne else ""
        except Exception as e:
            import logging

            logging.getLogger("megga").warning("contexte illisible : %s", str(e)[:200])
            extra = ""
        return [*base, extra] if extra else list(base)

    instructions.base = base  # les consignes fixes, lisibles sans tour (essais, atelier)
    return instructions


def construire(config: Config, db, cles: dict[str, str], principal: Model | None = None, secours: Model | None = None,
               outils: list | None = None, role: Role | None = None, nom_role: str | None = None, contexte=None) -> Agent:
    """`principal` et `secours` remplacent les modèles de la configuration (essais) ; `outils` : ceux du noyau et des packs ;
    `contexte` : le Contexte de chaque tour (instructions_du_tour)."""
    m = config.modeles
    principal = principal or modele(m.principal, cles, m.jetons, m.reflexion, m.effort)
    if secours is None and config.modeles.secours:
        secours = modele(config.modeles.secours, cles)
    return Agent(
        id=f"{config.id}-{nom_role}" if nom_role else config.id,
        name=config.nom_agent,
        model=principal,
        fallback_config=FallbackConfig(on_error=[secours]) if secours else None,
        db=db,
        instructions=instructions_du_tour(consignes(config, role), contexte),
        add_history_to_context=True,
        num_history_runs=config.historique.tours,
        # La mémoire par l'agent lui-même (outil d'Agno), pour ne retenir que ce qui est dit ou confirmé ; ou par les outils
        # du noyau (Memoire.outils), ses souvenirs utiles dans le Contexte de chaque tour.
        enable_agentic_memory=not config.memoire.outils,
        add_memories_to_context=not config.memoire.outils,
        tools=list(outils or []),
        # Un tour n'appelle pas plus d'outils que cela : une boucle (ou une consigne glissée) ne fait pas exploser la facture.
        tool_call_limit=TOOL_CALL_LIMIT,
        add_datetime_to_context=True,
        timezone_identifier=config.fuseau,
        post_hooks=[crochet_secrets, crochet_typographie],
        markdown=False,
        telemetry=False,
        # Les photos reçues sont montrées au modèle, jamais gardées dans l'historique (la base).
        store_media=False,
    )
