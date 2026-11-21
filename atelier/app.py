"""L'API de l'atelier. Pas d'écran : l'interface viendra au dernier lot et ne fera que l'appeler.

Variables d'environnement (jamais dans le dépôt) :
  DATABASE_URL       la base de l'atelier (versions des configurations, jetons des clients)
  ADMIN_TOKEN        le jeton de MEGGA (le même que celui de la porte)
  PORTE_URL          l'adresse de la porte, pour l'annuaire et les conteneurs
  ANTHROPIC_API_KEY, DEEPSEEK_API_KEY   les modèles, pour le mode d'essai
  ESSAIS_DIR         facultatif : le dossier des bases d'essai
  PILOTAGE_CLE       la clé privée de pilotage : elle signe les ordres des installations hors Cloudflare
  STRIPE_CLE         la clé secrète de Stripe (forfaits, recharges) ; sans elle, les routes de Stripe répondent 503
  STRIPE_SIGNATURE   le secret qui signe les événements de Stripe (POST /stripe)

Rôles, par le jeton (Authorization: Bearer …) :
  MEGGA   ADMIN_TOKEN : tous les clients, tous les réglages
  client  un jeton délivré par MEGGA : son seul agent, les réglages simples

Routes (toutes sous /atelier) :
  GET   /catalogue                              métiers, outils, zones, modèles, réglages du client
  GET   /gabarits                               les modèles par métier, prêts à marcher
  GET   /clients                                les clients et leur état (MEGGA : tous ; client : le sien) ;
                                                « ecart » : l'annuaire de la porte ne sert pas la version en service
  POST  /clients                                MEGGA : un nouveau client, d'une configuration complète
                                                ou d'un modèle par métier (gabarit, identité, prénom)
  GET   /clients/{id}                           un client, sa version en service et sa configuration
  PUT   /clients/{id}/pays                      MEGGA : le pays du client (code ISO à deux lettres, ou null)
  GET   /clients/{id}/versions                  l'historique
  GET   /clients/{id}/versions/{v}              une version et sa configuration
  POST  /clients/{id}/valider                   valide des changements sans rien enregistrer
  POST  /clients/{id}/versions                  une nouvelle version (brouillon), d'après une base
  POST  /clients/{id}/gabarit                   une nouvelle version d'après un modèle par métier et un prénom
  POST  /clients/{id}/versions/{v}/essai        l'agent de cette version répond, hors WhatsApp
  POST  /clients/{id}/versions/{v}/activer      mise en service (ou retour à une version publiée)
  POST  /clients/{id}/reprise                   MEGGA : reprendre la main (ou la rendre)
  POST  /clients/{id}/jetons                    MEGGA : un jeton pour le client, montré une fois
  DELETE /clients/{id}/jetons                   MEGGA : retire tous les jetons du client

Entrée par API (zones de la porte ; MEGGA ou le client) : les clés des logiciels, gardées en empreinte
dans la base du client, jamais dans l'atelier. Hors Cloudflare, elles se créent chez le client
(python -m noyau.cles).
  GET   /clients/{id}/cles                      les clés, sans empreinte
  POST  /clients/{id}/cles                      {logiciel, par_minute?} une clé, montrée une fois
  DELETE /clients/{id}/cles/{cle}               retire une clé, tout de suite

Connecteurs de Composio (atelier/routes_composio.py, noyau/composio.py) :
  GET   /clients/{id}/composio/comptes          les comptes connectés par le client, sans jeton
  POST  /clients/{id}/composio/lien             MEGGA : {auth_config, retour?} le lien où le client connecte un compte

L'agent d'accueil des entreprises (atelier/routes_accueil.py, atelier/accueil.py) : MEGGA ou le client
  GET   /clients/{id}/accueil                   ce qu'il a noté (notes, modèle, prénom, brouillon) et la présentation
  POST  /clients/{id}/accueil                   un tour de conversation en AG-UI, la réponse au fil de l'eau

Suivi (lu dans le conteneur du client, qui se réveille s'il dormait) :
  GET   /clients/{id}/suivi[?jours=7]           état, activité (tours, personnes, modèles, voix) ;
                                                coûts pour MEGGA seulement
  GET   /clients/{id}/conversations[?limite=]   le client seulement : les personnes qui ont écrit
  GET   /clients/{id}/conversations/{personne}  le client seulement : les derniers échanges avec elle
  GET   /clients/{id}/alertes[?jours=7]         échecs, pannes du conteneur, écart avec l'annuaire
  GET   /tarifs, PUT /tarifs                    MEGGA : les tarifs des modèles et de la voix
  GET   /forfaits, /abonnements, …              MEGGA : les forfaits et les clients payants (atelier/routes_forfaits.py)
  GET   /releves[?jours=7]                      MEGGA : le relevé chiffré de tous les agents, jour par jour (92 au plus),
                                                avec coûts, écart et agents silencieux (aucun conteneur réveillé)
  GET   /alertes, PUT /alertes/regles, …       MEGGA : les alertes envoyées (atelier/routes_alertes.py) : règles à
                                                seuils sur le relevé, destinations, évaluation toutes les 5 minutes

Installations hors Cloudflare (chez le client, zone suisse), pilotées par un canal sortant et signé :
  GET   /installations                          MEGGA : les installations et leur dernier état
  GET   /clients/{id}/installation              l'installation, ses derniers ordres et le journal du pilotage
  PUT   /clients/{id}/installation              MEGGA : {cle_publique} remise par l'installation (mise en service)
  DELETE /clients/{id}/installation             MEGGA : révoque sa clé
  POST  /clients/{id}/installation/image        MEGGA : {version, image} une version d'image proposée
  Pour ces zones, activer dépose un ordre signé ; le suivi et les alertes viennent du dernier relevé
  du pilote ; les conversations ne quittent jamais l'installation.

Le pilote d'une installation (requête signée de sa clé, transmise par la porte, sans jeton) :
  POST  /pilotage/releve                        son état et son suivi ; la réponse porte les ordres à remettre
"""

