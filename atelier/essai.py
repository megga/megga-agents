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


async def essayer(conf: Config, version: int, message: str, conversation: str, cles: dict[str, str],
                  dossier: Path, principal=None) -> str:
    """La réponse de l'agent de cette version ; `principal` remplace le modèle (essais du code)."""
    dossier.mkdir(parents=True, exist_ok=True)
    url = f"sqlite:///{dossier / conf.id}.db"
    agent = construire(conf, stockage.base_agno(url), cles, principal=principal,
                       outils=outils_du_client(conf, stockage.Rappels(url)))
    personne = f"essai-v{version}-{conversation}"
    sortie = await agent.arun(message, user_id=personne, session_id=personne)
    if en_echec(sortie):
        return EXCUSE
    return getattr(sortie, "content", None) or ""
