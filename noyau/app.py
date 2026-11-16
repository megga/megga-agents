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
  GESTIONNAIRES, GESTION_CLE  les gens du client et la clé de la gestion de son site (lot 7.1)
  SITE_CLE             facultatif : la clé du site du client pour /site/… (32 caractères au moins, lot 7.4)
Chaque secret peut aussi venir d'un fichier : <NOM>_FILE (noyau/environnement.py).

  PILOTAGE             le réglage du pilotage chez le client (non, suivi, complet), le même que celui du pilote

Avec PILOTAGE à suivi ou complet, la configuration servie est la dernière poussée par MEGGA et acceptée
(noyau/pilotage.py), revérifiée au démarrage, sinon CLIENT_CONFIG ; avec non, toujours CLIENT_CONFIG.
Quand le pilote en note une autre, l'agent finit ses tours et s'arrête : Compose ou Kubernetes le
relancent, et il la relit.

Routes :
  GET  /sante     l'état du conteneur, sans rien de privé
  GET  /whatsapp  l'abonnement du webhook de Meta (chez le client ; chez MEGGA, la porte s'en charge)
  POST /whatsapp  un webhook de Meta, transmis tel quel (corps et signature) ; sans numéro configuré, 404
  POST /api/messages  un logiciel parle à l'agent (clé du logiciel, noyau/api.py et docs/api.md)
  POST /site/bien      le site signale un bien entré en ligne {reference} : rapprochement et réseau (clé SITE_CLE)
  POST /site/demande   une demande d'information laissée sur une fiche du site (clé SITE_CLE)
  GET  /interne/cles             les clés des logiciels, sans empreinte (jeton INTERNE_TOKEN)
  POST /interne/cles             {id, logiciel, empreinte, par_minute} une clé créée par l'atelier
  DELETE /interne/cles/{id}      retire une clé
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

from . import api as entree_api
from . import approbations, reprises
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
from .roles import Personnes, lire_gestionnaires
from .tour import EXCUSE, Conversations, en_echec  # noqa: F401 (EXCUSE et en_echec réexportés)
from .voix import Voie
from .approbations import Gardien
from .whatsapp import FENETRE_S, FRAICHEUR_S, Expediteur, SansWhatsApp, lire_echecs, lire_entrants, signature_valide

log = logging.getLogger("megga")

# Ce que la personne apprend quand l'équipe a décidé d'une action qu'elle avait demandée (noyau/approbations.py) ;
# son agent en connaît le détail au tour suivant.
REPONSES_APPROBATION = {
    "fr": {"faite": "Bonne nouvelle : l'équipe a validé votre demande, c'est fait.",
           "echec": "L'équipe a validé votre demande, mais elle n'a pas pu se faire. Nous revenons vers vous.",
           "refusee": "L'équipe n'a pas validé votre demande."},
    "en": {"faite": "Good news: the team approved your request, it is done.",
           "echec": "The team approved your request, but it could not be completed. We will get back to you.",
           "refusee": "The team did not approve your request."},
}
ETATS_REPRISE = ("ouverte", "prise", "rendue", "expiree")
ETATS_APPROBATION = ("attente", "accordee", "faite", "echec", "refusee", "expiree")
CORPS_DOCUMENT = 12 * 1024 * 1024  # un document de 8 Mo, en base64 dans du JSON
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


def outils_du_client(conf, rappels, groupes: tuple[str, ...] | None = None, services=None, relations=None,
                     connaissances=None) -> list:
    """Les outils du noyau (rappels) et ceux des packs que la configuration active ; `groupes` : ceux d'un rôle.
    `services` : ce dont les outils d'annonces ont besoin (packs/immobilier/annonces.py), s'ils sont branchés ;
    `relations` : les partenaires et les visiteurs (packs/immobilier/relations.py) ; `connaissances` : la base de
    documents du client (noyau/connaissances.py), sans elle l'outil dit qu'il n'y a rien à chercher ici."""
    groupes = ("rappels", *conf.outils) if groupes is None else groupes
    liste = outils_rappels(rappels, conf.fuseau) if "rappels" in groupes else []
    if "connaissances" in groupes:
        from .connaissances import outils as outils_connaissances

        liste += outils_connaissances(connaissances)
    if "annonces" in groupes:
        if services is None:
            raise RuntimeError("outils d'annonces sans gestion du site (Config.gestion et GESTION_CLE)")
        from packs.immobilier.annonces import outils as outils_annonces

        liste += outils_annonces(services)
    if set(groupes) & {"partenaires", "visiteurs", "vitrine", "accueil", "marche", "travail"}:
        if relations is None:
            raise RuntimeError("outils de partenaires et de visiteurs sans gestion du site (Config.gestion et GESTION_CLE)")
        liste += relations.outils(groupes)
    if "immobilier" in groupes:
        from packs.immobilier import Catalogue, outils as outils_immobilier

        if not conf.catalogue:
            raise RuntimeError("pack immobilier sans catalogue")
        liste += outils_immobilier(Catalogue(conf.catalogue))
    return liste