from __future__ import annotations

import asyncio
import hmac
import logging
import os
import re
import tempfile
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from fastapi import APIRouter, Body, Depends, FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from noyau import pilotage as pilotages
from noyau import stockage
from noyau.app import CLES
from noyau.config import SANS_WHATSAPP_SCHEMA, Config

from . import gabarits, pays, regles, routes_accueil, routes_alertes, routes_cles, routes_composio, routes_forfaits, routes_installations, routes_stripe
from . import routes_suivi
from .alertes import Etats as EtatsAlertes
from .couts import Tarifs
from .essai import essayer
from .forfaits import Abonnements
from .stripe import Stripe
from .pilotage import TAILLE as TAILLE_RELEVE
from .pilotage import Pilotage
from .porte import Porte, PorteErreur
from .regles import Refus
from .releves import JOURS_LUS_MAX, rassembler
from .versions import Versions

log = logging.getLogger("megga.atelier")
ID = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
ESSAIS_PAR_JOUR = 200  # essais (mode d'essai) par agent et par jour
CONVERSATION = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


def trop_ancienne(agent: dict | None, schema_minimum: int) -> bool:
    """L'agent d'une installation, d'après son dernier relevé, sert-il une image d'avant ce schéma de nos tables ?
    Inconnu (pas de relevé, agent muet) : on ne sait pas, faux ; l'installation jugera l'ordre elle-même."""
    schema = (agent or {}).get("schema")
    return isinstance(schema, int) and not isinstance(schema, bool) and schema < schema_minimum


@dataclass(frozen=True)
class Identite:
    role: str  # « megga » ou « client »
    client: str | None = None


async def bd(f, *a, **k):
    """Un appel à la base, hors de la boucle : une lecture lente ne gèle pas les autres requêtes."""
    return await run_in_threadpool(f, *a, **k)


