"""Le pilote d'une installation hors Cloudflare (chez le client, puis la zone suisse).

Un petit service à côté de l'agent, la même image (MEGGA_SERVICE=pilote). Toujours sortant : à chaque
relevé, il appelle MEGGA en HTTPS par une requête signée de la clé de l'installation ; aucun port
n'est ouvert chez le client. Le protocole est dans noyau/pilotage.py.

Ce qui sort, selon PILOTAGE :
  non      rien (par défaut)
  suivi    l'état (agent, version, licence, configuration servie), les volumes, les modèles et leurs
           jetons, les échecs : jamais une conversation, un texte ni un numéro
  complet  le suivi, et MEGGA peut envoyer des ordres signés : une version de configuration de
           l'atelier, que l'agent prend à son redémarrage, ou une version d'image proposée (notée
           seulement : son installation viendra au lot 6.4)
Avec PILOTAGE_ACCORD=oui (par défaut), chaque ordre attend l'accord du client (python -m pilote).

Ses seuls secrets : sa clé et la base de l'installation ; ni les clés des modèles ni celles de Meta.

Variables :
  PILOTAGE             non, suivi ou complet
  PILOTAGE_ACCORD      oui ou non
  PILOTAGE_URL         l'adresse de MEGGA (https)
  PILOTE_CLE           la clé de l'installation (ou PILOTE_CLE_FILE), créée chez le client
  DATABASE_URL         la base de l'installation, celle de l'agent
  CLIENT_CONFIG_FILE   la configuration de départ (client.yaml)
  AGENT_URL            l'agent, pour son état ; http://agent:8080 par défaut
  PILOTAGE_INTERVALLE  les secondes entre deux relevés ; 60 par défaut
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import re
import signal
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from noyau import config as configuration
from noyau import pilotage, stockage
from noyau import suivi as suivi_agent
from noyau.config import Config
from noyau.environnement import charger
from noyau.version import revision, version

from .sonde import en_vie, vivant  # noqa: F401 (en_vie réexporté)

log = logging.getLogger("megga.pilote")

MODES = ("non", "suivi", "complet")
PROTOCOLE = 1
PERIODE_SUIVI = 300  # le suivi (volumes, modèles, alertes) part toutes les 5 minutes ; l'état, à chaque relevé
DELAI_APPLICATION = 600  # l'agent a 10 minutes pour servir une nouvelle configuration, sinon retour à la précédente
FENETRES = (1, 7, 30)  # les périodes du suivi, en jours
# Ce que le pilote retient de /sante (rien de privé n'y est ; on ne garde que ce qu'on connaît).
SANTE = ("ok", "version", "revision", "config", "schema", "installation", "zone", "licence", "configuration")


class PiloteErreur(RuntimeError):
    pass


def oui(valeur: str | None, nom: str, defaut: bool) -> bool:
    v = (valeur or "").strip().lower()
    if not v:
        return defaut
    if v in ("oui", "true", "1"):
        return True
    if v in ("non", "false", "0"):
        return False
    raise RuntimeError(f"{nom} : oui ou non")


def adresse(url: str) -> str:
    """L'adresse de MEGGA : https ; http seulement vers un nom local, pour les essais (http://atelier:8080)."""
    u = urlsplit((url or "").strip())
    # Un nom de service du réseau local (atelier, localhost), jamais une adresse qui mènerait au dehors.
    local = u.hostname == "127.0.0.1" or bool(re.fullmatch(r"[a-z][a-z0-9-]{0,62}", u.hostname or ""))
    if (u.scheme == "https" and u.hostname) or (u.scheme == "http" and local):
        return url.strip().rstrip("/")
    raise RuntimeError("PILOTAGE_URL : l'adresse https de MEGGA")


def source_config(env: dict) -> str:
    """La configuration de départ, lue comme l'agent la lit (noyau/app.py) : CLIENT_CONFIG, sinon CLIENT_CONFIG_FILE."""
    source = env.get("CLIENT_CONFIG") or env.get("CLIENT_CONFIG_FILE")
    if not source:
        raise RuntimeError("CLIENT_CONFIG_FILE manquante")
    return source


