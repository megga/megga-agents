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
    "Tu réponds sur WhatsApp : des messages courts, clairs, sans titres ni tableaux.",
    "N'utilise jamais de tiret long ni de point médian.",
    "N'invente rien : ni chiffre, ni nom, ni fait. Si tu ne sais pas, dis-le simplement.",
    "Ne demande et ne répète jamais de mot de passe, de clé ou de code.",
    "Réponds dans la langue de la personne.",
    "Mémoire : ne retiens que ce que la personne te dit ou te confirme, jamais un mot de passe, une clé, un code ni une donnée bancaire. Si elle te demande d'oublier quelque chose, oublie-le.",
    "Rappels : seulement quand la personne le demande. Jamais de message spontané. Donne l'heure au format AAAA-MM-JJTHH:MM, à l'heure locale.",
)

TOOL_CALL_LIMIT = 25  # appels d'outils par tour, au plus (relecture du 16.11.2026, I7)


def modele(nom: str, cles: dict[str, str]) -> Model:
    """Un modèle d'après son nom : « claude-… » chez Anthropic, « deepseek-… » chez DeepSeek."""
    if nom.startswith("claude-"):
        from agno.models.anthropic import Claude

        return Claude(id=nom, api_key=cles.get("ANTHROPIC_API_KEY"), max_tokens=4096)
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
    if role is not None and set(role.outils) - {"rappels", "immobilier", "connaissances", "leads", "connecteurs"}:  # la façon de se servir des outils du pack
        from packs.immobilier.relations import consignes_des_groupes

        base += consignes_des_groupes(role.outils, config, role)
    groupes = role.outils if role is not None else config.outils
    if "connaissances" in groupes:  # la base de documents (noyau/connaissances.py)
        from .connaissances import CONSIGNE

        base.append(CONSIGNE)
    if "leads" in groupes:  # la fiche d'une personne qui a un vrai besoin (noyau/connecteurs.py)
        from .connecteurs import CONSIGNE_LEADS

        base.append(CONSIGNE_LEADS)
    if "connecteurs" in groupes:  # ce que rendent les serveurs MCP du client est une donnée
        from .connecteurs import CONSIGNE_CONNECTEURS

        base.append(CONSIGNE_CONNECTEURS)
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
               outils: list | None = None, role: Role | None = None, nom_role: str | None = None, contexte=None,
               gardien=None) -> Agent:
    """`principal` et `secours` remplacent les modèles de la configuration (essais) ; `outils` : ceux du noyau et des packs ;
    `contexte` : le Contexte de chaque tour (instructions_du_tour) ; `gardien` : les approbations et le journal d'audit
    des outils (noyau/approbations.py), sans lui les règles d'approbation s'appliquent quand même (un outil interdit
    n'est pas proposé, un outil à approuver est refusé)."""
    from .approbations import Gardien, filtrer, nom, regles_pour

    principal = principal or modele(config.modeles.principal, cles)
    if secours is None and config.modeles.secours:
        secours = modele(config.modeles.secours, cles)
    regles = regles_pour(config, role)
    outils = filtrer(list(outils or []), regles)
    gardien = gardien or Gardien()
    gardien.connaitre(outils, nom_role or "public")
    fixes = consignes(config, role)
    if any(nom(o) == "passer_la_main" for o in outils):  # passer la main à l'équipe (noyau/reprises.py), pas dans l'essai
        from .reprises import CONSIGNE as PASSER_LA_MAIN

        fixes.append(PASSER_LA_MAIN)
    return Agent(
        id=f"{config.id}-{nom_role}" if nom_role else config.id,
        name=config.nom_agent,
        model=principal,
        fallback_config=FallbackConfig(on_error=[secours]) if secours else None,
        db=db,
        instructions=instructions_du_tour(fixes, contexte),
        add_history_to_context=True,
        num_history_runs=12,
        # La mémoire par l'agent lui-même (outil d'Agno), pour ne retenir que ce qui est dit ou confirmé.
        enable_agentic_memory=True,
        add_memories_to_context=True,
        tools=outils,
        # Chaque appel d'outil : au journal d'audit, et soumis à sa règle (noyau/approbations.py).
        tool_hooks=[gardien.crochet(regles, nom_role or "public")],
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