def creer(env: dict[str, str] | None = None, db=None, porte=None, principal_essai=None,
          transport_alertes=None, transport_stripe=None, transport_composio=None) -> FastAPI:
    """Les arguments nommés remplacent les vrais services (essais du code)."""
    from noyau.environnement import charger

    env = charger(dict(os.environ if env is None else env))
    os.environ.setdefault("AGNO_TELEMETRY", "false")
    admin = env.get("ADMIN_TOKEN", "")
    if not admin:
        raise RuntimeError("ADMIN_TOKEN manquant")
    if not env.get("DATABASE_URL"):
        raise RuntimeError("DATABASE_URL manquante")
    stockage.migrer(env["DATABASE_URL"])
    versions = Versions(db if db is not None else stockage.base_agno(env["DATABASE_URL"]))
    jetons = stockage.Jetons(env["DATABASE_URL"])
    reglages = stockage.Reglages(env["DATABASE_URL"])
    if porte is None and env.get("PORTE_URL"):
        porte = Porte(env["PORTE_URL"], admin)
    cles = {k: env.get(k, "") for k in CLES}
    essais = Path(env.get("ESSAIS_DIR") or Path(tempfile.gettempdir()) / "megga-essais")
    # La clé qui signe les ordres des installations hors Cloudflare ; illisible, l'atelier sert le reste.
    cle_pilotage = None
    if env.get("PILOTAGE_CLE"):
        try:
            cle_pilotage = pilotages.cle_privee(env["PILOTAGE_CLE"])
        except pilotages.PilotageRefuse:
            log.error("PILOTAGE_CLE illisible : aucun ordre de pilotage ne sera signé")
    canal = Pilotage(env["DATABASE_URL"], cle_pilotage)
    pilote_fenetres = (1, 7, 30)  # les périodes que le pilote calcule (pilote/service.py, FENETRES)
    # Une mise en service à la fois par client (l'atelier est un seul processus).
    verrous: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
    essais_du_jour: dict[tuple[str, str], int] = {}  # en mémoire : l'atelier est un seul processus

    def identite(requete: Request) -> Identite:
        jeton = (requete.headers.get("authorization") or "").removeprefix("Bearer ").strip()
        if jeton and hmac.compare_digest(jeton.encode(), admin.encode()):
            return Identite("megga")
        client = jetons.client(jeton)
        if client:
            return Identite("client", client)
        raise Refus(401, "jeton refusé")

    def megga(qui: Identite) -> None:
        if qui.role != "megga":
            raise Refus(403, "réservé à MEGGA")

    def client_de(qui: Identite, ident: str) -> dict:
        """Le client, s'il existe et si ce rôle peut le voir (un client ne voit que le sien)."""
        if not ID.fullmatch(ident) or (qui.role == "client" and qui.client != ident):
            raise Refus(404, "client inconnu")
        c = versions.client(ident)
        if c is None:
            raise Refus(404, "client inconnu")
        return c

    def version_de(ident: str, numero: int) -> dict:
        v = versions.version(ident, numero)
        if v is None:
            raise Refus(404, "version inconnue")
        return v

    def resume(c: dict, derniere: int | None, etats: dict | None, installation: dict | None = None) -> dict:
        meta = c.get("metadata") or {}
        r = {
            "id": c["component_id"],
            "nom_agent": c.get("name"),
            "entreprise": c.get("description"),
            "version_en_service": c.get("current_version"),
            "derniere_version": derniere,
            "gere_par_megga": bool(meta.get("gere_par_megga")),
        }
        if etats is not None:
            a = etats.get(c["component_id"])
            r["annuaire"] = a
            # Une mise en service interrompue : la porte sert une autre version que l'atelier.
            r["ecart"] = a is not None and a.get("version") != c.get("current_version")
        if installation is not None:  # hors Cloudflare : ce que sert l'installation, d'après son dernier relevé
            r["installation"] = installation
            r["ecart"] = installation["ecart"]
        return r

    def installation_de(ident: str, courante: int | None) -> dict | None:
        inst = canal.installations.lire(ident)
        return canal.bref(inst, courante) if inst else None

    async def etats_porte(ident: str | None = None) -> dict | None:
        if porte is None:
            return None
        try:
            return await porte.etats(ident)
        except PorteErreur as e:  # l'état de la porte n'empêche pas de lister
            log.warning("porte injoignable : %s", str(e)[:120])
            return None

    def zone_en_service(ident: str) -> str | None:
        v = versions.en_service(ident)
        return (v["config"] or {}).get("zone") if v else None

    def zone_de(ident: str) -> str | None:
        """La zone du client : celle de sa version en service, sinon de sa dernière version."""
        v = versions.en_service(ident) or versions.derniere(ident)
        return ((v or {}).get("config") or {}).get("zone")

    def nouvelle(qui: Identite, ident: str, corps: dict) -> tuple[Config, int]:
        """La configuration d'une nouvelle version, d'après sa base (la dernière par défaut)."""
        base_n = regles.numero(corps.get("base"), "base")
        base = version_de(ident, base_n) if base_n is not None else versions.derniere(ident)
        if base is None:
            raise Refus(404, "aucune version de base")
        changements = corps.get("changements")
        conf = regles.appliquer(qui.role, base["config"], {} if changements is None else changements, zone_en_service(ident))
        return conf, base["version"]

    def preparer(qui: Identite, ident: str, corps: dict) -> tuple[Config, int]:
        client_de(qui, ident)
        return nouvelle(qui, ident, corps)

    def config_de(v: dict) -> Config:
        """La configuration d'une version, revalidée par le code en service ; complète."""
        conf = regles.valider(v["config"])
        if regles.manques(conf):
            raise Refus(409, "version incomplète", regles.manques(conf))
        return conf

    r = APIRouter(prefix="/atelier")

    @r.get("/catalogue")
    def catalogue(qui: Identite = Depends(identite)):
        return regles.catalogue()

    @r.get("/clients")
    async def lister(qui: Identite = Depends(identite)):
        if qui.role == "megga":
            tous, etats = await bd(versions.clients), await etats_porte()
        else:
            tous = [c for c in [await bd(versions.client, qui.client)] if c]
            etats = await etats_porte(qui.client)
        dernieres = await bd(versions.dernieres, {c["component_id"] for c in tous}) if tous else {}
        courantes = {c["component_id"]: c.get("current_version") for c in tous}
        installations = {i["client"]: i for i in await bd(canal.toutes, courantes)}
        lus = await bd(pays.tous, reglages)
        return {"clients": [{**resume(c, dernieres.get(c["component_id"]), etats, installations.get(c["component_id"])),
                             "pays": lus.get(c["component_id"])} for c in tous],
                "porte": etats is not None}

    @r.get("/gabarits")
    def liste_gabarits(qui: Identite = Depends(identite)):
        return {"gabarits": gabarits.lister()}

    @r.post("/clients", status_code=201)
    def creer_client(qui: Identite = Depends(identite), corps: dict = Body(...)):
        megga(qui)
        if corps.get("gabarit") is not None:
            donnees = gabarits.nouvelle_config(corps["gabarit"], corps.get("client"), corps.get("nom_agent"))
        else:
            donnees = corps.get("config") or {}
        conf = regles.valider(donnees)
        if versions.db.get_component(conf.id, include_deleted=True) is not None:
            raise Refus(409, "ce client existe déjà")
        return {"client": conf.id, **versions.creer(conf, "megga")}

    @r.get("/clients/{ident}")
    async def lire(ident: str, qui: Identite = Depends(identite)):
        c = await bd(client_de, qui, ident)
        courante = c.get("current_version")
        config = (await bd(version_de, ident, courante))["config"] if courante else None
        derniere = (await bd(versions.dernieres, {ident})).get(ident)
        le_pays = (await bd(pays.tous, reglages)).get(ident)
        if ((config or {}).get("zone") or await bd(zone_de, ident)) in regles.ZONES_PORTE:
            return {**resume(c, derniere, await etats_porte(ident)), "pays": le_pays, "config": config}
        return {**resume(c, derniere, None, await bd(installation_de, ident, courante)), "pays": le_pays, "config": config}

    @r.put("/clients/{ident}/pays")
    def regler_pays(ident: str, qui: Identite = Depends(identite), corps: dict = Body(...)):
        """MEGGA : le pays du client sur la carte du monde (un code ISO à deux lettres, ou null)."""
        megga(qui)
        client_de(qui, ident)
        return {"client": ident, "pays": pays.regler(reglages, ident, corps.get("pays"))}

    @r.get("/clients/{ident}/versions")
    def historique(ident: str, qui: Identite = Depends(identite)):
        client_de(qui, ident)
        return {"versions": versions.historique(ident)}

    @r.get("/clients/{ident}/versions/{numero}")
    def version(ident: str, numero: int, qui: Identite = Depends(identite)):
        client_de(qui, ident)
        return version_de(ident, numero)

    @r.post("/clients/{ident}/valider")
    def valider(ident: str, qui: Identite = Depends(identite), corps: dict = Body(...)):
        conf, base = preparer(qui, ident, corps)
        return {"base": base, "config": conf.model_dump(mode="json"), "manques": regles.manques(conf)}

    @r.post("/clients/{ident}/versions", status_code=201)
    def ajouter(ident: str, qui: Identite = Depends(identite), corps: dict = Body(...)):
        conf, base = preparer(qui, ident, corps)
        v = versions.ajouter(conf, qui.role, base)
        return {**v, "manques": regles.manques(conf)}

    @r.post("/clients/{ident}/gabarit", status_code=201)
    def depuis_gabarit(ident: str, qui: Identite = Depends(identite), corps: dict = Body(...)):
        """Un modèle par métier appliqué à ce client : son identité et les réglages de MEGGA restent."""
        client_de(qui, ident)
        base_n = regles.numero(corps.get("base"), "base")
        base = version_de(ident, base_n) if base_n is not None else versions.derniere(ident)
        if base is None:
            raise Refus(404, "aucune version de base")
        changements = gabarits.reglages_pour(corps.get("gabarit"), base["config"])
        if qui.role == "client" and not regles.consignes_de_gabarit(base["config"].get("consignes", "")):
            changements.pop("consignes")  # celles que MEGGA a écrites sur mesure restent (relecture du 16.11.2026, I2)
        if corps.get("nom_agent") is not None:
            changements["nom_agent"] = corps["nom_agent"]
        conf = regles.valider(regles.fusionner(base["config"], changements))
        regles.verifier_zone(conf, zone_en_service(ident))
        v = versions.ajouter(conf, qui.role, base["version"])
        return {**v, "gabarit": corps["gabarit"], "manques": regles.manques(conf)}

    @r.post("/clients/{ident}/versions/{numero}/essai")
    async def essai(ident: str, numero: int, qui: Identite = Depends(identite), corps: dict = Body(...)):
        await bd(client_de, qui, ident)
        v = await bd(version_de, ident, numero)
        message = corps.get("message")
        if not isinstance(message, str) or not message.strip() or len(message) > 4000:
            raise Refus(400, "message : un texte de 1 à 4000 caractères")
        conversation = str(corps.get("conversation") or "1")
        if not CONVERSATION.fullmatch(conversation):
            raise Refus(400, "conversation : lettres, chiffres, - et _")
        conf = config_de(v)
        role = corps.get("role")
        if role is not None and not isinstance(role, str):
            raise Refus(400, "role : gestionnaire, partenaire ou visiteur")
        # Un essai coûte des jetons de modèle comme une vraie conversation : borné par client et par jour.
        jour = time.strftime("%Y-%m-%d")
        n = essais_du_jour.get((ident, jour), 0)
        if n >= ESSAIS_PAR_JOUR:
            raise Refus(429, f"{ESSAIS_PAR_JOUR} essais par jour au plus pour un agent : la suite demain")
        essais_du_jour[(ident, jour)] = n + 1
        try:
            reponse = await essayer(conf, numero, message, conversation, cles, essais, principal=principal_essai, role=role)
        except ValueError as e:
            raise Refus(400, str(e)) from e
        await bd(versions.noter_essai, ident, numero)
        return {"version": numero, "conversation": conversation, "reponse": reponse}

    @r.post("/clients/{ident}/versions/{numero}/activer")
    async def activer(ident: str, numero: int, qui: Identite = Depends(identite), corps: dict | None = Body(None)):
        forcer = regles.oui_non((corps or {}).get("forcer"), False, "forcer")
        async with verrous[ident]:
            c = await bd(client_de, qui, ident)
            v = await bd(version_de, ident, numero)
            if qui.role == "client":
                if (c.get("metadata") or {}).get("gere_par_megga"):
                    raise Refus(403, "MEGGA a repris la main sur cet agent : la mise en service passe par MEGGA")
                if forcer:
                    raise Refus(403, "forcer : réservé à MEGGA")
            courante = c.get("current_version")
            if qui.role == "client" and courante and courante != numero:
                en_service = await bd(version_de, ident, courante)
                if regles.reglages_de_megga(v["config"]) != regles.reglages_de_megga(en_service["config"]):
                    raise Refus(403, "cette version change des réglages de MEGGA (numéro WhatsApp, modèles Meta, gestion du site, "
                                     "consignes…) : sa mise en service passe par MEGGA")
            if courante == numero and v["config"].get("zone") in regles.ZONES_PORTE:
                # Déjà en service dans l'atelier ; mais si l'annuaire en sert une autre (mise en service interrompue,
                # inscription à la main), la relancer remet les deux d'accord (relecture du 16.11.2026).
                a = ((await etats_porte(ident)) or {}).get(ident)
                if a is None or a.get("version") == courante:
                    raise Refus(409, "cette version est déjà en service")
            if v["etat"] == "brouillon" and v["essais"] == 0 and not forcer:
                raise Refus(409, "essayez d'abord cette version (mode d'essai)")
            conf = config_de(v)
            avant = await bd(version_de, ident, courante) if courante else None
            regles.verifier_zone(conf, (avant["config"] or {}).get("zone") if avant else None)
            if conf.zone not in regles.ZONES_PORTE:
                # Suisse et installation chez le client : un ordre signé, remis par le pilotage.
                return await activer_hors_porte(qui, ident, numero, courante, conf, v)
            if porte is None:
                raise Refus(503, "porte non réglée (PORTE_URL)")
            try:
                annuaire = await porte.activer(conf, numero)
            except PorteErreur as e:
                if e.statut == 0:
                    raise Refus(504, "la porte n'a pas répondu : vérifiez l'écart dans la liste des clients avant de relancer",
                                {"texte": e.texte}) from e
                raise Refus(502, "la porte a refusé la mise en service", {"statut": e.statut, "texte": e.texte}) from e
            try:
                await bd(versions.mettre_en_service, ident, numero, courante)
            except Exception as e:
                # L'annuaire sert déjà la nouvelle version : on le remet sur celle d'avant.
                log.error("mise en service de %s v%s interrompue : %s", ident, numero, str(e)[:200])
                retabli = False
                if avant is not None:
                    try:
                        await porte.activer(regles.valider(avant["config"]), courante)
                        retabli = True
                    except (PorteErreur, Refus):
                        pass
                raise Refus(500, "mise en service interrompue", {"annuaire_retabli": retabli}) from e
        return {"client": ident, "version_en_service": numero, "retour": v["etat"] == "publiee", "annuaire": annuaire}

    async def activer_hors_porte(qui: Identite, ident: str, numero: int, courante: int | None, conf: Config, v: dict) -> dict:
        """Hors Cloudflare (chez le client, zone suisse) : la version est mise en service dans l'atelier, puis
        un ordre signé part à l'installation à son prochain relevé. Une version déjà en service peut être
        renvoyée si l'installation ne la sert pas (refusée, en échec, expirée)."""
        if conf.presentation:
            # Une image d'avant ce champ refuserait toute la configuration (Config refuse les champs inconnus).
            raise Refus(409, "la présentation de l'entreprise n'est pas encore servie hors Cloudflare : retirez-la de cette version")
        if canal.cle is None:
            raise Refus(503, "clé de pilotage absente : l'atelier ne peut pas signer d'ordre (scripts/pilotage.py poser)")
        if conf.whatsapp is None:
            # Deux versions soutenues : l'image précédente exige un numéro et refuserait l'ordre.
            agent = (await bd(installation_de, ident, courante) or {}).get("agent")
            if trop_ancienne(agent, SANS_WHATSAPP_SCHEMA):
                raise Refus(409, f"l'installation sert l'image {agent.get('version')}, qui exige un numéro WhatsApp : installez d'abord une image récente")
        en_cours = await bd(canal.en_cours, ident, numero)
        if en_cours is not None:
            raise Refus(409, f"l'ordre {en_cours} porte déjà cette version à l'installation")
        if courante == numero:
            inst = await bd(installation_de, ident, courante)
            if inst is not None and inst["releve"] is not None and inst["ecart"] is not True:
                # Servie, ou état inconnu (l'agent n'a pas répondu au dernier relevé) : rien à renvoyer pour l'instant.
                raise Refus(409, "cette version est déjà en service" if inst["ecart"] is False
                            else "l'installation n'a pas dit quelle version elle sert : attendez son prochain relevé")
        else:
            try:
                await bd(versions.mettre_en_service, ident, numero, courante)
            except Exception as e:
                log.error("mise en service de %s v%s interrompue : %s", ident, numero, str(e)[:200])
                raise Refus(500, "mise en service interrompue") from e
        try:
            ordre = await bd(canal.deposer, ident, "config", {"version": numero, "config": pilotages.config_a_envoyer(conf)}, qui.role)
        except Exception as e:
            log.error("ordre de %s v%s non déposé : %s", ident, numero, str(e)[:200])
            raise Refus(500, "version mise en service dans l'atelier, mais l'ordre n'est pas parti : relancez la mise en service") from e
        enregistree = await bd(canal.installations.cle, ident) is not None
        return {"client": ident, "version_en_service": numero, "retour": v["etat"] == "publiee",
                "annuaire": {"zone": conf.zone, "porte": False},
                "pilotage": {"ordre": ordre["numero"], "installation": enregistree}}

    @r.post("/clients/{ident}/reprise")
    def reprise(ident: str, qui: Identite = Depends(identite), corps: dict = Body(...)):
        megga(qui)
        client_de(qui, ident)
        meta = versions.regler(ident, gere_par_megga=regles.oui_non(corps.get("gere_par_megga"), True, "gere_par_megga"))
        return {"client": ident, "gere_par_megga": meta["gere_par_megga"]}

    @r.post("/clients/{ident}/jetons", status_code=201)
    def jeton(ident: str, qui: Identite = Depends(identite)):
        megga(qui)
        client_de(qui, ident)
        return {"client": ident, "jeton": jetons.creer(ident)}

    @r.delete("/clients/{ident}/jetons")
    def revoquer(ident: str, qui: Identite = Depends(identite)):
        megga(qui)
        client_de(qui, ident)
        return {"client": ident, "retires": jetons.revoquer(ident)}

    def lire_tarifs() -> Tarifs:
        return Tarifs.model_validate(reglages.lire("tarifs") or {})

    # Les clés d'API, le suivi et les installations hors Cloudflare : leurs modules de routes.
    routes_cles.monter(r, identite=identite, bd=bd, client_de=client_de, zone_de=zone_de, porte=porte)
    routes_composio.monter(r, identite=identite, megga=megga, bd=bd, client_de=client_de, cle=env.get("COMPOSIO_API_KEY"),
                           transport=transport_composio)
    routes_accueil.monter(r, identite=identite, bd=bd, client_de=client_de, versions=versions, reglages=reglages,
                          zone_en_service=zone_en_service, cles=cles, db_agno=versions.db, principal=principal_essai)
    routes_suivi.monter(r, identite=identite, bd=bd, client_de=client_de, zone_de=zone_de, porte=porte, versions=versions,
                        resume=resume, etats_porte=etats_porte, canal=canal, pilote_fenetres=pilote_fenetres,
                        lire_tarifs=lire_tarifs)
    routes_installations.monter(r, identite=identite, megga=megga, bd=bd, client_de=client_de, zone_de=zone_de, canal=canal,
                                versions=versions, verrous=verrous)

    @r.get("/releves")
    async def releves(requete: Request, qui: Identite = Depends(identite)):
        megga(qui)
        brut = requete.query_params.get("jours") or "7"
        if not re.fullmatch(r"[0-9]{1,2}", brut, re.ASCII) or not 1 <= int(brut) <= JOURS_LUS_MAX:
            raise Refus(400, f"jours : de 1 à {JOURS_LUS_MAX}")
        return await rassembler_tout(int(brut))

    async def rassembler_tout(jours: int) -> dict:
        """Le relevé de tous les agents, avec coûts, écart et silence (aucun conteneur réveillé)."""
        if porte is None:
            raise Refus(503, "porte non réglée (PORTE_URL)")
        try:
            lus = await porte.releves(jours)
        except PorteErreur as e:
            raise Refus(502, f"porte : {e.texte[:120]}") from e
        connus = {c["component_id"]: {"entreprise": c.get("description"), "version_en_service": c.get("current_version")}
                  for c in await bd(versions.clients)}
        return rassembler(lus, await bd(lire_tarifs), connus, time.time())

    routes_alertes.monter(r, identite=identite, megga=megga, bd=bd, reglages=reglages,
                          etats=EtatsAlertes(env["DATABASE_URL"]), porte=porte, rassembler_tout=rassembler_tout,
                          transport=transport_alertes)
    abonnements = Abonnements(env["DATABASE_URL"])
    routes_forfaits.monter(r, identite=identite, megga=megga, bd=bd, reglages=reglages,
                           abonnements=abonnements, client_de=client_de, rassembler_tout=rassembler_tout)

    @r.get("/tarifs")
    def tarifs(qui: Identite = Depends(identite)):
        megga(qui)
        return lire_tarifs().model_dump()

    @r.put("/tarifs")
    def regler_tarifs(qui: Identite = Depends(identite), corps: dict = Body(...)):
        megga(qui)
        try:
            t = Tarifs.model_validate(corps)
        except ValidationError as e:
            raise Refus(422, "tarifs invalides", regles.erreurs(e)) from e
        reglages.ecrire("tarifs", t.model_dump())
        return t.model_dump()

    app = FastAPI(title="megga-atelier", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.versions = versions
    app.state.jetons = jetons

    @app.exception_handler(Refus)
    async def refus(_: Request, e: Refus):
        corps = {"erreur": e.message}
        if e.details is not None:
            corps["details"] = e.details
        return JSONResponse(corps, status_code=e.statut)

    @app.get("/sante")
    async def sante():
        from noyau.version import carte

        return {"ok": True, "service": "atelier", **carte(), "pilotage": canal.cle is not None}

    @app.post("/pilotage/releve")
    async def releve(requete: Request):
        """Le relevé du pilote d'une installation : pas de jeton, une requête signée de sa clé."""
        # Lu par morceaux, borné : un corps trop gros est refusé sans être gardé en mémoire.
        corps = bytearray()
        async for morceau in requete.stream():
            corps += morceau
            if len(corps) > TAILLE_RELEVE:
                return JSONResponse({"erreur": "relevé trop gros"}, status_code=413)
        corps = bytes(corps)
        try:
            return await bd(canal.releve, "POST", "/pilotage/releve", requete.headers, corps)
        except pilotages.PilotageRefuse as e:
            log.warning("relevé refusé : %s", e)
            # Au pilote, l'heure et le rejeu se disent ; le reste (installation inconnue, révoquée, signature)
            # reste dans le journal de l'atelier : on ne peut pas sonder quelles installations existent.
            dicible = str(e) if str(e).startswith(("heure", "requête rejouée", "relevé")) else "installation non reconnue"
            return JSONResponse({"erreur": dicible}, status_code=401)

    # Stripe (atelier/routes_stripe.py) : sa route d'événements est hors de /atelier, sans jeton mais signée.
    stripe = Stripe(env["STRIPE_CLE"], transport_stripe) if env.get("STRIPE_CLE") else None
    routes_stripe.monter(app, r, identite=identite, megga=megga, bd=bd, reglages=reglages, abonnements=abonnements,
                         client_de=client_de, rassembler_tout=rassembler_tout, stripe=stripe, secret=env.get("STRIPE_SIGNATURE"))
    app.include_router(r)
    return app


def principal() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    uvicorn.run(creer(), host="0.0.0.0", port=int(os.environ.get("PORT", "8080")), access_log=False)