class Installation:
    """Ce que le pilote tient dans la base de l'installation : les ordres reçus et le journal du pilotage."""

    def __init__(self, url: str, base: Config, cle_megga=None, horloge=time.time):
        self.url, self.base, self.cle_megga, self.horloge = url, base, cle_megga, horloge
        self.client = base.id
        self._ordres: stockage.Ordres | None = None
        self._journal: stockage.JournalPilotage | None = None
        self._lecture = None
        # Les ordres qu'on n'a pas pu ouvrir (signature, autre client), par numéro annoncé : dits à MEGGA,
        # jamais notés parmi les ordres (un numéro non signé ne doit rien décaler).
        self.refus: dict[int, dict] = {}

    def prete(self) -> bool:
        """La base a été migrée par l'agent : le pilote peut y tenir ses tables."""
        return stockage.migree(self.url)

    @property
    def ordres(self) -> stockage.Ordres:
        if self._ordres is None:
            self._ordres = stockage.Ordres(self.url)
        return self._ordres

    @property
    def journal(self) -> stockage.JournalPilotage:
        if self._journal is None:
            self._journal = stockage.JournalPilotage(self.url)
        return self._journal

    def config_servie(self) -> tuple[Config, dict | None]:
        """La configuration que l'agent sert (ou servira à son prochain démarrage), et sa source."""
        conf, source, _ = pilotage.configuration_servie(self.base, self.ordres.a_servir(self.client), self.cle_megga)
        return conf, source

    @staticmethod
    def decrire(o: dict) -> str:
        c = o.get("contenu") if isinstance(o.get("contenu"), dict) else {}
        if o.get("genre") == "config":
            return f"configuration, version {c.get('version')}"
        if o.get("genre") == "image":
            return f"image {c.get('version')} proposée"
        return "ordre"

    def noter(self, evenement: str, numero: int | None, detail: str) -> None:
        log.info("pilotage, ordre %s : %s (%s)", numero if numero is not None else "?", evenement, detail)
        self.journal.noter(self.client, evenement, numero, detail)

    # Les ordres de MEGGA

    def recevoir(self, jeton: str, accord: bool, maintenant: float | None = None) -> str | None:
        """Un ordre remis par MEGGA : vérifié, noté, puis en attente d'accord, à appliquer ou proposé.

        Rend son état, ou None s'il était déjà là. Un ordre qu'on ne peut pas ouvrir n'est pas noté
        parmi les ordres : son refus est dit à MEGGA et inscrit au journal.
        """
        maintenant = self.horloge() if maintenant is None else maintenant
        try:
            o = pilotage.ouvrir_ordre(jeton, self.client, self.cle_megga)
        except pilotage.PilotageRefuse as e:
            numero = pilotage.contenu(jeton).get("numero")
            # Un numéro non signé ne vaut que pour un ordre jamais vu : il ne doit rien dire d'un ordre réel.
            if (isinstance(numero, int) and not isinstance(numero, bool) and numero not in self.refus
                    and numero > self.ordres.dernier_numero(self.client) and len(self.refus) < 20):
                self.refus[numero] = {"numero": numero, "etat": "refuse", "detail": str(e)}
                self.noter("refuse", None, f"ordre {numero} annoncé : {e}")
            return "refuse"
        numero = o["numero"]
        if self.ordres.lire(self.client, numero) is not None:
            return None
        etat, detail = "", ""
        try:
            if numero <= self.ordres.dernier_numero(self.client):
                raise pilotage.PilotageRefuse("ordre plus ancien que le dernier reçu")
            pilotage.valider_ordre(o, self.base, maintenant)
        except pilotage.PilotageRefuse as e:
            etat, detail = "refuse", str(e)
        genre = o.get("genre") if o.get("genre") in pilotage.GENRES else "inconnu"
        if not etat:
            etat = ("attente_accord" if accord else "a_appliquer") if genre == "config" else "propose"
        if not self.ordres.ajouter(self.client, numero, genre, jeton, etat, detail, o["cree"], o["expire"], maintenant):
            return None
        if etat != "refuse":
            # Un ordre plus récent remplace ceux du même genre qui attendent encore ; jamais une configuration
            # déjà acceptée par une autre qui attend l'accord du client.
            depuis = {"attente_accord": ("attente_accord",), "a_appliquer": ("attente_accord", "a_appliquer"),
                      "propose": ("propose",)}[etat]
            for n in self.ordres.remplacer(self.client, genre, depuis, numero, maintenant):
                self.noter("remplace", n, f"remplacé par l'ordre {numero}")
        self.noter(etat, numero, detail or self.decrire(o))
        return etat

    def statuts(self, limite: int = 20) -> list[dict]:
        """Ce que sont devenus les derniers ordres, pour MEGGA (sans leur contenu)."""
        lignes = self.ordres.lister(self.client, limite)
        vus = {l["numero"] for l in lignes}
        return ([{"numero": l["numero"], "etat": l["etat"], "detail": l["detail"]} for l in lignes]
                + [r for n, r in self.refus.items() if n not in vus])

    # Le client répond

    def _attendu(self, numero: int, etats: tuple[str, ...]) -> dict:
        l = self.ordres.lire(self.client, numero)
        if l is None:
            raise pilotage.PilotageRefuse(f"aucun ordre {numero}")
        if l["etat"] not in etats:
            raise pilotage.PilotageRefuse(f"l'ordre {numero} n'attend pas de réponse (il est : {l['etat']})")
        return l

    def accepter(self, numero: int, maintenant: float | None = None) -> str:
        maintenant = self.horloge() if maintenant is None else maintenant
        l = self.ordres.lire(self.client, numero)
        if l is not None and l["etat"] == "propose":
            raise pilotage.PilotageRefuse("une image proposée ne s'installe pas encore d'ici (mises à jour signées, "
                                          "lot 6.4) ; elle peut être refusée")
        l = self._attendu(numero, ("attente_accord",))
        if maintenant > l["expire"]:
            if self.ordres.changer(self.client, numero, "expire", "plus d'une semaine sans accord", ("attente_accord",), maintenant):
                self.noter("expire", numero, "plus d'une semaine sans accord")
            raise pilotage.PilotageRefuse(f"l'ordre {numero} a expiré : MEGGA peut le renvoyer")
        pilotage.lire_ordre(l["jeton"], self.base, self.cle_megga, maintenant)  # revérifié au moment de l'accord
        if not self.ordres.changer(self.client, numero, "a_appliquer", "accepté par le client", ("attente_accord",), maintenant):
            raise pilotage.PilotageRefuse(f"l'ordre {numero} vient de changer : python -m pilote ordres")
        for n in self.ordres.remplacer(self.client, "config", ("a_appliquer",), numero, maintenant):
            self.noter("remplace", n, f"remplacé par l'ordre {numero}")
        self.noter("accepte", numero, "accepté par le client")
        return f"Ordre {numero} accepté : l'agent prend cette configuration dans la minute, après ses tours en cours."

    def refuser(self, numero: int, maintenant: float | None = None) -> str:
        self._attendu(numero, ("attente_accord", "propose"))
        if not self.ordres.changer(self.client, numero, "refuse", "refusé par le client", ("attente_accord", "propose"),
                                   self.horloge() if maintenant is None else maintenant):
            raise pilotage.PilotageRefuse(f"l'ordre {numero} vient de changer : python -m pilote ordres")
        self.noter("refuse", numero, "refusé par le client")
        return f"Ordre {numero} refusé."

    def revenir(self, maintenant: float | None = None) -> str:
        """Retire les configurations poussées par MEGGA : l'agent revient à client.yaml dans la minute."""
        maintenant = self.horloge() if maintenant is None else maintenant
        servis = ("attente_accord", "a_appliquer", "applique")
        retires = [l["numero"] for l in self.ordres.lister(self.client, 1000, etats=servis) if l["genre"] == "config"]
        for n in retires:
            if self.ordres.changer(self.client, n, "retire", "retiré par le client", servis, maintenant):
                self.noter("retire", n, "retiré par le client : retour au fichier client.yaml")
        if not retires:
            return "Aucune configuration poussée par MEGGA : l'agent sert déjà client.yaml."
        return "Configurations de MEGGA retirées : l'agent revient à client.yaml dans la minute."

    # L'application d'une configuration

    def suivre_application(self, sante: dict, maintenant: float | None = None) -> None:
        """Une configuration à appliquer devient appliquée quand l'agent la sert (son /sante) ; si, 10 minutes
        plus tard, il ne la sert toujours pas, elle est en échec et l'agent revient à la précédente."""
        maintenant = self.horloge() if maintenant is None else maintenant
        for l in self.ordres.lister(self.client, 50, etats=("attente_accord",)):
            if maintenant > l["expire"] and self.ordres.changer(self.client, l["numero"], "expire", "plus d'une semaine sans accord",
                                                                ("attente_accord",), maintenant):
                self.noter("expire", l["numero"], "plus d'une semaine sans accord")
        servie = self.ordres.a_servir(self.client)
        if not servie:
            return
        numero = servie["numero"]
        # L'agent revérifie l'ordre qu'il sert ; s'il ne passe plus (autre image, autre clé), l'agent sert son
        # fichier : l'ordre est en échec, et le suivant le plus récent reprend la main.
        _, _, refus = pilotage.configuration_servie(self.base, servie, self.cle_megga)
        if refus:
            if self.ordres.changer(self.client, numero, "echec", f"refusé par l'agent : {refus}", ("a_appliquer", "applique"), maintenant):
                self.noter("echec", numero, f"refusé par l'agent : {refus}")
            return
        if servie["etat"] != "a_appliquer":
            return
        if (sante.get("configuration") or {}).get("ordre") == numero:
            if self.ordres.changer(self.client, numero, "applique", "servie par l'agent", ("a_appliquer",), maintenant):
                for n in self.ordres.remplacer(self.client, "config", ("applique",), numero, maintenant):
                    self.noter("remplace", n, f"remplacé par l'ordre {numero}")
                self.noter("applique", numero, "l'agent sert cette configuration")
        elif maintenant - servie["maj"] > DELAI_APPLICATION:
            motif = "l'agent ne sert pas cette configuration après 10 minutes"
            if self.ordres.changer(self.client, numero, "echec", motif, ("a_appliquer",), maintenant):
                precedente = self.ordres.a_servir(self.client)
                retour = f"retour à l'ordre {precedente['numero']}" if precedente else "retour au fichier client.yaml"
                self.noter("echec", numero, f"{motif} ; {retour}")

    # Le suivi

    def suivi(self, maintenant: float | None = None) -> dict:
        """Le suivi, calculé dans la base comme /interne/suivi : volumes, modèles, échecs, sur 1, 7 et 30 jours.
        Jamais de texte, de conversation ni de numéro : des nombres, des modèles, des genres d'échec."""
        maintenant = self.horloge() if maintenant is None else maintenant
        if self._lecture is None:
            self._lecture = (stockage.Suivi(self.url), stockage.Journal(self.url), stockage.Rappels(self.url))
        lecture, journal, rappels = self._lecture
        conf, _ = self.config_servie()
        attente = rappels.en_attente()
        debut = maintenant - max(FENETRES) * 86400
        tours = lecture.tours(debut)
        fenetres = {}
        for jours in FENETRES:
            depuis = maintenant - jours * 86400
            fenetres[str(jours)] = suivi_agent.resumer(conf, [t for t in tours if (t["quand"] or 0) >= depuis],
                                                        journal.totaux(depuis), attente, depuis)
        alertes = [{"quand": a["quand"], "genre": a["genre"], "detail": pilotage.sans_donnees(a["detail"])}
                   for a in journal.alertes(debut)]
        return {"calcule": maintenant, "fenetres": fenetres, "alertes": alertes}


