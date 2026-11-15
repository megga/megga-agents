"""Le serveur d'un agent : une image, un client par conteneur.

Variables d'environnement (jamais dans le dépôt) :
  CLIENT_CONFIG        la configuration du client, en JSON (ou CLIENT_CONFIG_FILE, un chemin)
  DATABASE_URL         la base du client (noyau/stockage.py)
  META_TOKEN           le jeton de l'app Meta, pour répondre
  META_APP_SECRET      la clé secrète de l'app Meta, pour vérifier la signature
  ANTHROPIC_API_KEY    Claude
  DEEPSEEK_API_KEY     le modèle de secours
  ELEVENLABS_API_KEY   facultatif : écouter les vocaux et répondre de vive voix
  JWT_VERIFICATION_KEY facultatif : ouvre l'API d'AgentOS, protégée par jeton (console, mode 2)
  INTERNE_TOKEN        le jeton des routes internes (posé par la porte, propre à chaque client)

Routes :
  GET  /sante     l'état du conteneur, sans rien de privé
  POST /whatsapp  un webhook de Meta, transmis tel quel (corps et signature)
  POST /interne/rappels  envoie les rappels échus, rend l'heure du prochain (jeton INTERNE_TOKEN)
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import time
from collections import OrderedDict

from fastapi import FastAPI, Request, Response

from . import config as configuration
from . import stockage
from .agent import construire, modele
from .oral import consignes as consignes_orales
from .rappels import outils as outils_rappels
from .tour import EXCUSE, Conversations, en_echec  # noqa: F401 (EXCUSE et en_echec réexportés)
from .voix import Voie
from .whatsapp import Expediteur, lire_entrants, signature_valide

log = logging.getLogger("megga")
CLES = ("ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY")


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


def outils_du_client(conf, rappels) -> list:
    """Les outils du noyau (rappels) et ceux des packs que la configuration active."""
    liste = outils_rappels(rappels, conf.fuseau)
    if "immobilier" in conf.outils:
        from packs.immobilier import Catalogue, outils as outils_immobilier

        if not conf.catalogue:
            raise RuntimeError("pack immobilier sans catalogue")
        liste += outils_immobilier(Catalogue(conf.catalogue))
    return liste


def _reecriture(conf, cles):
    """Le modèle qui réécrit une réponse pour l'oral : un agent sans mémoire ni outils."""
    from agno.agent import Agent

    nom = conf.modeles.oral or conf.modeles.secours or conf.modeles.principal
    oral = Agent(model=modele(nom, cles), instructions=consignes_orales(conf), telemetry=False, markdown=False)

    async def reecrire(demande: str) -> str:
        sortie = await oral.arun(demande)
        if en_echec(sortie):
            raise RuntimeError("réécriture en échec")
        return getattr(sortie, "content", "") or ""

    return reecrire


def creer(env: dict[str, str] | None = None, agent=None, expediteur=None, voie=None, contacts=None,
          reecrire=None, attente: float = 2.5, seuil_regard: float = 8.0, rappels=None) -> FastAPI:
    """Les arguments nommés remplacent les vrais services (essais)."""
    env = dict(os.environ if env is None else env)
    os.environ.setdefault("AGNO_TELEMETRY", "false")
    source = env.get("CLIENT_CONFIG") or env.get("CLIENT_CONFIG_FILE")
    if not source:
        raise RuntimeError("CLIENT_CONFIG manquante")
    conf = configuration.lire(source)
    cles = {k: env.get(k, "") for k in CLES}
    if agent is None:
        if not env.get("DATABASE_URL"):
            raise RuntimeError("DATABASE_URL manquante")
        rappels = rappels or stockage.Rappels(env["DATABASE_URL"])
        agent = construire(conf, stockage.base_agno(env["DATABASE_URL"]), cles, outils=outils_du_client(conf, rappels))
        contacts = contacts or stockage.Contacts(env["DATABASE_URL"])
        reecrire = reecrire or _reecriture(conf, cles)
    if expediteur is None:
        expediteur = Expediteur(env.get("META_TOKEN", ""), conf.whatsapp.numero_id, conf.whatsapp.version_graph)
    if voie is None and env.get("ELEVENLABS_API_KEY"):
        voie = Voie(env["ELEVENLABS_API_KEY"], conf.voix)
    conversations = Conversations(conf, agent, expediteur, voie, contacts, reecrire, attente, seuil_regard, rappels=rappels)
    jeton_interne = env.get("INTERNE_TOKEN", "")
    secret = env.get("META_APP_SECRET")
    deja = Deja()

    app = FastAPI(title=f"megga-agents {conf.id}", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.config = conf
    app.state.conversations = conversations
    app.state.taches = conversations.taches

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
            conversations.recevoir(m)
            lus += 1
        # Meta veut une réponse rapide : le tour se poursuit après.
        return Response(f"reçu {lus}", media_type="text/plain")

    @app.post("/interne/rappels")
    async def interne_rappels(requete: Request):
        jeton = requete.headers.get("x-megga-interne", "")
        if not jeton_interne or not hmac.compare_digest(jeton, jeton_interne):
            return Response("refusé", status_code=401)
        return await conversations.envoyer_rappels_echus(time.time())

    if env.get("JWT_VERIFICATION_KEY"):
        from agno.os import AgentOS

        os.environ.setdefault("JWT_VERIFICATION_KEY", env["JWT_VERIFICATION_KEY"])
        return AgentOS(agents=[agent], base_app=app, authorization=True, telemetry=False).get_app()
    return app


def principal() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    uvicorn.run(creer(), host="0.0.0.0", port=int(os.environ.get("PORT", "8080")), access_log=False)