def _reecriture(conf, cles):
    """Le modèle qui réécrit une réponse pour l'oral : un agent sans mémoire ni outils."""
    from agno.agent import Agent

    nom = conf.modeles.petit()
    oral = Agent(model=modele(nom, cles), instructions=consignes_orales(conf), telemetry=False, markdown=False)

    async def reecrire(demande: str) -> str:
        sortie = await oral.arun(demande)
        if en_echec(sortie):
            raise RuntimeError("réécriture en échec")
        return getattr(sortie, "content", "") or ""

    return reecrire


def _resumeur(conf, cles):
    """Le modèle qui tient le fil (noyau/fil.py) : sans mémoire ni outils, celui de l'oral (Modeles.petit)."""
    from agno.agent import Agent

    nom = conf.modeles.petit()

    async def resumer(consigne: str, demande: str) -> str:
        sortie = await Agent(model=modele(nom, cles), instructions=[consigne], telemetry=False, markdown=False).arun(demande)
        if en_echec(sortie):
            raise RuntimeError("résumé en échec")
        return getattr(sortie, "content", "") or ""

    return resumer


def ensemble(*contextes):
    """Plusieurs Contextes d'un tour (async f(personne) -> texte) en un seul ; None s'il n'y en a aucun."""
    fonctions = [f for f in contextes if f is not None]
    if not fonctions:
        return None

    async def contexte(personne: str) -> str:
        return "\n\n".join(t for t in [await f(personne) for f in fonctions] if t)

    return contexte