class Pilote:
    """Le service : un relevé par intervalle, tant que l'installation n'a pas dit « non »."""

    def __init__(self, env: dict[str, str] | None = None, transport=None, transport_agent=None, cle_megga=None,
                 horloge=time.time):
        """Les arguments nommés remplacent les vrais services (essais) ; `cle_megga`, la clé publique des ordres."""
        env = charger(dict(os.environ if env is None else env))
        self.mode = (env.get("PILOTAGE") or "non").strip().lower()
        if self.mode not in MODES:
            raise RuntimeError("PILOTAGE : non, suivi ou complet")
        self.accord = oui(env.get("PILOTAGE_ACCORD"), "PILOTAGE_ACCORD", True)
        source = source_config(env)
        if not source:
            raise RuntimeError("CLIENT_CONFIG_FILE manquante")
        self.base = configuration.lire(source)
        try:
            self.intervalle = max(1.0, float(env.get("PILOTAGE_INTERVALLE") or 60))
        except ValueError:
            raise RuntimeError("PILOTAGE_INTERVALLE : un nombre de secondes") from None
        self.horloge = horloge
        self.url_agent = (env.get("AGENT_URL") or "http://agent:8080").rstrip("/")
        self.transport, self.transport_agent = transport, transport_agent
        self.dernier_suivi = 0.0
        self.suivi_a_envoyer: dict | None = None
        self.annonce = False
        self.installation: Installation | None = None
        self.cle, self.url = None, ""
        if self.mode == "non":
            return
        if not env.get("DATABASE_URL"):
            raise RuntimeError("DATABASE_URL manquante")
        if not env.get("PILOTE_CLE"):
            raise RuntimeError("PILOTE_CLE manquante : la clé de l'installation (docs/installation-client.md, « Le pilotage »)")
        self.cle = pilotage.cle_privee(env["PILOTE_CLE"])
        self.url = (env.get("PILOTAGE_URL") or "http://megga").rstrip("/") if transport else adresse(env.get("PILOTAGE_URL") or "")
        self.installation = Installation(env["DATABASE_URL"], self.base, cle_megga, horloge)

    async def sante_agent(self) -> dict:
        """L'état de l'agent, par son /sante (réseau de l'installation) ; « injoignable » s'il ne répond pas."""
        try:
            # Le réseau de l'installation, jamais par un proxy (HTTP_PROXY est souvent réglé pour joindre MEGGA).
            async with httpx.AsyncClient(timeout=5, transport=self.transport_agent, trust_env=False) as c:
                r = await c.get(f"{self.url_agent}/sante")
            d = r.json()
        except (httpx.HTTPError, ValueError):
            return {"ok": False, "erreur": "injoignable"}
        if not isinstance(d, dict):
            return {"ok": False, "erreur": "réponse illisible"}
        etat = {k: d[k] for k in SANTE if k in d}
        etat["ok"] = bool(d.get("ok")) and r.status_code == 200
        return etat

    async def appeler(self, chemin: str, corps: dict) -> dict:
        """Une requête signée à MEGGA."""
        brut = json.dumps(corps, ensure_ascii=False, separators=(",", ":")).encode()
        # À l'heure vraie : MEGGA la compare à la sienne, à 5 minutes près.
        entetes = {**pilotage.entetes(self.base.id, self.cle, "POST", chemin, brut), "content-type": "application/json"}
        try:
            async with httpx.AsyncClient(base_url=self.url, timeout=30, transport=self.transport) as c:
                r = await c.post(chemin, content=brut, headers=entetes)
        except httpx.HTTPError as e:
            raise PiloteErreur(f"MEGGA injoignable ({type(e).__name__})") from e
        if r.status_code != 200:
            raise PiloteErreur(f"MEGGA a refusé le relevé ({r.status_code}) : {r.text[:200]}")
        try:
            d = r.json()
        except ValueError as e:
            raise PiloteErreur("réponse de MEGGA illisible") from e
        return d if isinstance(d, dict) else {}

    async def tour(self) -> dict | None:
        """Un relevé : l'état et, toutes les 5 minutes, le suivi ; puis les ordres que MEGGA remet."""
        if self.mode == "non":
            return None
        inst = self.installation
        maintenant = self.horloge()
        sante = await self.sante_agent()
        # La base en panne, ou une erreur dans le suivi, n'empêche pas le relevé : MEGGA voit au moins l'état
        # de l'agent, et que la base ne répond pas.
        prete, statuts, dernier, erreur = False, [], None, None
        try:
            prete = await asyncio.to_thread(inst.prete)
            if prete:
                if not self.annonce:
                    await asyncio.to_thread(inst.noter, "demarrage", None, f"pilotage {self.mode}, accord du client "
                                            f"{'demandé' if self.accord else 'non demandé'}, pilote {version()}")
                    self.annonce = True
                await asyncio.to_thread(inst.suivre_application, sante, maintenant)
                statuts = await asyncio.to_thread(inst.statuts)
                dernier = await asyncio.to_thread(inst.ordres.dernier_numero, inst.client)
        except Exception as e:
            prete, statuts, dernier, erreur = False, [], None, type(e).__name__
            log.warning("base de l'installation en échec : %s", str(e)[:200])
        if prete and maintenant - self.dernier_suivi >= PERIODE_SUIVI:
            # Calculé toutes les 5 minutes au plus, même si l'envoi échoue : gardé et renvoyé jusqu'à ce que MEGGA le prenne.
            self.dernier_suivi = maintenant
            try:
                self.suivi_a_envoyer = await asyncio.to_thread(inst.suivi, maintenant)
            except Exception as e:
                log.warning("suivi en échec : %s", str(e)[:200])
        corps = {"protocole": PROTOCOLE, "pilotage": self.mode, "accord": self.accord,
                 "etat": {"agent": sante, "pilote": {"version": version(), "revision": revision()}, "base": prete,
                          **({"base_erreur": erreur} if erreur else {})},
                 "ordres": statuts, "dernier_ordre": dernier}
        if self.suivi_a_envoyer is not None:
            corps["suivi"] = self.suivi_a_envoyer
        reponse = await self.appeler("/pilotage/releve", corps)
        self.suivi_a_envoyer = None
        # Sous « suivi », aucun ordre n'est pris, même si MEGGA en remettait un : c'est le réglage du client qui décide.
        if prete and self.mode == "complet":
            for jeton in (reponse.get("ordres") or [])[:20]:
                if isinstance(jeton, str):
                    try:  # un ordre qui ne passe pas n'empêche pas les suivants
                        await asyncio.to_thread(inst.recevoir, jeton, self.accord, maintenant)
                    except Exception as e:
                        log.warning("ordre illisible : %s", str(e)[:200])
        return reponse

    async def tourner(self, arret: asyncio.Event) -> None:
        if self.mode == "non":
            log.info("pilotage : non ; rien ne sort de l'installation")
        else:
            log.info("pilotage : %s, vers %s ; accord du client %s", self.mode, self.url,
                     "demandé pour chaque ordre" if self.accord else "non demandé")
        while not arret.is_set():
            try:
                await self.tour()
            except Exception as e:  # MEGGA injoignable, base en panne : le relevé suivant réessaie
                log.warning("relevé en échec : %s", str(e)[:200])
            vivant()
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(arret.wait(), timeout=self.intervalle)


def principal() -> None:
    logging.basicConfig(level=logging.INFO)
    pilote = Pilote()

    async def lancer():
        arret = asyncio.Event()
        boucle = asyncio.get_running_loop()
        for s in (signal.SIGTERM, signal.SIGINT):
            boucle.add_signal_handler(s, arret.set)
        await pilote.tourner(arret)

    asyncio.run(lancer())
