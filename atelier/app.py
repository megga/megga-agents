"""L'API de l'atelier. Pas d'écran : l'interface viendra au dernier lot et ne fera que l'appeler.

Variables d'environnement (jamais dans le dépôt) :
  DATABASE_URL       la base de l'atelier (versions des configurations, jetons des clients)
  ADMIN_TOKEN        le jeton de MEGGA (le même que celui de la porte)
  PORTE_URL          l'adresse de la porte, pour l'annuaire et les conteneurs
  ANTHROPIC_API_KEY, DEEPSEEK_API_KEY   les modèles, pour le mode d'essai
  ESSAIS_DIR         facultatif : le dossier des bases d'essai
  PILOTAGE_CLE       la clé privée de pilotage : elle signe les ordres des installations hors Cloudflare

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

Suivi (lu dans le conteneur du client, qui se réveille s'il dormait) :
  GET   /clients/{id}/suivi[?jours=7]           état, activité (tours, personnes, modèles, voix) ;
                                                coûts pour MEGGA seulement
  GET   /clients/{id}/conversations[?limite=]   les personnes qui ont écrit
  GET   /clients/{id}/conversations/{personne}  les derniers échanges avec elle
  GET   /clients/{id}/alertes[?jours=7]         échecs, pannes du conteneur, écart avec l'annuaire
  GET   /tarifs, PUT /tarifs                    MEGGA : les tarifs des modèles et de la voix

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
import json
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

from noyau import api as entree_api
from noyau import pilotage as pilotages
from noyau import stockage
from noyau.app import CLES
from noyau.config import SANS_WHATSAPP_SCHEMA, Config
from noyau.suivi import PERSONNE

ETATS_APPROBATION = ("attente", "accordee", "faite", "echec", "refusee", "expiree")

from . import gabarits, regles
from .couts import Tarifs, couts
from .essai import essayer
from .pilotage import TAILLE as TAILLE_RELEVE
from .pilotage import Pilotage
from .porte import Porte, PorteErreur
from .regles import Refus
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


def creer(env: dict[str, str] | None = None, db=None, porte=None, principal_essai=None, juge_banc=None) -> FastAPI:
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
        return {"clients": [resume(c, dernieres.get(c["component_id"]), etats, installations.get(c["component_id"])) for c in tous],
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
        if ((config or {}).get("zone") or await bd(zone_de, ident)) in regles.ZONES_PORTE:
            return {**resume(c, derniere, await etats_porte(ident)), "config": config}
        return {**resume(c, derniere, None, await bd(installation_de, ident, courante)), "config": config}

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

    @r.post("/clients/{ident}/versions/{numero}/banc")
    async def banc_d_essai(ident: str, numero: int, qui: Identite = Depends(identite), corps: dict | None = Body(None)):
        """Le banc d'essai d'une version (lot 9.6, noyau/banc.py) : les scénarios de son métier, chacun k fois (1 à 5,
        3 par défaut), notés en pass^k. Il appelle les modèles pour de vrai : réservé à MEGGA. Le score d'un brouillon
        est gardé avec lui."""
        from noyau import banc

        megga(qui)
        k = (corps or {}).get("k", 3)
        if isinstance(k, bool) or not isinstance(k, int) or not 1 <= k <= banc.K_MAX:
            raise Refus(400, f"k : un nombre de 1 à {banc.K_MAX}")
        v = await bd(version_de, ident, numero)
        conf = config_de(v)
        juger = juge_banc or banc.juge_anthropic(env.get("BANC_JUGE") or "claude-sonnet-5-5", cles.get("ANTHROPIC_API_KEY", ""))
        rapport = await banc.passer(conf, banc.agent_d_essai(cles, principal=principal_essai), juger, k)
        resume = {**{c: rapport[c] for c in ("k", "cas", "tenus", "score", "pass_1")}, "quand": time.time()}
        await bd(versions.noter_banc, ident, numero, resume)
        return {"version": numero, **rapport}

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

    # L'entrée par API : les clés des logiciels

    def cles_par_porte(qui: Identite, ident: str) -> None:
        c = client_de(qui, ident)
        if zone_de(ident) not in regles.ZONES_PORTE:
            raise Refus(409, "hors Cloudflare, les clés se créent chez le client : python -m noyau.cles creer <logiciel> (docs/api.md)")
        if porte is None:
            raise Refus(503, "porte non réglée (PORTE_URL)")
        if c.get("current_version") is None:
            raise Refus(409, "mettez d'abord une version de l'agent en service : ses clés se gardent dans sa base")

    async def appel_cles(ident: str, methode: str = "GET", chemin: str = "", corps: dict | None = None) -> dict:
        try:
            return await porte.cles(ident, methode, chemin, corps)
        except PorteErreur as e:
            if e.statut in (400, 404, 409):
                raise Refus(e.statut, "clé refusée par le conteneur", {"texte": e.texte}) from e
            raise Refus(502 if e.statut else 504, f"clés indisponibles : {raison(e)}", {"statut": e.statut, "texte": e.texte}) from e

    @r.get("/clients/{ident}/cles")
    async def lister_cles(ident: str, qui: Identite = Depends(identite)):
        await bd(cles_par_porte, qui, ident)
        return {"client": ident, **await appel_cles(ident)}

    @r.post("/clients/{ident}/cles", status_code=201)
    async def creer_cle(ident: str, qui: Identite = Depends(identite), corps: dict = Body(...)):
        """Une clé pour un logiciel du client : montrée ici une seule fois ; seule son empreinte part au conteneur."""
        logiciel = corps.get("logiciel")
        if not isinstance(logiciel, str) or not entree_api.LOGICIEL.fullmatch(logiciel):
            raise Refus(400, "logiciel : un nom court, en minuscules (lettres, chiffres, tirets, 20 au plus)")
        try:
            debit = entree_api.par_minute(corps.get("par_minute"))
        except ValueError as e:
            raise Refus(400, str(e)) from e
        if qui.role == "client" and debit > entree_api.PAR_MINUTE:
            # Le débit protège la facture des modèles : au-delà du débit par défaut, c'est à MEGGA de le régler.
            raise Refus(403, f"par_minute : au plus {entree_api.PAR_MINUTE} ; davantage se demande à MEGGA")
        await bd(cles_par_porte, qui, ident)
        if qui.role == "client":
            en_service = [c for c in (await appel_cles(ident)).get("cles", []) if not c.get("retiree")]
            if len(en_service) >= entree_api.CLES_CLIENT_MAX:
                raise Refus(409, f"{entree_api.CLES_CLIENT_MAX} clés en service au plus : retirez-en une, ou demandez à MEGGA")
        cle_id, cle, empreinte = entree_api.nouvelle_cle()
        await appel_cles(ident, "POST", corps={"id": cle_id, "logiciel": logiciel, "empreinte": empreinte, "par_minute": debit})
        log.info("clé %s créée pour %s (%s, %s)", cle_id, ident, logiciel, qui.role)
        return {"client": ident, "id": cle_id, "logiciel": logiciel, "par_minute": debit, "cle": cle}

    @r.delete("/clients/{ident}/cles/{cle_id}")
    async def retirer_cle(ident: str, cle_id: str, qui: Identite = Depends(identite)):
        if not entree_api.IDENT_CLE.fullmatch(cle_id):
            raise Refus(400, "identifiant de clé")
        await bd(cles_par_porte, qui, ident)
        r = await appel_cles(ident, "DELETE", f"/{cle_id}")
        log.info("clé %s de %s retirée (%s)", cle_id, ident, qui.role)
        return {"client": ident, **r}

    # Le suivi

    def jours_de(valeur: str | None) -> int:
        try:
            jours = int(valeur or 7)
        except ValueError:
            raise Refus(400, "jours : un nombre de 1 à 365") from None
        if not 1 <= jours <= 365:
            raise Refus(400, "jours : un nombre de 1 à 365")
        return jours

    def limite_de(valeur: str | None) -> int | None:
        if valeur is None:
            return None
        if not valeur.isdigit() or not 1 <= int(valeur) <= 200:
            raise Refus(400, "limite : un nombre de 1 à 200")
        return int(valeur)

    def suivable(qui: Identite, ident: str, conversations: bool = False) -> tuple[dict, bool]:
        """Le client, et si son suivi passe par la porte (zones Europe et États-Unis) ou par le pilotage
        (hors Cloudflare : le dernier relevé de son installation, jamais ses conversations)."""
        c = client_de(qui, ident)
        if zone_de(ident) not in regles.ZONES_PORTE:
            if conversations:
                raise Refus(409, "les conversations d'une installation hors Cloudflare ne la quittent jamais : elles se lisent chez le client")
            return c, False
        if porte is None:
            raise Refus(503, "porte non réglée (PORTE_URL)")
        return c, True

    def raison(e: PorteErreur) -> str:
        """Ce qui a empêché la lecture, dit simplement."""
        if e.statut == 0:
            return "la porte n'a pas répondu"
        if e.statut == 401:
            return "le conteneur refuse la lecture (jeton interne : le jeton d'administration a-t-il changé ?)"
        try:
            erreur = json.loads(e.texte).get("erreur")
        except (ValueError, AttributeError):
            erreur = None
        if erreur == "conteneur injoignable":
            return "le conteneur du client ne répond pas"
        if erreur == "suivi indisponible" or "suivi indisponible" in e.texte:
            return "le conteneur répond, mais sa base n'est pas branchée"
        return f"réponse inattendue du conteneur ({e.statut})"

    async def lire_suivi(ident: str, chemin: str = "", **params) -> dict:
        try:
            return await porte.suivi(ident, chemin, **params)
        except PorteErreur as e:
            if e.statut in (400, 404):
                raise Refus(e.statut, "suivi refusé", {"texte": e.texte}) from e
            raise Refus(502 if e.statut else 504, f"suivi indisponible : {raison(e)}",
                        {"statut": e.statut, "texte": e.texte}) from e

    def debut(jours: int) -> int:
        """Le début de la période, arrondi à 5 minutes : des lectures rapprochées tombent sur la lecture
        gardée en mémoire par la porte, sans réveiller le conteneur du client."""
        return int((time.time() - jours * 86400) // 300 * 300)

    def lire_tarifs() -> Tarifs:
        return Tarifs.model_validate(reglages.lire("tarifs") or {})

    @r.get("/clients/{ident}/suivi")
    async def suivi(ident: str, requete: Request, qui: Identite = Depends(identite)):
        jours = jours_de(requete.query_params.get("jours"))
        c, par_porte = await bd(suivable, qui, ident)
        derniere = (await bd(versions.dernieres, {ident})).get(ident)
        if par_porte:
            activite = await lire_suivi(ident, depuis=debut(jours))
            sortie = {**resume(c, derniere, await etats_porte(ident)), "periode_jours": jours, "activite": activite}
        else:
            if jours not in pilote_fenetres:
                raise Refus(400, "jours : 1, 7 ou 30 pour une installation hors Cloudflare")
            try:
                activite, inst = await bd(canal.suivi, ident, jours)
            except pilotages.PilotageRefuse as e:
                raise Refus(409, f"suivi indisponible : {e}") from e
            sortie = {**resume(c, derniere, None, canal.bref(inst, c.get("current_version"))), "periode_jours": jours,
                      "activite": activite}
        if qui.role == "megga":
            try:
                sortie["couts"] = couts(activite, await bd(lire_tarifs))
            except (TypeError, ValueError, AttributeError, ArithmeticError):
                if par_porte:
                    raise
                sortie["couts"] = {"erreur": "activité illisible"}  # le relevé d'une installation, pas notre code
        return sortie

    @r.get("/clients/{ident}/conversations")
    async def conversations(ident: str, requete: Request, qui: Identite = Depends(identite)):
        limite = limite_de(requete.query_params.get("limite"))
        await bd(suivable, qui, ident, True)
        return await lire_suivi(ident, "/conversations", limite=limite)

    @r.get("/clients/{ident}/conversations/{personne}")
    async def echanges(ident: str, personne: str, requete: Request, qui: Identite = Depends(identite)):
        limite = limite_de(requete.query_params.get("limite"))
        if not PERSONNE.fullmatch(personne):
            raise Refus(400, "personne : un numéro, ou api:<logiciel>:<identifiant>")
        await bd(suivable, qui, ident, True)
        return await lire_suivi(ident, f"/conversations/{personne}", limite=limite)

    @r.get("/clients/{ident}/alertes")
    async def alertes(ident: str, requete: Request, qui: Identite = Depends(identite)):
        jours = jours_de(requete.query_params.get("jours"))
        c, par_porte = await bd(suivable, qui, ident)
        maintenant = time.time()
        depuis = debut(jours)
        if not par_porte:
            liste = await bd(canal.alertes, ident, depuis, c.get("current_version"))
            return {"periode_jours": jours, "alertes": sorted(liste, key=lambda x: x["quand"] or 0, reverse=True)}
        liste = []
        etats = await etats_porte(ident)
        if etats is None:
            liste.append({"quand": maintenant, "genre": "porte_injoignable", "detail": ""})
        else:
            a = etats.get(ident) or {}
            if a and a.get("version") != c.get("current_version"):
                liste.append({"quand": maintenant, "genre": "ecart",
                              "detail": f"l'annuaire sert la version {a.get('version')}, l'atelier la {c.get('current_version')}"})
            for panne in (a.get("conteneur") or {}).get("alertes") or []:
                if panne.get("quand", 0) / 1000 >= depuis:
                    resolue = panne.get("resolue")
                    liste.append({"quand": panne["quand"] / 1000, "genre": f"conteneur_{panne.get('quoi')}",
                                  "detail": panne.get("message", ""), "resolue": resolue / 1000 if resolue else None})
        try:
            liste += (await lire_suivi(ident, "/alertes", depuis=depuis)).get("alertes", [])
        except Refus as e:
            liste.append({"quand": maintenant, "genre": "conteneur_injoignable", "detail": e.message})
        return {"periode_jours": jours, "alertes": sorted(liste, key=lambda x: x["quand"], reverse=True)}

    # Les approbations et le journal d'audit des outils (lot 9.1, noyau/approbations.py). Comme les conversations,
    # ils ne quittent jamais une installation hors Cloudflare : elle décide sur WhatsApp, par ses gestionnaires.

    @r.get("/clients/{ident}/audit")
    async def audit(ident: str, requete: Request, qui: Identite = Depends(identite)):
        """Chaque appel d'outil de la période : l'outil, la personne, la règle, l'issue, la durée."""
        jours = jours_de(requete.query_params.get("jours"))
        await bd(suivable, qui, ident, True)
        lu = await lire_suivi(ident, "/audit", depuis=debut(jours), limite=limite_de(requete.query_params.get("limite")))
        return {"periode_jours": jours, **lu}

    @r.get("/clients/{ident}/approbations")
    async def approbations(ident: str, requete: Request, qui: Identite = Depends(identite)):
        """Les demandes d'accord, les plus récentes d'abord ; `etat=attente` : celles à décider."""
        etat = requete.query_params.get("etat")
        if etat is not None and etat not in ETATS_APPROBATION:
            raise Refus(400, "etat : " + ", ".join(ETATS_APPROBATION))
        await bd(suivable, qui, ident, True)
        return await lire_suivi(ident, "/approbations", etat=etat, limite=limite_de(requete.query_params.get("limite")))

    @r.post("/clients/{ident}/approbations/{numero}")
    async def decider(ident: str, numero: int, qui: Identite = Depends(identite), corps: dict = Body(...)):
        """{accord: true|false} : l'action accordée est faite tout de suite, au nom de la personne qui l'a demandée."""
        accord = corps.get("accord")
        if not isinstance(accord, bool):
            raise Refus(400, "accord : true ou false")
        await bd(suivable, qui, ident, True)
        try:
            return await porte.decider(ident, numero, accord)
        except PorteErreur as e:
            if e.statut in (400, 404, 409):
                raise Refus(e.statut, "décision refusée", {"texte": e.texte}) from e
            raise Refus(502 if e.statut else 504, f"décision non transmise : {raison(e)}", {"statut": e.statut}) from e
    # Le transfert vers un humain (lot 9.3, noyau/reprises.py) : la console prend une conversation, répond du numéro de
    # l'entreprise, puis la rend à l'agent. Comme les conversations, rien ne quitte une installation hors Cloudflare.

    # Le client et ses chiffres (lot 9.5) : ce que l'agent lui fait gagner, et les droits des personnes (nLPD, RGPD).

    @r.get("/clients/{ident}/valeur")
    async def valeur(ident: str, requete: Request, qui: Identite = Depends(identite)):
        """Ce que l'agent a fait gagner sur la période : conversations, part résolue sans humain, leads, minutes gagnées."""
        jours = jours_de(requete.query_params.get("jours"))
        await bd(suivable, qui, ident, True)
        return {"periode_jours": jours, **await lire_suivi(ident, "/valeur", depuis=debut(jours))}

    async def droits(qui: Identite, ident: str, methode: str, personne: str) -> dict:
        if not PERSONNE.fullmatch(personne):
            raise Refus(400, "personne : un numéro, ou api:<logiciel>:<identifiant>")
        await bd(suivable, qui, ident, True)
        try:
            return await porte.personne(ident, methode, personne)
        except PorteErreur as e:
            if e.statut in (400, 404):
                raise Refus(e.statut, "personne refusée", {"texte": e.texte}) from e
            raise Refus(502 if e.statut else 504, f"données injoignables : {raison(e)}") from e

    @r.get("/clients/{ident}/personnes/{personne}")
    async def donnees_personne(ident: str, personne: str, qui: Identite = Depends(identite)):
        """Tout ce que la base du client garde d'une personne, à lui remettre (son droit d'accès)."""
        return await droits(qui, ident, "GET", personne)

    @r.delete("/clients/{ident}/personnes/{personne}")
    async def effacer_personne(ident: str, personne: str, requete: Request, qui: Identite = Depends(identite)):
        """Efface tout ce que la base garde d'une personne, à sa demande ; `?confirmer=oui`, rien ne se récupère."""
        if requete.query_params.get("confirmer") != "oui":
            raise Refus(400, "l'effacement est définitif : confirmez avec ?confirmer=oui")
        return await droits(qui, ident, "DELETE", personne)

    @r.get("/clients/{ident}/leads")
    async def leads(ident: str, requete: Request, qui: Identite = Depends(identite)):
        """Les leads de la période (lot 9.4, noyau/connecteurs.py) et ce qu'est devenu leur envoi au webhook du client."""
        jours = jours_de(requete.query_params.get("jours"))
        await bd(suivable, qui, ident, True)
        lu = await lire_suivi(ident, "/leads", depuis=debut(jours), limite=limite_de(requete.query_params.get("limite")))
        return {"periode_jours": jours, **lu}

    @r.get("/clients/{ident}/reprises")
    async def reprises(ident: str, requete: Request, qui: Identite = Depends(identite)):
        """Les conversations confiées à l'équipe ; `etat=ouverte` : celles que personne n'a encore prises."""
        etat = requete.query_params.get("etat")
        if etat is not None and etat not in ("ouverte", "prise", "rendue", "expiree"):
            raise Refus(400, "etat : ouverte, prise, rendue, expiree")
        await bd(suivable, qui, ident, True)
        return await lire_suivi(ident, "/reprises", etat=etat, limite=limite_de(requete.query_params.get("limite")))

    @r.post("/clients/{ident}/reprises/{numero}")
    async def reprendre(ident: str, numero: int, qui: Identite = Depends(identite), corps: dict = Body(...)):
        """{action: prendre | message | rendre, texte?} : la réponse part du numéro de l'entreprise."""
        action, texte = corps.get("action"), corps.get("texte", "")
        if action not in ("prendre", "message", "rendre") or not isinstance(texte, str) or (action == "message" and not texte.strip()):
            raise Refus(400, "{action: prendre | message | rendre, texte (pour un message)}")
        await bd(suivable, qui, ident, True)
        try:
            return await porte.reprise(ident, numero, {"action": action, "texte": texte})
        except PorteErreur as e:
            if e.statut in (400, 404, 409):
                raise Refus(e.statut, "action refusée", {"texte": e.texte}) from e
            raise Refus(502 if e.statut else 504, f"action non transmise : {raison(e)}", {"statut": e.statut}) from e

    # La base de connaissances (lot 9.2, noyau/connaissances.py) : les documents restent dans la base du client ; hors
    # Cloudflare, ils s'ajoutent sur son serveur (python -m noyau.connaissances), rien n'entrant chez lui.

    async def base_du_client(qui: Identite, ident: str, methode: str, chemin: str = "", corps: dict | None = None) -> dict:
        await bd(suivable, qui, ident, True)
        try:
            return await porte.connaissances(ident, methode, chemin, corps)
        except PorteErreur as e:
            if e.statut in (400, 404, 409, 413):
                try:
                    message = json.loads(e.texte).get("erreur") or e.texte
                except (ValueError, AttributeError):
                    message = e.texte
                raise Refus(e.statut, str(message)[:300]) from e
            raise Refus(502 if e.statut else 504, f"base de connaissances injoignable : {raison(e)}") from e

    @r.get("/clients/{ident}/connaissances")
    async def documents(ident: str, qui: Identite = Depends(identite)):
        """Les documents de la base de connaissances du client."""
        return await base_du_client(qui, ident, "GET")

    @r.post("/clients/{ident}/connaissances", status_code=201)
    async def ajouter_document(ident: str, qui: Identite = Depends(identite), corps: dict = Body(...)):
        """{titre, genre (texte, pdf, html), texte ou base64, source?} : lu, découpé et rangé dans la base du client."""
        if set(corps) - {"titre", "genre", "texte", "base64", "source"} or not isinstance(corps.get("titre"), str):
            raise Refus(400, "{titre, genre (texte, pdf, html), texte ou base64, source?}")
        return await base_du_client(qui, ident, "POST", corps=corps)

    @r.delete("/clients/{ident}/connaissances/{numero}")
    async def retirer_document(ident: str, numero: int, qui: Identite = Depends(identite)):
        return await base_du_client(qui, ident, "DELETE", f"/{int(numero)}")

    # Les installations hors Cloudflare

    def hors_porte(qui: Identite, ident: str) -> dict:
        """Le client, s'il tourne hors Cloudflare (chez lui, zone suisse) : son installation se pilote."""
        c = client_de(qui, ident)
        if zone_de(ident) in regles.ZONES_PORTE:
            raise Refus(409, "ce client est servi par la porte de Cloudflare : il n'a pas d'installation à piloter")
        return c

    @r.get("/installations")
    def installations(qui: Identite = Depends(identite)):
        megga(qui)
        # cle_pilotage : l'atelier a sa clé et peut signer des ordres (scripts/pilotage.py poser).
        return {"installations": canal.toutes({c["component_id"]: c.get("current_version") for c in versions.clients()}),
                "cle_pilotage": canal.cle is not None}

    @r.get("/clients/{ident}/installation")
    def installation(ident: str, qui: Identite = Depends(identite)):
        c = hors_porte(qui, ident)
        return {"client": ident, "version_en_service": c.get("current_version"), **canal.vue(ident, c.get("current_version"))}

    @r.put("/clients/{ident}/installation")
    def enregistrer_installation(ident: str, qui: Identite = Depends(identite), corps: dict = Body(...)):
        """La mise en service d'une installation : MEGGA enregistre la clé publique qu'elle lui a remise."""
        megga(qui)
        hors_porte(qui, ident)
        try:
            empreinte = canal.enregistrer(ident, corps.get("cle_publique"))
        except pilotages.PilotageRefuse as e:
            raise Refus(400, str(e)) from e
        return {"client": ident, "cle": empreinte}

    @r.delete("/clients/{ident}/installation")
    def revoquer_installation(ident: str, qui: Identite = Depends(identite)):
        megga(qui)
        hors_porte(qui, ident)
        return {"client": ident, "revoquee": canal.revoquer(ident)}

    @r.post("/clients/{ident}/installation/image", status_code=201)
    async def proposer_image(ident: str, qui: Identite = Depends(identite), corps: dict = Body(...)):
        """Une version d'image pour l'installation : son pilote la vérifie et l'installe (MISES_A_JOUR=oui), sinon la propose."""
        megga(qui)
        await bd(hors_porte, qui, ident)
        contenu = {"version": corps.get("version"), "image": corps.get("image")}
        if not (isinstance(contenu["version"], str) and pilotages.VERSION_IMAGE.fullmatch(contenu["version"])):
            raise Refus(400, "version : celle de l'image, par exemple 0.2.0")
        if not (isinstance(contenu["image"], str) and pilotages.IMAGE.fullmatch(contenu["image"])):
            raise Refus(400, "image : ghcr.io/megga/megga-agents@sha256:<empreinte>, l'image signée par MEGGA")
        if canal.cle is None:
            raise Refus(503, "clé de pilotage absente : l'atelier ne peut pas signer d'ordre (scripts/pilotage.py poser)")
        async with verrous[ident]:
            ordre = await bd(canal.deposer, ident, "image", contenu, qui.role)
        return {"client": ident, "ordre": ordre["numero"], **contenu}

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

    app.include_router(r)
    return app


def principal() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    uvicorn.run(creer(), host="0.0.0.0", port=int(os.environ.get("PORT", "8080")), access_log=False)