def creer(env: dict[str, str] | None = None, agent=None, expediteur=None, voie=None, contacts=None,
          reecrire=None, attente: float = 2.5, seuil_regard: float = 8.0, rappels=None,
          delai_vider: float = 100.0, journal=None, lecture=None, fil=None, cle_licence=None, cle_pilotage=None,
          quitter=None, cles_api=None, agents=None, personnes=None, medias=None, relations=None, differes=None,
          fil_tenu=None, connaissances=None) -> FastAPI:
    """Les arguments nommés remplacent les vrais services (essais) ; `cle_licence` et `cle_pilotage`, les clés
    publiques des licences et des ordres de MEGGA ; `quitter`, l'arrêt de l'agent pour relire sa configuration."""
    env = charger(dict(os.environ if env is None else env))
    os.environ.setdefault("AGNO_TELEMETRY", "false")
    source = env.get("CLIENT_CONFIG") or env.get("CLIENT_CONFIG_FILE")
    if not source:
        raise RuntimeError("CLIENT_CONFIG manquante")
    fichier = configuration.lire(source)
    chez_le_client = env.get("MEGGA_INSTALLATION") == "client"
    # Le pilotage est le choix du client : avec « non », MEGGA ne change rien, même ce qu'il avait poussé.
    pilotage_actif = (env.get("PILOTAGE") or "non").strip().lower() in ("suivi", "complet")
    url = env.get("DATABASE_URL", "")
    # Chez le client, pas de licence valide, pas de démarrage (vérifiée sans appel extérieur), avant de toucher
    # à la base ; une configuration poussée garde l'identifiant du fichier (noyau/pilotage.py, config_de).
    licence = licences.verifier(env.get("MEGGA_LICENCE", ""), fichier.id, cle=cle_licence) if chez_le_client else None
    if agent is None:
        if not url:
            raise RuntimeError("DATABASE_URL manquante")
        stockage.migrer(url)  # avant toute table : une base neuve se reconnaît à ce qu'elle n'en a aucune
    # La dernière configuration poussée par MEGGA et acceptée, revérifiée ; sinon le fichier.
    ordres = stockage.Ordres(url) if pilotage_actif and url else None
    conf, pilotee, refus = fichier, None, None
    if ordres is not None:
        conf, pilotee, refus = pilotages.configuration_servie(fichier, ordres.a_servir(fichier.id), cle_pilotage)
        if refus:
            log.error("configuration poussée refusée (%s) : l'agent sert son fichier", refus)
    cles = {k: env.get(k, "") for k in CLES}
    quitter = quitter or (lambda: os.kill(os.getpid(), signal.SIGTERM))
    construire_agents = agent is None
    if construire_agents:
        rappels = rappels or stockage.Rappels(env["DATABASE_URL"])
        reecrire = reecrire or _reecriture(conf, cles)
    if env.get("DATABASE_URL"):
        journal = journal or stockage.Journal(env["DATABASE_URL"])
        lecture = lecture or stockage.Suivi(env["DATABASE_URL"])
        fil = fil or stockage.Fil(env["DATABASE_URL"])
        contacts = contacts or stockage.Contacts(env["DATABASE_URL"])
        cles_api = cles_api or stockage.ClesApi(env["DATABASE_URL"])
        medias = medias or stockage.Medias(env["DATABASE_URL"])
        differes = differes or stockage.Differes(env["DATABASE_URL"])
        if personnes is None:
            try:
                gestionnaires = lire_gestionnaires(env.get("GESTIONNAIRES"))
            except ValueError as e:
                raise RuntimeError(str(e)) from None
            personnes = Personnes(conf, gestionnaires, stockage.Bloques(env["DATABASE_URL"]), stockage.Partenaires(env["DATABASE_URL"]))
    if personnes is None:
        personnes = Personnes(conf)
    # La base de connaissances (noyau/connaissances.py), si l'agent ou un rôle en a le groupe d'outils ; son modèle ne
    # se charge qu'à la première recherche ou au premier document.
    groupes_actifs = {*conf.outils, *(o for r in conf.les_roles().values() for o in r.outils)}
    if connaissances is None and "connaissances" in groupes_actifs and env.get("DATABASE_URL"):
        from .connaissances import Base

        connaissances = Base(stockage.Connaissances(env["DATABASE_URL"]))
    if expediteur is None:
        expediteur = (Expediteur(env.get("META_TOKEN", ""), conf.whatsapp.numero_id, conf.whatsapp.version_graph)
                      if conf.whatsapp else SansWhatsApp())
    # Les approbations et le journal d'audit des outils (noyau/approbations.py) ; sans base, les règles tiennent quand
    # même (interdit : pas proposé ; à approuver : refusé), sans journal.
    gardien = (Gardien(stockage.Audit(env["DATABASE_URL"]), stockage.Approbations(env["DATABASE_URL"]))
               if env.get("DATABASE_URL") else Gardien())
    # Le transfert vers un humain (noyau/reprises.py), si le client l'a voulu (Config.transfert).
    transfert = None
    if conf.transfert and env.get("DATABASE_URL"):
        from .reprises import Transfert

        transfert = Transfert(stockage.Reprises(env["DATABASE_URL"]), fil, approbations.equipe(personnes.gestionnaires),
                              conf.nom_agent)
    # La gestion du site du client, pour les outils qui agissent au nom d'un gestionnaire (packs).
    gestion = None
    if conf.gestion is not None and env.get("GESTION_CLE"):
        from packs.immobilier.gestion import Gestion

        gestion = Gestion(conf.gestion, env["GESTION_CLE"])
    if construire_agents:
        base = stockage.base_agno(env["DATABASE_URL"])
        services = None
        if gestion is not None:
            from packs.immobilier.annonces import Services
            from packs.immobilier.redaction import Choisisseuse, Redactrice

            cle = cles.get("ANTHROPIC_API_KEY")
            from packs.immobilier.redaction import Assistante

            url = env["DATABASE_URL"]

            async def memoires(personne: str) -> list[str]:
                """Ce que l'agent a retenu d'un gestionnaire (sa mémoire d'Agno) : les clients qu'il cherche à loger."""
                souvenirs = await asyncio.to_thread(base.get_user_memories, user_id=personne) or []
                return [str(getattr(m, "memory", "") or "") for m in souvenirs]

            services = Services(gestion, personnes, medias, stockage.Etats(url), expediteur,
                                Redactrice(cle, conf.entreprise) if cle else None, conf.gestion.noms_interdits,
                                conf.gestion.formulaire_annonce, Choisisseuse(cle, conf.entreprise) if cle else None,
                                conf.gestion.fiche, conf.entreprise, personnes.partenaires or stockage.Partenaires(url),
                                stockage.Reseau(url), personnes.bloques or stockage.Bloques(url), stockage.Questions(url),
                                fuseau=conf.fuseau, memoires=memoires, assistante=Assistante(cle, conf.entreprise) if cle else None,
                                a_whatsapp=conf.whatsapp is not None, carnet=stockage.Carnet(url), veilles=stockage.Veilles(url),
                                reglage_marche=conf.marche, regles=stockage.Regles(url), rappels=rappels)
            if conf.marche is not None:
                from packs.immobilier.marche import Portails

                services.portails = Portails(cles.get("DEEPSEEK_API_KEY", ""))
            if relations is None and any(set(r.outils) & {"partenaires", "visiteurs", "vitrine", "accueil", "marche", "travail"}
                                         for r in conf.les_roles().values()):
                from packs.immobilier.relations import Relations

                relations = Relations(services)
        # Le fil des conversations (Config.fil), relu à chaque tour.
        if fil_tenu is None and conf.fil and fil is not None:
            from .fil import TenueDuFil

            fil_tenu = TenueDuFil(fil, stockage.Etats(env["DATABASE_URL"]), _resumeur(conf, cles), conf.fuseau)
        du_fil = fil_tenu.contexte if fil_tenu is not None else None
        agent = construire(conf, base, cles, outils=outils_du_client(conf, rappels, connaissances=connaissances)
                           + (transfert.outils_pour(None) if transfert else []),
                           contexte=ensemble(du_fil, gardien.contexte, transfert.contexte if transfert else None), gardien=gardien)
        # Un agent par rôle (noyau/roles.py) : ses consignes et ses outils en plus de ceux de tous, et le Contexte de
        # chaque tour (le fil ; les demandes, les questions, les règles des packs ; l'issue de ses demandes d'accord).
        agents = agents or {nom: construire(conf, base, cles,
                                            outils=outils_du_client(conf, rappels, role.outils, services, relations, connaissances)
                                            + (transfert.outils_pour(nom) if transfert else []),
                                            role=role, nom_role=nom, gardien=gardien,
                                            contexte=ensemble(du_fil, relations.contexte(role.outils) if relations else None,
                                                              gardien.contexte, transfert.contexte if transfert else None))
                            for nom, role in conf.les_roles().items()}
    if conf.les_roles() and agents is None:
        raise RuntimeError("des rôles sans agents")
    if voie is None and env.get("ELEVENLABS_API_KEY"):
        voie = Voie(env["ELEVENLABS_API_KEY"], conf.voix)
    conversations = Conversations(conf, agent, expediteur, voie, contacts, reecrire, attente, seuil_regard, rappels=rappels,
                                  journal=journal, fil=fil, agents=agents, medias=medias, differes=differes,
                                  choix={**(relations.choix if relations else {}), approbations.PREFIXE: gardien.choix,
                                         **({reprises.PREFIXE: transfert.choix} if transfert else {})},
                                  echeances=relations.echeances if relations else None, fil_tenu=fil_tenu,
                                  etats=stockage.Etats(env["DATABASE_URL"]) if env.get("DATABASE_URL") else None)
    if relations is not None:  # les outils qui préviennent quelqu'un d'autre passent par les conversations
        relations.reseau.s.conversations = conversations

    async def prevenir_equipe(demande: dict) -> None:
        """Une action attend un accord : chaque gestionnaire reçoit la demande, avec Accepter et Refuser, une fois
        fini le tour de la personne qui l'a faite (sa réponse part d'abord)."""
        numeros = approbations.equipe(personnes.gestionnaires)
        qui = demande["personne"]
        corps = (f"{conf.nom_agent} demande votre accord (demande {demande['id']}) pour {qui if qui.startswith('api:') else '+' + qui} : "
                 f"{demande['outil']}.\n{approbations.apercu(demande['arguments'])}")
        message = {"liste": {"corps": corps, "bouton": "Répondre", "section": f"Demande {demande['id']}", "lignes": [
            {"id": f"{approbations.PREFIXE}{demande['id']}:oui", "titre": "Accepter", "description": demande["outil"]},
            {"id": f"{approbations.PREFIXE}{demande['id']}:non", "titre": "Refuser"}]}}
        for n in numeros:
            conversations.apres_le_tour(qui, lambda n=n: conversations.envoyer_de_soi_meme(
                n, [message], "approbation", variables=[conf.nom_agent, demande["outil"]]))

    async def prevenir_personne(demande: dict, etat: str) -> None:
        """La personne qui a demandé l'action apprend l'issue ; son agent en connaîtra le détail au tour suivant."""
        textes = REPONSES_APPROBATION.get(conf.langue, REPONSES_APPROBATION["fr"])
        if etat in textes:
            await conversations.envoyer_de_soi_meme(demande["personne"], [{"texte": textes[etat]}], "approbation_reponse",
                                                    variables=[conf.nom_agent])

    gardien.notifier, gardien.prevenir = prevenir_equipe, prevenir_personne
    if transfert is not None:  # l'équipe répond par les conversations ; un tour s'arrête si elle a la main
        transfert.conversations = conversations
        conversations.reprise = transfert.garde
    jeton_interne = env.get("INTERNE_TOKEN", "")
    cle_site = env.get("SITE_CLE", "")
    secret = env.get("META_APP_SECRET")
    # Les messages déjà traités, gardés dans la base : un webhook renvoyé après un redémarrage n'a pas deux réponses.
    deja = stockage.Vus(env["DATABASE_URL"]) if env.get("DATABASE_URL") else Deja()
    debit_cles = entree_api.DebitCles()

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
        veille = asyncio.create_task(veiller(arret)) if (chez_le_client and rappels is not None) or ordres is not None else None
        yield
        # L'arrêt (SIGTERM : mise à jour, redémarrage) : ce qui est en route va au bout. La veille finit
        # sa tournée de rappels (un rappel envoyé est aussi marqué), puis les tours en cours se terminent.
        arret.set()
        if veille:
            await asyncio.wait({veille}, timeout=delai_vider)
        restantes = await finir_les_tours(delai_vider)
        if restantes:
            log.warning("arrêt avec %d tour(s) inachevé(s)", restantes)
        # Les lignes du journal d'audit de ces tours, écrites en arrière-plan (noyau/approbations.py)
        if restantes := await gardien.vider(delai_vider):
            log.warning("arrêt avec %d ligne(s) du journal d'audit non écrite(s)", restantes)

    def a_relire() -> bool:
        """Une autre configuration est à servir : poussée et acceptée, retirée par le client, ou la précédente
        après un échec. Comparée par le numéro de son ordre (aucun : le fichier)."""
        _, nouvelle, _ = pilotages.configuration_servie(fichier, ordres.a_servir(fichier.id), cle_pilotage)
        return (nouvelle or {}).get("ordre") != (pilotee or {}).get("ordre")

    async def veiller(arret: asyncio.Event):
        verifier_le = 0.0
        while not arret.is_set():
            prochain = None
            if chez_le_client and rappels is not None and not licence_echue():
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
    app.state.personnes = personnes
    app.state.gestion = gestion
    app.state.taches = conversations.taches

    @app.get("/sante")
    async def sante():
        etat = {"ok": True, "client": conf.id, "zone": conf.zone, **version_image.carte(),
                "installation": "client" if chez_le_client else "megga"}
        if licence:
            etat["licence"] = licences.etat_du_jour(licence)
        if chez_le_client or ordres is not None:  # d'où vient la configuration servie : poussée par MEGGA (version, ordre), ou le fichier
            etat["configuration"] = {"source": "pilotage", **pilotee} if pilotee else {"source": "fichier"}
        if licence_echue():  # les sondes le voient : l'agent n'est plus en service
            return JSONResponse({**etat, "ok": False}, status_code=503)
        return etat

    @app.get("/whatsapp")
    async def abonnement(requete: Request):
        """Meta vérifie l'adresse du webhook : le défi est rendu si le jeton correspond."""
        if conf.whatsapp is None:
            return Response("pas de WhatsApp", status_code=404)
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
        if conf.whatsapp is None:
            return Response("pas de WhatsApp", status_code=404)
        corps = await requete.body()
        if not signature_valide(corps, requete.headers.get("x-hub-signature-256"), secret):
            return Response("signature", status_code=401)
        try:
            evenement = json.loads(corps)
        except ValueError:
            return Response("corps", status_code=400)
        # Rejoué par la porte (un webhook qu'elle a gardé pendant une panne du conteneur) : lu jusqu'à 24 heures après.
        rejoue = requete.headers.get("x-megga-rejoue") == "1" and interne(requete)
        for echec in lire_echecs(evenement, conf.whatsapp.numero_id):
            log.warning("envoi refusé par Meta : %s", echec)
            conversations.noter_journal("envoi_refuse", detail=echec)
        lus = 0
        for m in lire_entrants(evenement, conf.whatsapp.numero_id):
            if not m.frais(limite=FENETRE_S if rejoue else FRAICHEUR_S):
                log.warning("message ancien, sans réponse")
                conversations.noter_journal("message_ancien", detail="rejoué" if rejoue else "")
                continue
            if not await asyncio.to_thread(deja.nouveau, m.id):
                continue
            role = await asyncio.to_thread(personnes.role, m.de)
            if role == "bloque":  # un numéro bloqué par le client : ni lu, ni répondu
                continue
            if role is None:  # aucun rôle ne sert cette personne : au plus un refus poli, une fois par jour
                refus = personnes.refuser(m.de)
                if refus:
                    conversations._lancer(conversations._ecrire(m.de, refus))
                continue
            conversations.recevoir(m, role)
            lus += 1
        # Meta veut une réponse rapide : le tour se poursuit après.
        return Response(f"reçu {lus}", media_type="text/plain")

    def erreur(statut: int, message: str, entetes: dict | None = None, **autres) -> JSONResponse:
        return JSONResponse({"erreur": message, **autres}, status_code=statut, headers=entetes)

    @app.post("/api/messages")
    async def api_messages(requete: Request):
        """Un logiciel parle à l'agent : la réponse vient dans la même requête (noyau/api.py, docs/api.md)."""
        if licence_echue():
            return erreur(503, "licence échue")
        if cles_api is None:
            return erreur(503, "entrée par API indisponible")
        jeton = (requete.headers.get("authorization") or "").removeprefix("Bearer ").strip()
        cle = await asyncio.to_thread(cles_api.par_empreinte, entree_api.empreinte(jeton)) if entree_api.CLE.fullmatch(jeton) else None
        if cle is None:
            return erreur(401, "clé refusée")
        # Lu par morceaux, borné : un corps trop gros est refusé sans être gardé en mémoire.
        corps = bytearray()
        async for morceau in requete.stream():
            corps += morceau
            if len(corps) > entree_api.CORPS_MAX:
                return erreur(413, "requête trop grosse")
        try:
            donnees = json.loads(bytes(corps))
        except ValueError:
            return erreur(400, "corps : du JSON")
        if not isinstance(donnees, dict) or set(donnees) - {"personne", "texte"}:
            return erreur(400, "corps : {personne, texte}")
        personne, texte = donnees.get("personne"), donnees.get("texte")
        if not isinstance(personne, str) or not entree_api.IDENTIFIANT.fullmatch(personne):
            return erreur(400, "personne : un identifiant de 1 à 40 caractères (lettres, chiffres, . _ -), avec au moins une lettre ; jamais un numéro de téléphone")
        if not isinstance(texte, str) or not texte.strip() or len(texte) > entree_api.TEXTE_MAX:
            return erreur(400, f"texte : de 1 à {entree_api.TEXTE_MAX} caractères")
        qui = entree_api.personne_interne(cle["logiciel"], personne)

        def trop(de: str, attente: int) -> JSONResponse:
            conversations.noter_journal("api_debit", detail=cle["id"] if de == "clé" else "personne")
            return erreur(429, f"trop de messages pour cette {de}", attente=attente, entetes={"retry-after": str(attente)})

        role = await asyncio.to_thread(personnes.role, qui)
        if role is None:  # des rôles sans visiteurs : personne n'est servi par API
            return erreur(403, "cet agent ne répond pas par API")
        # Les deux débits sont regardés avant d'en compter aucun : un refus n'use pas l'autre.
        if not debit_cles.libre(cle):
            return trop("clé", debit_cles.attente(cle))
        if not conversations.debit.libre(qui):
            return trop("personne", conversations.debit.attente(qui))
        if (atteint := conversations.plafond.libre(qui, role)) is not None:  # le plafond du jour (relecture, I7)
            conversations.noter_plafond(atteint)
            attente = conversations.plafond.attente()
            return erreur(429, "plafond du jour atteint", attente=attente, entetes={"retry-after": str(attente)})
        debit_cles.permis(cle)
        tour = await conversations.repondre_api(qui, texte.strip(), role)
        if tour is None:  # une autre requête de la même personne est passée entre-temps : la place de la clé est rendue
            debit_cles.rendre(cle)
            return trop("personne", conversations.debit.attente(qui))
        reponse, echec = tour
        if echec:  # le tour a échoué : le logiciel peut réessayer, ou montrer l'excuse
            return erreur(503, "l'agent n'a pas pu répondre", reponse=reponse)
        return {"reponse": reponse}

    async def site(requete: Request):
        """Une requête du site du client (lot 7.4) : sa clé, puis son corps JSON borné ; sinon la réponse de refus."""
        if relations is None or len(cle_site) < 32:
            return None, erreur(404, "introuvable")
        jeton = (requete.headers.get("authorization") or "").removeprefix("Bearer ").strip()
        if not hmac.compare_digest(jeton.encode(), cle_site.encode()):
            return None, erreur(401, "clé refusée")
        corps = bytearray()
        async for morceau in requete.stream():
            corps += morceau
            if len(corps) > entree_api.CORPS_MAX:
                return None, erreur(413, "requête trop grosse")
        try:
            donnees = json.loads(bytes(corps))
        except ValueError:
            return None, erreur(400, "corps : du JSON")
        return (donnees, None) if isinstance(donnees, dict) else (None, erreur(400, "corps : un objet JSON"))

    @app.post("/site/bien")
    async def site_bien(requete: Request):
        """Un bien entre en ligne : rapproché des clients en mémoire et des recherches gardées des partenaires, juste après."""
        donnees, refus = await site(requete)
        if refus is not None:
            return refus
        reference = str(donnees.get("reference") or "").strip()[:40]
        if not reference:
            return erreur(400, "reference")
        conversations._lancer(conversations._sans_echec(relations.reseau.bien_en_ligne(reference)))
        return JSONResponse({"signale": reference}, status_code=202)

    @app.post("/site/demande")
    async def site_demande(requete: Request):
        """Une demande d'information d'une fiche : au courtier du bien, avec une réponse prête."""
        donnees, refus = await site(requete)
        if refus is not None:
            return refus
        from packs.immobilier.gestion import GestionErreur

        try:
            n = await relations.visiteurs.demande_du_site(donnees)
        except ValueError as e:
            return erreur(400, str(e)[:200])
        except LookupError as e:
            return erreur(503, str(e)[:200])
        except GestionErreur:
            return erreur(502, "gestion du site injoignable")
        return JSONResponse({"transmise": n}, status_code=202)

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

    @app.get("/interne/suivi/audit")
    async def interne_audit(requete: Request):
        """Le journal d'audit des outils (noyau/approbations.py) : les appels les plus récents d'abord."""
        if (refus := lisible(requete)) is not None:
            return refus
        if gardien.audit is None:
            return Response("base absente", status_code=503)
        limite = borne(requete.query_params.get("limite"), 200, 1000)
        return {"appels": await asyncio.to_thread(gardien.audit.lire, date(requete.query_params.get("depuis")), limite)}

    @app.get("/interne/suivi/approbations")
    async def interne_approbations(requete: Request):
        """Les demandes d'accord, les plus récentes d'abord, leurs arguments masqués ; `etat=attente` pour celles à décider."""
        if (refus := lisible(requete)) is not None:
            return refus
        if gardien.demandes is None:
            return Response("base absente", status_code=503)
        etat = requete.query_params.get("etat")
        if etat and etat not in ETATS_APPROBATION:
            return erreur(400, "etat : " + ", ".join(ETATS_APPROBATION))
        demandes = await asyncio.to_thread(gardien.demandes.lister, etat, borne(requete.query_params.get("limite"), 100, 500))
        return {"demandes": [{**{k: v for k, v in d.items() if k not in ("arguments", "relu")},
                              "apercu": approbations.apercu(d["arguments"])} for d in demandes]}

    @app.get("/interne/suivi/reprises")
    async def interne_reprises(requete: Request):
        """Les conversations confiées à l'équipe (lot 9.3), les plus récentes d'abord ; `etat=ouverte` : celles à prendre."""
        if (refus := lisible(requete)) is not None:
            return refus
        if transfert is None:
            return erreur(409, "cet agent ne transmet pas de conversations (Config.transfert)")
        etat = requete.query_params.get("etat")
        if etat and etat not in ETATS_REPRISE:
            return erreur(400, "etat : " + ", ".join(ETATS_REPRISE))
        lignes = await asyncio.to_thread(transfert.reprises.lister, etat, borne(requete.query_params.get("limite"), 100, 500))
        return {"reprises": [{k: v for k, v in r.items() if k not in ("prevenue", "relue")} for r in lignes]}

    @app.post("/interne/reprises/{ident}")
    async def interne_reprise(ident: str, requete: Request):
        """Ce que la console fait d'une conversation transmise : {action: prendre | message | rendre, texte?}."""
        if not interne(requete):
            return Response("refusé", status_code=401)
        if transfert is None:
            return erreur(409, "cet agent ne transmet pas de conversations (Config.transfert)")
        try:
            d = await requete.json()
            action, texte = d["action"], d.get("texte", "")
        except (ValueError, KeyError, TypeError):
            return erreur(400, "{action: prendre | message | rendre, texte?}")
        if action not in reprises.ACTIONS or not isinstance(texte, str) or not ident.isdigit() or len(ident) > 10:
            return erreur(400, "{action: prendre | message | rendre, texte?}")
        n = int(ident)
        if action == "message":
            try:
                return await transfert.repondre(n, texte, "console")
            except ValueError as e:
                return erreur(409 if "plus en cours" in str(e) else 400, str(e))
        r = await (transfert.prendre(n, "console") if action == "prendre" else transfert.rendre(n))
        if r is None:
            return erreur(409, f"la conversation {n} n'est plus " + ("à prendre" if action == "prendre" else "en cours"))
        return {"id": n, "etat": r["etat"]}

    @app.post("/interne/approbations/{ident}")
    async def interne_decider(ident: str, requete: Request):
        """Une décision de la console : {accord: true|false} ; l'action accordée est faite tout de suite."""
        if not interne(requete):
            return Response("refusé", status_code=401)
        if gardien.demandes is None:
            return Response("base absente", status_code=503)
        try:
            d = await requete.json()
            accord = d["accord"]
        except (ValueError, KeyError, TypeError):
            return erreur(400, "{accord: true|false}")
        if not isinstance(accord, bool) or not ident.isdigit() or len(ident) > 10:
            return erreur(400, "{accord: true|false}")
        try:
            return await gardien.decider(int(ident), accord, "console")
        except ValueError as e:
            return erreur(409, str(e))

    def cles_lisibles(requete: Request) -> Response | None:
        if not interne(requete):
            return Response("refusé", status_code=401)
        if cles_api is None:
            return Response("base absente", status_code=503)
        return None

    # La base de connaissances (lot 9.2) : la console ajoute, liste et retire les documents du client, à travers la porte.

    def base_lisible(requete: Request) -> Response | None:
        if not interne(requete):
            return Response("refusé", status_code=401)
        if connaissances is None:
            return erreur(409, "cet agent n'a pas de base de connaissances (groupe d'outils « connaissances »)")
        return None

    @app.get("/interne/connaissances")
    async def interne_documents(requete: Request):
        if (refus := base_lisible(requete)) is not None:
            return refus
        return {"documents": await asyncio.to_thread(connaissances.documents)}

    @app.post("/interne/connaissances")
    async def interne_ajouter_document(requete: Request):
        """{titre, genre (texte, pdf, html), texte ou base64, source?} : le document lu, découpé, calculé, rangé."""
        if (refus := base_lisible(requete)) is not None:
            return refus
        corps = bytearray()
        async for morceau in requete.stream():
            corps += morceau
            if len(corps) > CORPS_DOCUMENT:
                return erreur(413, "document trop gros")
        try:
            from .connaissances import contenu_de

            titre, contenu, genre, source = contenu_de(json.loads(bytes(corps)))
            return await asyncio.to_thread(connaissances.ajouter, titre, contenu, genre, source)
        except ValueError as e:  # JSON illisible, document refusé, bornes du client
            return erreur(400, str(e)[:300])

    @app.delete("/interne/connaissances/{ident}")
    async def interne_retirer_document(ident: str, requete: Request):
        if (refus := base_lisible(requete)) is not None:
            return refus
        if not ident.isdigit() or len(ident) > 10:
            return erreur(400, "identifiant de document")
        return {"id": int(ident), "retire": await asyncio.to_thread(connaissances.retirer, int(ident))}

    @app.get("/interne/cles")
    async def interne_cles(requete: Request):
        if (refus := cles_lisibles(requete)) is not None:
            return refus
        return {"cles": await asyncio.to_thread(cles_api.lister)}

    @app.post("/interne/cles")
    async def interne_ajouter_cle(requete: Request):
        """Une clé créée par l'atelier : son empreinte seulement, la clé ne vient jamais jusqu'ici."""
        if (refus := cles_lisibles(requete)) is not None:
            return refus
        try:
            d = await requete.json()
            ident, logiciel, empreinte = d["id"], d["logiciel"], d["empreinte"]
            debit = entree_api.par_minute(d.get("par_minute"))
        except (ValueError, KeyError, TypeError):
            return erreur(400, "{id, logiciel, empreinte, par_minute}")
        if not (isinstance(ident, str) and entree_api.IDENT_CLE.fullmatch(ident) and isinstance(logiciel, str)
                and entree_api.LOGICIEL.fullmatch(logiciel) and isinstance(empreinte, str) and entree_api.EMPREINTE.fullmatch(empreinte)):
            return erreur(400, "{id, logiciel, empreinte, par_minute}")
        if not await asyncio.to_thread(cles_api.ajouter, ident, logiciel, empreinte, debit):
            return erreur(409, "clé déjà enregistrée")
        return {"id": ident, "logiciel": logiciel, "par_minute": debit}

    @app.delete("/interne/cles/{ident}")
    async def interne_retirer_cle(ident: str, requete: Request):
        if (refus := cles_lisibles(requete)) is not None:
            return refus
        if not entree_api.IDENT_CLE.fullmatch(ident):
            return erreur(400, "identifiant de clé")
        return {"id": ident, "retiree": await asyncio.to_thread(cles_api.retirer, ident)}

    if env.get("JWT_VERIFICATION_KEY"):
        from agno.os import AgentOS
        from agno.os.authz import Authorization

        os.environ.setdefault("JWT_VERIFICATION_KEY", env["JWT_VERIFICATION_KEY"])
        # Le jeton d'AgentOS ne protège que l'API d'AgentOS : nos routes ont leur propre garde (signature
        # de Meta, clé du logiciel, jeton interne), et /sante sert aux sondes.
        propres = [r.path for r in app.routes if hasattr(r, "path")]
        exclues = sorted({p.split("{", 1)[0] + "*" if "{" in p else p for p in propres})
        return AgentOS(agents=[agent], base_app=app, authorization=Authorization(excluded_route_paths=exclues),
                       telemetry=False).get_app()
    return app


def principal() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    uvicorn.run(creer(), host="0.0.0.0", port=int(os.environ.get("PORT", "8080")), access_log=False)
