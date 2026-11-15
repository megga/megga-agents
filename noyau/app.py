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
  MEGGA_INSTALLATION   « client » : installation chez le client (webhook direct, rappels sans porte,
                       licence exigée) ; sinon, derrière la porte de MEGGA
  META_VERIFY_TOKEN    chez le client : le jeton d'abonnement du webhook de Meta
  MEGGA_LICENCE        chez le client : la licence signée par MEGGA (noyau/licence.py)
Chaque secret peut aussi venir d'un fichier : <NOM>_FILE (noyau/environnement.py).

Chez le client, la configuration servie est la dernière poussée par MEGGA et acceptée (pilotage,
noyau/pilotage.py), revérifiée au démarrage, sinon CLIENT_CONFIG. Quand le pilote en note une autre,
l'agent finit ses tours et s'arrête : Compose ou Kubernetes le relancent, et il la relit.

Routes :
  GET  /sante     l'état du conteneur, sans rien de privé
  GET  /whatsapp  l'abonnement du webhook de Meta (chez le client ; chez MEGGA, la porte s'en charge)
  POST /whatsapp  un webhook de Meta, transmis tel quel (corps et signature)
  POST /interne/rappels  envoie les rappels échus, rend l'heure du prochain (jeton INTERNE_TOKEN)
  POST /interne/vider    attend la fin des tours en cours, avant un redémarrage (jeton INTERNE_TOKEN)
  GET  /interne/suivi[?depuis=]                 volumes, modèles, échecs (jeton INTERNE_TOKEN)
  GET  /interne/suivi/conversations[?limite=]   les personnes qui ont écrit
  GET  /interne/suivi/conversations/{personne}  ses derniers messages, reçus et envoyés
  GET  /interne/suivi/alertes[?depuis=]         les échecs récents
