"""Le mode d'essai : l'agent d'une version répond, sans être branché au numéro du client.

Même construction qu'en service (noyau/agent.py, outils du noyau et des packs), mais
dans une base d'essai à part : rien ne touche la base ni les contacts du client, et
aucun message ne part sur WhatsApp. Les rappels demandés s'enregistrent dans la base
d'essai et ne partent jamais. Chaque version et chaque conversation d'essai est une
personne neuve : l'agent ne se souvient pas des essais d'avant.
"""

from __future__ import annotations

from pathlib import Path

from noyau import flux, stockage
from noyau.agent import construire
from noyau.app import outils_du_client
from noyau.config import Config
from noyau.tour import EXCUSE, en_echec


async def essayer(conf: Config, version: int, message: str, conversation: str, cles: dict[str, str],
                  dossier: Path, principal=None, sur_evenement=None) -> str:
    """La réponse de l'agent de cette version ; `principal` remplace le modèle (essais du code).
    Avec `sur_evenement` (async f(genre, valeur)), la réponse part aussi au fil de l'eau (noyau/flux.py) : les
    morceaux de texte, masqués comme en service, et les outils ; la réponse rendue reste celle qui fait foi."""
    dossier.mkdir(parents=True, exist_ok=True)
    url = f"sqlite:///{dossier / conf.id}.db"
    agent = construire(conf, stockage.base_agno(url), cles, principal=principal,
                       outils=outils_du_client(conf, stockage.Rappels(url)))
    personne = f"essai-v{version}-{conversation}"
    if sur_evenement is None:
        sortie = await agent.arun(message, user_id=personne, session_id=personne)
    else:
        relais = flux.Relais(sur_evenement)
        sortie = await flux.suivre(agent.arun(message, user_id=personne, session_id=personne, stream=True,
                                              stream_events=True, yield_run_output=True), relais)
        await relais.finir()
    if en_echec(sortie):
        return EXCUSE
    return getattr(sortie, "content", None) or ""
