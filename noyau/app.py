"""Le serveur d'un agent : une image, un client par conteneur.

Variables d'environnement (jamais dans le dépôt) :
  CLIENT_CONFIG        la configuration du client, en JSON (ou CLIENT_CONFIG_FILE, un chemin)
  DATABASE_URL         la base du client (noyau/stockage.py)
  META_TOKEN           le jeton de l'app Meta, pour répondre
  META_APP_SECRET      la clé secrète de l'app Meta, pour vérifier la signature
  ANTHROPIC_API_KEY    Claude
  DEEPSEEK_API_KEY     le modèle de secours
  JWT_VERIFICATION_KEY facultatif : ouvre l'API d'AgentOS, protégée par jeton (console, mode 2)

Routes :
  GET  /sante     l'état du conteneur, sans rien de privé
  POST /whatsapp  un webhook de Meta, transmis tel quel (corps et signature)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections import OrderedDict

from fastapi import FastAPI, Request, Response

from . import config as configuration
from . import stockage
from .agent import construire
from .typographie import nettoyer
from .whatsapp import Entrant, Expediteur, lire_entrants, signature_valide

log = logging.getLogger("megga")
CLES = ("ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY")
# Ce que reçoit la personne quand le tour échoue : jamais le texte d'une erreur technique.
EXCUSE = "Je rencontre un petit souci technique. Je reviens vers vous dès que possible."


def en_echec(sortie) -> bool:
    statut = getattr(sortie, "status", None)
    return str(getattr(statut, "value", statut) or "").upper() in {"ERROR", "CANCELLED"}


class Deja:
    """Les identifiants de messages déjà traités : Meta renvoie un webhook en cas de doute."""

    def __init__(self, taille: int = 2000):
        self._vus: OrderedDict[str, None] = OrderedDict()
        self._taille = taille

    def nouveau(self, ident: str) -> bool:
        if not ident:
            return True
        if ident in self._vus:
            return False
        self._vus[ident] = None
        if len(self._vus) > self._taille:
            self._vus.popitem(last=False)
        return True


def creer(env: dict[str, str] | None = None, agent=None, expediteur=None) -> FastAPI:
    """`agent` et `expediteur` remplacent les vrais (essais)."""
    env = dict(os.environ if env is None else env)
    os.environ.setdefault("AGNO_TELEMETRY", "false")
    source = env.get("CLIENT_CONFIG") or env.get("CLIENT_CONFIG_FILE")
    if not source:
        raise RuntimeError("CLIENT_CONFIG manquante")
    conf = configuration.lire(source)
    if agent is None:
        if not env.get("DATABASE_URL"):
            raise RuntimeError("DATABASE_URL manquante")
        agent = construire(conf, stockage.base_agno(env["DATABASE_URL"]), {k: env.get(k, "") for k in CLES})
    if expediteur is None:
        expediteur = Expediteur(env.get("META_TOKEN", ""), conf.whatsapp.numero_id, conf.whatsapp.version_graph)
    secret = env.get("META_APP_SECRET")
    deja = Deja()
    verrous: dict[str, asyncio.Lock] = {}
    taches: set[asyncio.Task] = set()

    async def repondre(m: Entrant) -> None:
        # Un tour à la fois par personne, dans l'ordre d'arrivée.
        async with verrous.setdefault(m.de, asyncio.Lock()):
            try:
                if not m.texte:
                    reponse = "Je ne lis que les messages écrits pour le moment."
                else:
                    sortie = await agent.arun(m.texte, user_id=m.de, session_id=m.de)
                    if en_echec(sortie):
                        log.error("tour en échec (%s)", conf.id)
                        reponse = EXCUSE
                    else:
                        reponse = getattr(sortie, "content", None) or ""
                if reponse.strip():
                    await expediteur.texte(m.de, nettoyer(reponse))
            except Exception as e:  # le tour échoue, le conteneur continue
                log.error("tour en échec (%s) : %s", conf.id, str(e)[:300])

    app = FastAPI(title=f"megga-agents {conf.id}", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.config = conf
    app.state.taches = taches

    @app.get("/sante")
    async def sante():
        return {"ok": True, "client": conf.id, "zone": conf.zone, "version": configuration.VERSION}

    @app.post("/whatsapp")
    async def whatsapp(requete: Request):
        corps = await requete.body()
        if not signature_valide(corps, requete.headers.get("x-hub-signature-256"), secret):
            return Response("signature", status_code=401)
        try:
            evenement = json.loads(corps)
        except ValueError:
            return Response("corps", status_code=400)
        lus = 0
        for m in lire_entrants(evenement, conf.whatsapp.numero_id):
            if not m.frais():
                log.warning("message ancien, sans réponse")
                continue
            if not deja.nouveau(m.id):
                continue
            t = asyncio.create_task(repondre(m))
            taches.add(t)
            t.add_done_callback(taches.discard)
            lus += 1
        # Meta veut une réponse rapide : le tour se poursuit après.
        return Response(f"reçu {lus}", media_type="text/plain")

    if env.get("JWT_VERIFICATION_KEY"):
        from agno.os import AgentOS

        os.environ.setdefault("JWT_VERIFICATION_KEY", env["JWT_VERIFICATION_KEY"])
        return AgentOS(agents=[agent], base_app=app, authorization=True, telemetry=False).get_app()
    return app


def principal() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    uvicorn.run(creer(), host="0.0.0.0", port=int(os.environ.get("PORT", "8080")), access_log=False)