"""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import json
import logging
import os
import signal
import time
from collections import OrderedDict

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from . import config as configuration
from . import licence as licences
from . import pilotage as pilotages
from . import stockage
from . import suivi as suivi_agent
from . import version as version_image
from .agent import construire, modele
from .environnement import charger
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
          reecrire=None, attente: float = 2.5, seuil_regard: float = 8.0, rappels=None,
          delai_vider: float = 100.0, journal=None, lecture=None, fil=None, cle_licence=None, cle_pilotage=None,
          quitter=None) -> FastAPI:
    """Les arguments nommés remplacent les vrais services (essais) ; `cle_licence` et `cle_pilotage`, les clés
    publiques des licences et des ordres de MEGGA ; `quitter`, l'arrêt de l'agent pour relire sa configuration."""
    env = charger(dict(os.environ if env is None else env))
    os.environ.setdefault("AGNO_TELEMETRY", "false")
    source = env.get("CLIENT_CONFIG") or env.get("CLIENT_CONFIG_FILE")
    if not source:
        raise RuntimeError("CLIENT_CONFIG manquante")
    fichier = configuration.lire(source)
    chez_le_client = env.get("MEGGA_INSTALLATION") == "client"
    url = env.get("DATABASE_URL", "")
    if agent is None:
        if not url:
            raise RuntimeError("DATABASE_URL manquante")
        stockage.migrer(url)  # avant toute table : une base neuve se reconnaît à ce qu'elle n'en a aucune
    # Chez le client, la dernière configuration poussée par MEGGA et acceptée, revérifiée ; sinon son fichier.
    ordres = stockage.Ordres(url) if chez_le_client and url else None
    conf, pilotee, refus = fichier, None, None
    if ordres is not None:
        conf, pilotee, refus = pilotages.configuration_servie(fichier, ordres.a_servir(fichier.id), cle_pilotage)
        if refus:
            log.error("configuration poussée refusée (%s) : l'agent sert son fichier", refus)
    # Chez le client, pas de licence valide, pas de démarrage (vérifiée sans appel extérieur).
    licence = licences.verifier(env.get("MEGGA_LICENCE", ""), conf.id, cle=cle_licence) if chez_le_client else None
    cles = {k: env.get(k, "") for k in CLES}
    quitter = quitter or (lambda: os.kill(os.getpid(), signal.SIGTERM))
    if agent is None:
        rappels = rappels or stockage.Rappels(env["DATABASE_URL"])
        agent = construire(conf, stockage.base_agno(env["DATABASE_URL"]), cles, outils=outils_du_client(conf, rappels))
        contacts = contacts or stockage.Contacts(env["DATABASE_URL"])
        reecrire = reecrire or _reecriture(conf, cles)
    if env.get("DATABASE_URL"):
        journal = journal or stockage.Journal(env["DATABASE_URL"])
        lecture = lecture or stockage.Suivi(env["DATABASE_URL"])
        fil = fil or stockage.Fil(env["DATABASE_URL"])
    if expediteur is None:
        expediteur = Expediteur(env.get("META_TOKEN", ""), conf.whatsapp.numero_id, conf.whatsapp.version_graph)
    if voie is None and env.get("ELEVENLABS_API_KEY"):
        voie = Voie(env["ELEVENLABS_API_KEY"], conf.voix)
    conversations = Conversations(conf, agent, expediteur, voie, contacts, reecrire, attente, seuil_regard, rappels=rappels,
                                  journal=journal, fil=fil)
    jeton_interne = env.get("INTERNE_TOKEN", "")
    secret = env.get("META_APP_SECRET")
    deja = Deja()

    def licence_echue() -> bool:
        """Au-delà du délai de grâce, même un agent lancé avant cesse de servir (vérifié à chaque appel)."""
        return bool(licence) and licences.etat_du_jour(licence)["etat"] == "hors_delai"

    async def finir_les_tours(delai: float) -> int:
        """Attend la fin des tours en cours (un tour peut en lancer un autre) ; rend ceux qui restent."""
        fin = time.monotonic() + delai
        while conversations.taches and time.monotonic() < fin:
            await asyncio.wait(set(conversations.taches), timeout=fin - time.monotonic())
        return len(conversations.taches)

    @contextlib.asynccontextmanager
    async def vie(_):
        arret = asyncio.Event()
        # Chez le client, pas de porte pour réveiller l'agent à l'heure d'un rappel ni pour le relancer
        # sur une nouvelle configuration : il veille lui-même.
        veille = asyncio.create_task(veiller(arret)) if chez_le_client and (rappels is not None or ordres is not None) else None
        yield
        # L'arrêt (SIGTERM : mise à jour, redémarrage) : ce qui est en route va au bout. La veille finit
        # sa tournée de rappels (un rappel envoyé est aussi marqué), puis les tours en cours se terminent.
        arret.set()
        if veille:
            await asyncio.wait({veille}, timeout=delai_vider)
        restantes = await finir_les_tours(delai_vider)
        if restantes:
            log.warning("arrêt avec %d tour(s) inachevé(s)", restantes)

    def a_relire() -> bool:
        """Une autre configuration est à servir : poussée et acceptée, retirée par le client, ou la précédente
        après un échec. Comparée par le numéro de son ordre (aucun : le fichier)."""
        _, nouvelle, _ = pilotages.configuration_servie(fichier, ordres.a_servir(fichier.id), cle_pilotage)
        return (nouvelle or {}).get("ordre") != (pilotee or {}).get("ordre")

    async def veiller(arret: asyncio.Event):
        verifier_le = 0.0
        while not arret.is_set():
            prochain = None
            if rappels is not None and not licence_echue():
                try:
                    prochain = (await conversations.envoyer_rappels_echus(time.time())).get("prochain")
                except Exception as e:
                    log.error("rappels en échec : %s", str(e)[:200])
            if ordres is not None and time.monotonic() >= verifier_le:
                verifier_le = time.monotonic() + 30
                try:
                    if await asyncio.to_thread(a_relire):
                        # L'arrêt en douceur (SIGTERM) : les tours en cours finissent, puis Compose ou
                        # Kubernetes relancent l'agent, qui relit sa configuration.
                        log.info("nouvelle configuration du pilotage : l'agent finit ses tours et redémarre")
                        quitter()
                        return
                except Exception as e:
                    log.error("pilotage illisible : %s", str(e)[:200])
            attente = min(60.0, max(1.0, (prochain - time.time()) if prochain else 60.0))
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(arret.wait(), timeout=attente)

    app = FastAPI(title=f"megga-agents {conf.id}", docs_url=None, redoc_url=None, openapi_url=None, lifespan=vie)
    app.state.config = conf
    app.state.conversations = conversations
    app.state.taches = conversations.taches

    @app.get("/sante")
    async def sante():
        etat = {"ok": True, "client": conf.id, "zone": conf.zone, **version_image.carte(),
                "installation": "client" if chez_le_client else "megga"}
        if licence:
            etat["licence"] = licences.etat_du_jour(licence)
        if chez_le_client:  # d'où vient la configuration servie : poussée par MEGGA (version, ordre), ou le fichier
            etat["configuration"] = {"source": "pilotage", **pilotee} if pilotee else {"source": "fichier"}
        if licence_echue():  # les sondes le voient : l'agent n'est plus en service
            return JSONResponse({**etat, "ok": False}, status_code=503)
        return etat

    @app.get("/whatsapp")
    async def abonnement(requete: Request):
        """Meta vérifie l'adresse du webhook : le défi est rendu si le jeton correspond."""
        p = requete.query_params
        jeton = env.get("META_VERIFY_TOKEN", "")
        # En octets : un jeton accentué se compare aussi (sur des textes, compare_digest n'accepte que l'ASCII).
        if jeton and p.get("hub.mode") == "subscribe" and hmac.compare_digest(p.get("hub.verify_token", "").encode(), jeton.encode()):
            return Response(p.get("hub.challenge", ""), media_type="text/plain")
        return Response("refusé", status_code=403)

    @app.post("/whatsapp")
    async def whatsapp(requete: Request):
        if licence_echue():
            return Response("licence échue", status_code=503)
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

    def interne(requete: Request) -> bool:
        jeton = requete.headers.get("x-megga-interne", "")
        return bool(jeton_interne) and hmac.compare_digest(jeton.encode(), jeton_interne.encode())

    @app.post("/interne/rappels")
    async def interne_rappels(requete: Request):
        if not interne(requete):
            return Response("refusé", status_code=401)
        return await conversations.envoyer_rappels_echus(time.time())

    @app.post("/interne/vider")
    async def interne_vider(requete: Request):
        if not interne(requete):
            return Response("refusé", status_code=401)
        return {"restantes": await finir_les_tours(delai_vider)}

    def lisible(requete: Request) -> Response | None:
        if not interne(requete):
            return Response("refusé", status_code=401)
        if lecture is None or journal is None or fil is None:
            return Response("suivi indisponible", status_code=503)
        return None

    def borne(valeur: str | None, defaut: int, maximum: int) -> int:
        try:
            return max(1, min(int(valeur or defaut), maximum))
        except ValueError:
            return defaut

    def date(valeur: str | None) -> float:
        try:
            return max(0.0, float(valeur or 0))
        except ValueError:
            return 0.0

    @app.get("/interne/suivi")
    async def interne_suivi(requete: Request):
        if (refus := lisible(requete)) is not None:
            return refus
        depuis = date(requete.query_params.get("depuis"))
        tours = await asyncio.to_thread(lecture.tours, depuis)
        totaux = await asyncio.to_thread(journal.totaux, depuis)
        attente = await asyncio.to_thread(rappels.en_attente) if rappels is not None else 0
        return suivi_agent.resumer(conf, tours, totaux, attente, depuis)

    @app.get("/interne/suivi/conversations")
    async def interne_conversations(requete: Request):
        if (refus := lisible(requete)) is not None:
            return refus
        limite = borne(requete.query_params.get("limite"), 50, 200)
        # Le fil d'abord ; les tours d'Agno pour les conversations d'avant le fil.
        source = lecture if await asyncio.to_thread(fil.vide) else fil
        return {"conversations": await asyncio.to_thread(source.conversations, limite)}

    @app.get("/interne/suivi/conversations/{personne}")
    async def interne_echanges(personne: str, requete: Request):
        if (refus := lisible(requete)) is not None:
            return refus
        if not suivi_agent.PERSONNE.fullmatch(personne):
            return Response("personne", status_code=400)
        limite = borne(requete.query_params.get("limite"), 50, 200)
        messages = await asyncio.to_thread(fil.messages, personne, limite)
        if not messages:
            messages = await asyncio.to_thread(lecture.messages, personne, limite, EXCUSE)
        return {"personne": personne, "messages": [suivi_agent.message_lisible(m) for m in messages]}

    @app.get("/interne/suivi/alertes")
    async def interne_alertes(requete: Request):
        if (refus := lisible(requete)) is not None:
            return refus
        return {"alertes": await asyncio.to_thread(journal.alertes, date(requete.query_params.get("depuis")))}

    if env.get("JWT_VERIFICATION_KEY"):
        from agno.os import AgentOS

        os.environ.setdefault("JWT_VERIFICATION_KEY", env["JWT_VERIFICATION_KEY"])
        return AgentOS(agents=[agent], base_app=app, authorization=True, telemetry=False).get_app()
    return app


def principal() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    uvicorn.run(creer(), host="0.0.0.0", port=int(os.environ.get("PORT", "8080")), access_log=False)
