"""Le mode d'essai : l'agent d'une version répond, sans être branché au numéro du client.

Même construction qu'en service (noyau/agent.py, outils du noyau et des packs), mais
dans une base d'essai à part : rien ne touche la base ni les contacts du client, et
aucun message ne part sur WhatsApp. Les rappels demandés s'enregistrent dans la base
d'essai et ne partent jamais. Chaque version et chaque conversation d'essai est une
personne neuve : l'agent ne se souvient pas des essais d'avant.
"""

from __future__ import annotations

from pathlib import Path

from noyau import stockage
from noyau.agent import construire
from noyau.app import outils_du_client
from noyau.config import Config
from noyau.tour import EXCUSE, en_echec


def role_d_essai(conf: Config, role: str | None) -> str | None:
    """Le rôle qu'on essaie : celui demandé, sinon le visiteur (la personne que l'agent rencontre le plus), sinon le
    premier ; aucun pour une configuration sans rôles."""
    roles = conf.les_roles()
    if not roles:
        return None
    if role is not None:
        if role not in roles:
            raise ValueError(f"rôle : {', '.join(roles)}")
        return role
    return "visiteur" if "visiteur" in roles else next(iter(roles))


async def essayer(conf: Config, version: int, message: str, conversation: str, cles: dict[str, str],
                  dossier: Path, principal=None, role: str | None = None) -> str:
    """La réponse de l'agent de cette version ; `principal` remplace le modèle (essais du code). Avec des rôles,
    l'agent de ce rôle : ses consignes ; ses outils du pack, eux, demandent la gestion du site du client, que l'atelier
    n'a pas (relecture du 16.11.2026)."""
    dossier.mkdir(parents=True, exist_ok=True)
    url = f"sqlite:///{dossier / conf.id}.db"
    nom_role = role_d_essai(conf, role)
    r = conf.les_roles().get(nom_role) if nom_role else None
    groupes = tuple(g for g in r.outils if g in ("rappels", "memoire")) if r is not None else None
    agent = construire(conf, stockage.base_agno(url), cles, principal=principal, role=r, nom_role=nom_role,
                       outils=outils_du_client(conf, stockage.Rappels(url), groupes))
    personne = f"essai-v{version}-{nom_role + '-' if nom_role else ''}{conversation}"
    sortie = await agent.arun(message, user_id=personne, session_id=personne)
    if en_echec(sortie):
        return EXCUSE
    return getattr(sortie, "content", None) or ""
