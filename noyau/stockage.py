"""Le seul point du noyau qui parle à la base.

Rien d'autre dans le code n'ouvre de connexion. Changer de base (Neon, Postgres
d'Exoscale, Postgres du client, puis SQLite chez Cloudflare) se fait ici.

  DATABASE_URL  postgresql://… (Postgres) ou sqlite:///chemin (essais, SQLite)

L'export et l'import d'un client entier servent au changement de zone, à
l'installation chez le client et à la future migration vers Cloudflare : toutes
les tables de la base, ligne à ligne, en JSON.
"""

from __future__ import annotations

import base64
import datetime as dt
import decimal
import gzip
import json
import re
import secrets
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Iterator

from sqlalchemy import (Column, Float, Integer, LargeBinary, MetaData, String, Table, Text, UniqueConstraint, and_, create_engine, delete, func, insert,
                        or_, select, text, update)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

FORMAT = 1
# La version de nos tables (préfixe megga_). Chaque migration est additive : une image démarre
# aussi sur une base migrée par la version suivante (retour arrière), pas au-delà.
SCHEMA_VERSION = 2
# La longueur d'une personne : un numéro WhatsApp, ou « api:<logiciel>:<identifiant> » (noyau/api.py).
PERSONNE = 80


def _elargir_personnes(c, schema) -> None:
    """Version 2 : la personne passe de 32 à 80 caractères (les conversations par API). SQLite ne borne pas
    la longueur ; sous Postgres, élargir garde les lignes et reste lisible par l'image précédente."""
    if c.dialect.name != "postgresql":
        return
    for table in ("megga_contacts", "megga_rappels", "megga_fil"):
        c.execute(text(f'ALTER TABLE IF EXISTS "{schema}"."{table}" ALTER COLUMN personne TYPE VARCHAR({PERSONNE})'))


# Les étapes de migration, de la version n-1 à n : {n: fonction(connexion, schéma)}.
ETAPES: dict = {2: _elargir_personnes}
# Le schéma Postgres des tables d'Agno (SQLite n'a pas de schéma).
SCHEMA = "ai"  # celui d'Agno par défaut, qu'il emploie dans tous les cas


# Un seul moteur (et une seule réserve de connexions) par base, partagé par tout le noyau :
# les bases des clients partagent le calcul de Neon et son nombre de connexions.
_MOTEURS: dict[str, Engine] = {}
_VERROU = threading.Lock()


def moteur(url: str) -> Engine:
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    if not (url.startswith("postgresql+psycopg://") or url.startswith("sqlite:///")):
        raise ValueError("DATABASE_URL : Postgres ou SQLite seulement")
    with _VERROU:
        if url not in _MOTEURS:
            _MOTEURS[url] = create_engine(url, pool_pre_ping=True)
        return _MOTEURS[url]


def _table(url: str, nom: str, *colonnes: Column) -> tuple[Engine, Table]:
    """Une de nos tables (préfixe megga_), créée au besoin, dans le schéma d'Agno sous Postgres."""
    e = moteur(url)
    pg = e.dialect.name == "postgresql"
    meta = MetaData(schema=SCHEMA if pg else None)
    t = Table(nom, meta, *colonnes)
    if pg:
        with e.begin() as c:
            c.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"'))
    meta.create_all(e)
    return e, t


def base_agno(url: str):
    """La base d'Agno (sessions, mémoire, traces) sur ce moteur."""
    e = moteur(url)
    if e.dialect.name == "sqlite":
        from agno.db.sqlite import SqliteDb

        return SqliteDb(db_engine=e)
    from agno.db.postgres import PostgresDb

    return PostgresDb(db_engine=e)


def _en_json(v: Any) -> Any:
    if isinstance(v, (dt.datetime, dt.date, dt.time)):
        return {"$t": "date", "v": v.isoformat()}
    if isinstance(v, decimal.Decimal):
        return {"$t": "decimal", "v": str(v)}
    if isinstance(v, uuid.UUID):
        return str(v)
    if isinstance(v, (bytes, bytearray, memoryview)):
        return {"$t": "octets", "v": base64.b64encode(bytes(v)).decode()}
    return v


def _depuis_json(v: Any) -> Any:
    if isinstance(v, dict) and set(v) == {"$t", "v"}:
        if v["$t"] == "date":
            return dt.datetime.fromisoformat(v["v"])
        if v["$t"] == "decimal":
            return decimal.Decimal(v["v"])
        if v["$t"] == "octets":
            return base64.b64decode(v["v"])
    return v


def _tables(e: Engine) -> MetaData:
    """Les tables d'Agno : le schéma SCHEMA sous Postgres, toute la base sous SQLite."""
    meta = MetaData(schema=SCHEMA if e.dialect.name == "postgresql" else None)
    meta.reflect(bind=e)
    return meta


def _lignes(e: Engine, retouche=None) -> Iterator[dict]:
    meta = _tables(e)
    # Sous Postgres, toutes les tables lues au même instant, même si l'agent écrit pendant l'export.
    options = {"isolation_level": "REPEATABLE READ"} if e.dialect.name == "postgresql" else {}
    with e.connect().execution_options(**options) as c, c.begin():
        for table in meta.sorted_tables:
            for ligne in c.execute(select(table)).mappings():
                l = dict(ligne) if retouche is None else retouche(table.name, dict(ligne))
                if l is not None:
                    yield {"table": table.name, "ligne": {k: _en_json(v) for k, v in l.items()}}


def _ouvrir(fichier: str | Path, mode: str, gz: bool):
    return gzip.open(fichier, mode + "t", encoding="utf-8") if gz else open(fichier, mode, encoding="utf-8")


def exporter(url: str, fichier: str | Path, gz: bool | None = None, retouche=None) -> int:
    """Toutes les lignes de la base du client dans un fichier JSON Lines (compressé si `gz`, ou si le nom finit
    par .gz) ; rend leur nombre. `retouche(table, ligne)` change une ligne avant de l'écrire, ou rend None pour la laisser."""
    n = 0
    with _ouvrir(fichier, "w", str(fichier).endswith(".gz") if gz is None else gz) as f:
        f.write(json.dumps({"format": FORMAT}) + "\n")
        for l in _lignes(moteur(url), retouche):
            f.write(json.dumps(l, ensure_ascii=False, default=str) + "\n")
            n += 1
    return n


class BaseTropRecente(RuntimeError):
    pass


def _table_schema(url: str) -> tuple[Engine, Table]:
    """La version de nos tables (table megga_schema), une ligne."""
    return _table(url, "megga_schema", Column("cle", String(20), primary_key=True), Column("version", Integer, nullable=False))


def migree(url: str) -> bool:
    """La base a-t-elle déjà été migrée par un agent ? Le pilote attend ce moment avant d'y créer ses tables."""
    e, t = _table_schema(url)
    with e.connect() as c:
        return c.execute(select(t.c.version).where(t.c.cle == "megga")).scalar() is not None


# La version des tables d'avant les migrations (lot 6) : une base qui les a sans megga_schema en est là.
VERSION_DE_DEPART = 1


def migrer(url: str, version: int | None = None, etapes: dict | None = None, _relu: bool = False) -> int:
    """Joue au démarrage les migrations de nos tables qui manquent ; rend la version de la base.

    Refuse une base migrée au-delà de la version suivante : deux versions sont soutenues à la fois.
    `version` et `etapes` remplacent SCHEMA_VERSION et ETAPES (essais).
    """
    from sqlalchemy import inspect

    cible = SCHEMA_VERSION if version is None else version
    etapes = ETAPES if etapes is None else etapes
    e, t = _table_schema(url)
    schema = SCHEMA if e.dialect.name == "postgresql" else None
    try:
        with e.begin() as c:
            if e.dialect.name == "postgresql":  # deux conteneurs qui démarrent ensemble ne migrent pas deux fois
                c.execute(text("SELECT pg_advisory_xact_lock(4242)"))
            actuelle = c.execute(select(t.c.version).where(t.c.cle == "megga")).scalar()
            if actuelle is None:
                nos_tables = [n for n in inspect(c).get_table_names(schema=schema) if n.startswith("megga_") and n != "megga_schema"]
                # Une base neuve : nos tables seront créées à la version de l'image. Une base d'avant les
                # migrations : elle est à la version de départ, et ses étapes restent à jouer.
                actuelle = VERSION_DE_DEPART if nos_tables else cible
                c.execute(insert(t).values(cle="megga", version=actuelle))
            actuelle = int(actuelle)
            if actuelle > cible + 1:
                raise BaseTropRecente(f"base à la version {actuelle}, image à la {cible} : trop ancienne pour cette base")
            for n in range(actuelle + 1, cible + 1):
                etapes[n](c, schema)
            if cible > actuelle:
                c.execute(update(t).where(t.c.cle == "megga").values(version=cible))
            return max(actuelle, cible)
    except IntegrityError:
        # Deux démarrages simultanés sur une base neuve (SQLite, sans verrou) : l'autre a écrit la
        # version entre-temps ; on relit, une fois.
        if _relu:
            raise
        return migrer(url, version, etapes, _relu=True)


def preparer(url: str) -> None:
    """Crée dans une base neuve toutes les tables : celles d'Agno et les nôtres."""
    base = base_agno(url)
    creer = getattr(base, "_create_all_tables", None)  # Agno ne crée ses tables qu'au premier usage
    if creer:
        creer()
    Contacts(url)
    Rappels(url)
    Journal(url)
    Fil(url)
    ClesApi(url)
    Bloques(url)
    Partenaires(url)
    Medias(url)
    Etats(url)
    Ordres(url)
    JournalPilotage(url)
    Reglages(url)
    _table_schema(url)


def importer(fichier: str | Path, url: str) -> int:
    """Recharge un export dans une base, neuve ou non (les tables sont créées au besoin).

    Une ligne de même clé est remplacée : l'import peut être rejoué sans doublon.
    """
    preparer(url)
    e = moteur(url)
    tables = {t.name: t for t in _tables(e).sorted_tables}
    n = 0
    with open(fichier, "rb") as f:
        gz = f.read(2) == b"\x1f\x8b"  # un export compressé (les sauvegardes du pilote)
    with _ouvrir(fichier, "r", gz) as f, e.begin() as c:
        entete = json.loads(f.readline() or "{}")
        if entete.get("format") != FORMAT:
            raise ValueError("export d'un format inconnu")
        for brut in f:
            l = json.loads(brut)
            table = tables.get(l["table"])
            if table is None:
                raise ValueError(f"table absente de la base cible : {l['table']}")
            valeurs = {k: _depuis_json(v) for k, v in l["ligne"].items()}
            cle = [col for col in table.primary_key.columns if col.name in valeurs]
            if cle:  # la ligne de l'export remplace celle qui existe déjà
                c.execute(delete(table).where(and_(*(col == valeurs[col.name] for col in cle))))
            c.execute(insert(table).values(valeurs))
            n += 1
    return n


class Contacts:
    """Nos propres tables, à côté de celles d'Agno (même schéma, préfixe megga_) :
    pour chaque personne, l'heure de son dernier message, qui ouvre la fenêtre de
    24 heures de WhatsApp. Elle doit survivre au sommeil du conteneur.
    """

    def __init__(self, url: str):
        self._e, self._t = _table(
            url,
            "megga_contacts",
            Column("personne", String(PERSONNE), primary_key=True),
            Column("dernier_entrant", Float, nullable=False),
        )

    def noter(self, personne: str, quand: float) -> None:
        """Retient le message le plus récent de la personne."""
        with self._e.begin() as c:
            t = self._t
            r = c.execute(update(t).where(t.c.personne == personne, t.c.dernier_entrant < quand).values(dernier_entrant=quand))
            if r.rowcount == 0 and c.execute(select(t.c.personne).where(t.c.personne == personne)).first() is None:
                c.execute(insert(t).values(personne=personne, dernier_entrant=quand))

    def dernier(self, personne: str) -> float | None:
        with self._e.connect() as c:
            return c.execute(select(self._t.c.dernier_entrant).where(self._t.c.personne == personne)).scalar()


class Rappels:
    """Les rappels demandés à l'agent (« rappelle-moi jeudi de… »), table megga_rappels.

    états : attente (à envoyer), differe (l'heure est passée hors des 24 heures sans
    modèle Meta : part au prochain message de la personne), envoye, annule.
    """

    def __init__(self, url: str):
        self._e, self._t = _table(
            url,
            "megga_rappels",
            Column("id", String(36), primary_key=True),
            Column("personne", String(PERSONNE), nullable=False, index=True),
            Column("quand", Float, nullable=False, index=True),
            Column("texte", String(500), nullable=False),
            Column("etat", String(10), nullable=False, default="attente"),
            Column("cree", Float, nullable=False),
        )

    def ajouter(self, personne: str, quand: float, texte: str) -> str:
        import time as _t

        ident = uuid.uuid4().hex[:12]
        with self._e.begin() as c:
            c.execute(insert(self._t).values(id=ident, personne=personne, quand=quand, texte=texte, etat="attente", cree=_t.time()))
        return ident

    def lister(self, personne: str) -> list[dict]:
        t = self._t
        with self._e.connect() as c:
            lignes = c.execute(select(t).where(t.c.personne == personne, t.c.etat.in_(("attente", "differe"))).order_by(t.c.quand))
            return [dict(l._mapping) for l in lignes]

    def annuler(self, personne: str, ident: str) -> bool:
        t = self._t
        with self._e.begin() as c:
            r = c.execute(update(t).where(t.c.id == ident, t.c.personne == personne, t.c.etat.in_(("attente", "differe"))).values(etat="annule"))
            return r.rowcount > 0

    def echus(self, maintenant: float) -> list[dict]:
        t = self._t
        with self._e.connect() as c:
            return [dict(l._mapping) for l in c.execute(select(t).where(t.c.etat == "attente", t.c.quand <= maintenant).order_by(t.c.quand))]

    def differes(self, personne: str) -> list[dict]:
        t = self._t
        with self._e.connect() as c:
            return [dict(l._mapping) for l in c.execute(select(t).where(t.c.personne == personne, t.c.etat == "differe").order_by(t.c.quand))]

    def marquer(self, ident: str, etat: str) -> None:
        with self._e.begin() as c:
            c.execute(update(self._t).where(self._t.c.id == ident).values(etat=etat))

    def en_attente(self) -> int:
        from sqlalchemy import func

        t = self._t
        with self._e.connect() as c:
            return c.execute(select(func.count()).where(t.c.etat.in_(("attente", "differe")))).scalar() or 0

    def prochain(self) -> float | None:
        from sqlalchemy import func

        t = self._t
        with self._e.connect() as c:
            return c.execute(select(func.min(t.c.quand)).where(t.c.etat == "attente")).scalar()


class Jetons:
    """Les jetons d'accès des clients à l'atelier (table megga_jetons, dans la base de l'atelier).

    Seule leur empreinte est gardée : un jeton se montre une fois, à sa création.
    """

    def __init__(self, url: str):
        self._e, self._t = _table(
            url,
            "megga_jetons",
            Column("empreinte", String(64), primary_key=True),
            Column("client", String(63), nullable=False, index=True),
            Column("cree", Float, nullable=False),
        )

    @staticmethod
    def _empreinte(jeton: str) -> str:
        import hashlib

        return hashlib.sha256(jeton.encode()).hexdigest()

    def creer(self, client: str) -> str:
        import secrets
        import time as _t

        jeton = "mgc_" + secrets.token_urlsafe(32)
        with self._e.begin() as c:
            c.execute(insert(self._t).values(empreinte=self._empreinte(jeton), client=client, cree=_t.time()))
        return jeton

    def client(self, jeton: str) -> str | None:
        """Le client de ce jeton, ou None."""
        if not jeton:
            return None
        with self._e.connect() as c:
            return c.execute(select(self._t.c.client).where(self._t.c.empreinte == self._empreinte(jeton))).scalar()

    def revoquer(self, client: str) -> int:
        with self._e.begin() as c:
            return c.execute(delete(self._t).where(self._t.c.client == client)).rowcount


class ClesApi:
    """Les clés des logiciels qui parlent à l'agent par API (table megga_cles_api, dans la base du client).

    Seule leur empreinte est gardée : une clé se montre une fois, à sa création (par l'atelier, ou chez le
    client par python -m noyau.cles). Une clé retirée reste listée, marquée, et ne sert plus.
    """

    def __init__(self, url: str):
        self._e, self._t = _table(
            url,
            "megga_cles_api",
            Column("id", String(12), primary_key=True),
            Column("empreinte", String(64), nullable=False, unique=True),
            Column("logiciel", String(20), nullable=False),
            Column("par_minute", Integer, nullable=False),
            Column("cree", Float, nullable=False),
            Column("retiree", Float, nullable=True),
        )

    def ajouter(self, ident: str, logiciel: str, empreinte: str, par_minute: int, quand: float | None = None) -> bool:
        """Faux si cet identifiant ou cette empreinte existent déjà."""
        try:
            with self._e.begin() as c:
                c.execute(insert(self._t).values(id=ident, empreinte=empreinte, logiciel=logiciel, par_minute=par_minute,
                                                 cree=quand or time.time(), retiree=None))
            return True
        except IntegrityError:
            return False

    def par_empreinte(self, empreinte: str) -> dict | None:
        """La clé en service de cette empreinte : {id, logiciel, par_minute}, ou None."""
        t = self._t
        with self._e.connect() as c:
            l = c.execute(select(t.c.id, t.c.logiciel, t.c.par_minute).where(t.c.empreinte == empreinte, t.c.retiree.is_(None))).first()
        return dict(l._mapping) if l else None

    def lister(self) -> list[dict]:
        t = self._t
        with self._e.connect() as c:
            lignes = c.execute(select(t.c.id, t.c.logiciel, t.c.par_minute, t.c.cree, t.c.retiree).order_by(t.c.cree))
            return [dict(l._mapping) for l in lignes]

    def retirer(self, ident: str, quand: float | None = None) -> bool:
        t = self._t
        with self._e.begin() as c:
            return c.execute(update(t).where(t.c.id == ident, t.c.retiree.is_(None)).values(retiree=quand or time.time())).rowcount > 0


class Bloques:
    """Les numéros que le client a bloqués (table megga_bloques) : jamais lus, jamais répondus (noyau/roles.py)."""

    def __init__(self, url: str):
        self._e, self._t = _table(
            url,
            "megga_bloques",
            Column("personne", String(PERSONNE), primary_key=True),
            Column("quand", Float, nullable=False),
            Column("par", String(PERSONNE), nullable=False, default=""),
            Column("nom", String(120), nullable=False, default=""),
        )

    def bloquer(self, personne: str, par: str = "", quand: float | None = None, nom: str = "") -> bool:
        """Faux s'il l'était déjà (son nom est alors mis à jour, s'il en est donné un)."""
        t = self._t
        with self._e.begin() as c:
            if c.execute(select(t.c.personne).where(t.c.personne == personne)).first() is not None:
                if nom:
                    c.execute(update(t).where(t.c.personne == personne).values(nom=nom[:120]))
                return False
            c.execute(insert(t).values(personne=personne, quand=quand or time.time(), par=par, nom=nom[:120]))
            return True

    def debloquer(self, personne: str) -> bool:
        with self._e.begin() as c:
            return c.execute(delete(self._t).where(self._t.c.personne == personne)).rowcount > 0

    def bloque(self, personne: str) -> bool:
        with self._e.connect() as c:
            return c.execute(select(self._t.c.personne).where(self._t.c.personne == personne)).first() is not None

    def lister(self) -> list[dict]:
        with self._e.connect() as c:
            return [dict(l._mapping) for l in c.execute(select(self._t).order_by(self._t.c.quand.desc()))]


# Ce qui part d'office à un partenaire, sans demander au gestionnaire (packs/immobilier/reseau.py).
REGLES_PARTENAIRE = ("partenaire", "normale", "lignes", "rien")


class Partenaires:
    """Les partenaires inscrits par le client (table megga_partenaires) : une agence, un indépendant.

    `famille` : le nom de famille, pour trier la liste ; `regle` : ce qui lui part d'office (REGLES_PARTENAIRE),
    vide pour demander chaque fois au gestionnaire. Un partenaire retiré est effacé (ses demandes gardent son nom).
    """

    def __init__(self, url: str):
        self._e, self._t = _table(
            url,
            "megga_partenaires",
            Column("personne", String(PERSONNE), primary_key=True),
            Column("nom", String(120), nullable=False, default=""),
            Column("ajoute", Float, nullable=False),
            Column("par", String(PERSONNE), nullable=False, default=""),
            Column("famille", String(60), nullable=False, default=""),
            Column("agence", String(120), nullable=False, default=""),
            Column("regle", String(12), nullable=False, default=""),
        )

    def inscrire(self, personne: str, nom: str = "", par: str = "", quand: float | None = None, famille: str = "", agence: str = "") -> bool:
        """Faux s'il l'était déjà (son nom, sa famille et son agence sont alors mis à jour)."""
        t = self._t
        with self._e.begin() as c:
            if c.execute(select(t.c.personne).where(t.c.personne == personne)).first() is not None:
                champs = {k: v for k, v in {"nom": nom[:120], "famille": famille[:60], "agence": agence[:120]}.items() if v}
                if champs:
                    c.execute(update(t).where(t.c.personne == personne).values(**champs))
                return False
            c.execute(insert(t).values(personne=personne, nom=nom[:120], ajoute=quand or time.time(), par=par, famille=famille[:60],
                                       agence=agence[:120], regle=""))
            return True

    def retirer(self, personne: str) -> bool:
        with self._e.begin() as c:
            return c.execute(delete(self._t).where(self._t.c.personne == personne)).rowcount > 0

    def inscrit(self, personne: str) -> bool:
        with self._e.connect() as c:
            return c.execute(select(self._t.c.personne).where(self._t.c.personne == personne)).first() is not None

    def lire(self, personne: str) -> dict | None:
        with self._e.connect() as c:
            l = c.execute(select(self._t).where(self._t.c.personne == personne)).first()
        return dict(l._mapping) if l else None

    def regle(self, personne: str, regle: str) -> bool:
        """La règle d'un partenaire (REGLES_PARTENAIRE), ou « » pour l'effacer ; faux s'il n'est pas inscrit."""
        if regle and regle not in REGLES_PARTENAIRE:
            raise ValueError(f"règle inconnue : {regle}")
        with self._e.begin() as c:
            return c.execute(update(self._t).where(self._t.c.personne == personne).values(regle=regle)).rowcount > 0

    def lister(self) -> list[dict]:
        """Par nom de famille (sinon par nom), puis par nom."""
        with self._e.connect() as c:
            lignes = [dict(l._mapping) for l in c.execute(select(self._t))]
        return sorted(lignes, key=lambda p: ((p["famille"] or p["nom"]).lower(), p["nom"].lower()))


GARDE_DEMANDE = 30 * 86400  # une demande de partenaire sert un mois, puis s'efface
GARDE_QUESTION = 30 * 86400  # une question de visiteur aussi
GARDE_DIFFERE = 30 * 86400  # un message gardé hors des 24 heures aussi (un média chez Meta vit 30 jours)
GARDE_RECHERCHE = 90 * 86400  # une recherche gardée, trois mois après la dernière fois


def _ident(n: int = 8) -> str:
    return "".join(secrets.choice("abcdefghijkmnpqrstuvwxyz23456789") for _ in range(n))


class Reseau:
    """Les demandes des partenaires et les recherches de leurs clients (packs/immobilier/reseau.py).

      megga_demandes      une recherche d'un partenaire, transmise à un gestionnaire (le nom du partenaire y est copié)
      megga_propositions  les biens de cette demande (trois au plus) : la référence, ce que la vitrine en dit,
                          le choix du gestionnaire et ce qu'il en est advenu
      megga_recherches    les recherches gardées trois mois : un bien qui entre en ligne et y répond devient une demande

    Jamais de prix ni d'adresse d'un bien : seulement ce que la vitrine en dit.
    """

    def __init__(self, url: str):
        self._e, self._d = _table(
            url,
            "megga_demandes",
            Column("id", String(16), primary_key=True),
            Column("partenaire", String(PERSONNE), nullable=False, index=True),
            Column("nom", String(200), nullable=False, default=""),
            Column("gestionnaire", String(PERSONNE), nullable=False, index=True),
            Column("recherche", String(400), nullable=False, default=""),
            Column("suite", String(16), nullable=False, default=""),  # la recherche gardée d'où vient la demande
            Column("depuis", Float, nullable=True),  # sa dernière fois
            Column("cree", Float, nullable=False, index=True),
            Column("statut", String(12), nullable=False, default="nouvelle"),
        )
        _, self._p = _table(
            url,
            "megga_propositions",
            Column("demande", String(16), primary_key=True),
            Column("rang", Integer, primary_key=True, autoincrement=False),
            Column("reference", String(40), nullable=False),
            Column("bien", Text, nullable=False, default="{}"),
            Column("choix", String(12), nullable=True),
            Column("etat", String(12), nullable=True),
            Column("decide", Float, nullable=True),
        )
        _, self._r = _table(
            url,
            "megga_recherches",
            Column("id", String(16), primary_key=True),
            Column("partenaire", String(PERSONNE), nullable=False, index=True),
            Column("criteres", Text, nullable=False),
            Column("resume", String(400), nullable=False),
            Column("cree", Float, nullable=False),
            Column("derniere", Float, nullable=False),
            Column("close", Float, nullable=True),
        )

    def creer(self, partenaire: str, nom: str, gestionnaire: str, recherche: str, biens: list[dict], suite: dict | None = None,
              maintenant: float | None = None) -> str:
        """Une demande et ses biens (trois au plus) ; efface celles de plus d'un mois. Rend son identifiant."""
        maintenant = maintenant or time.time()
        d, p = self._d, self._p
        ident = _ident()
        with self._e.begin() as c:
            vieilles = select(d.c.id).where(d.c.cree < maintenant - GARDE_DEMANDE)
            c.execute(delete(p).where(p.c.demande.in_(vieilles)))
            c.execute(delete(d).where(d.c.cree < maintenant - GARDE_DEMANDE))
            c.execute(insert(d).values(id=ident, partenaire=partenaire, nom=nom[:200], gestionnaire=gestionnaire, recherche=recherche[:400],
                                       suite=(suite or {}).get("recherche", ""), depuis=(suite or {}).get("depuis"), cree=maintenant,
                                       statut="nouvelle"))
            for rang, b in enumerate((biens or [])[:3]):
                c.execute(insert(p).values(demande=ident, rang=rang, reference=str(b.get("reference") or "")[:40], bien=_json(b)))
        return ident

    def lire(self, ident: str) -> dict | None:
        """La demande et ses propositions, ou None."""
        d, p = self._d, self._p
        with self._e.connect() as c:
            l = c.execute(select(d).where(d.c.id == str(ident))).first()
            if l is None:
                return None
            props = [dict(x._mapping) for x in c.execute(select(p).where(p.c.demande == str(ident)).order_by(p.c.rang))]
        for x in props:
            x["bien"] = _de_json(x["bien"]) or {}
        return {**dict(l._mapping), "propositions": props}

    def marquer(self, ident: str, statut: str) -> None:
        with self._e.begin() as c:
            c.execute(update(self._d).where(self._d.c.id == str(ident)).values(statut=statut))

    def reserver(self, ident: str, rang: int, choix: str) -> dict:
        """Retient le choix d'une proposition s'il n'y en a pas déjà un : {ok: True}, ou {ok: False, choix, etat}.
        En une écriture conditionnelle : deux choix simultanés ne passent pas tous les deux."""
        p = self._p
        with self._e.begin() as c:
            n = c.execute(update(p).where(p.c.demande == str(ident), p.c.rang == int(rang), p.c.choix.is_(None))
                          .values(choix=choix, etat="en cours", decide=time.time())).rowcount
            if n:
                return {"ok": True}
            l = c.execute(select(p.c.choix, p.c.etat).where(p.c.demande == str(ident), p.c.rang == int(rang))).first()
        return {"ok": False, "inconnue": l is None, **(dict(l._mapping) if l else {})}

    def terminer(self, ident: str, rang: int, etat: str) -> None:
        """Ce qu'il est advenu du choix ; « liberer » l'efface (un envoi qui a échoué se retente)."""
        p = self._p
        valeurs = {"choix": None, "etat": None, "decide": None} if etat == "liberer" else {"etat": etat}
        with self._e.begin() as c:
            c.execute(update(p).where(p.c.demande == str(ident), p.c.rang == int(rang)).values(**valeurs))

    def _demandes(self, condition, limite: int) -> list[dict]:
        d = self._d
        with self._e.connect() as c:
            ids = [x[0] for x in c.execute(select(d.c.id).where(condition).order_by(d.c.cree.desc()).limit(limite))]
        return [x for x in (self.lire(i) for i in ids) if x]

    def de_partenaire(self, partenaire: str, depuis: float) -> list[dict]:
        """Ses demandes depuis cette date, les plus récentes d'abord (cinq au plus)."""
        return self._demandes(and_(self._d.c.partenaire == partenaire, self._d.c.cree >= depuis), 5)

    def en_attente(self, gestionnaire: str, depuis: float) -> list[dict]:
        """Les demandes adressées à ce gestionnaire dont un bien attend encore un choix (dix au plus)."""
        d, p = self._d, self._p
        attend = select(p.c.demande).where(p.c.choix.is_(None))
        return self._demandes(and_(d.c.gestionnaire == gestionnaire, d.c.cree >= depuis, d.c.id.in_(attend)), 10)

    def deja_propose(self, partenaire: str, reference: str, depuis: float) -> bool:
        d, p = self._d, self._p
        norme = lambda r: re.sub(r"[^0-9A-Z]", "", str(r or "").upper())  # noqa: E731
        with self._e.connect() as c:
            refs = c.execute(select(p.c.reference).join(d, d.c.id == p.c.demande).where(d.c.partenaire == partenaire, d.c.cree >= depuis))
            return any(norme(r[0]) == norme(reference) for r in refs)

    def retenir(self, partenaire: str, criteres: dict, resume: str, maintenant: float | None = None) -> str:
        """Garde la recherche du client d'un partenaire ; la même, refaite, est seulement rafraîchie."""
        maintenant = maintenant or time.time()
        r = self._r
        with self._e.begin() as c:
            deja = c.execute(select(r.c.id).where(r.c.partenaire == partenaire, r.c.resume == resume[:400], r.c.close.is_(None))).first()
            if deja:
                c.execute(update(r).where(r.c.id == deja[0]).values(derniere=maintenant, criteres=_json(criteres)))
                return deja[0]
            ident = f"r{_ident(7)}"
            c.execute(insert(r).values(id=ident, partenaire=partenaire, criteres=_json(criteres), resume=resume[:400], cree=maintenant,
                                       derniere=maintenant))
            return ident

    def recherches(self, partenaire: str | None = None, maintenant: float | None = None) -> list[dict]:
        """Les recherches gardées en cours (ni closes, ni vieilles de plus de trois mois), les plus récentes d'abord."""
        maintenant = maintenant or time.time()
        r = self._r
        condition = and_(r.c.close.is_(None), r.c.derniere >= maintenant - GARDE_RECHERCHE)
        if partenaire:
            condition = and_(condition, r.c.partenaire == partenaire)
        with self._e.connect() as c:
            lignes = [dict(l._mapping) for l in c.execute(select(r).where(condition).order_by(r.c.derniere.desc()))]
        for x in lignes:
            x["criteres"] = _de_json(x["criteres"]) or {}
        return lignes

    def clore(self, ident: str) -> dict | None:
        """Clôt une recherche gardée ; rend la recherche, ou None."""
        r = self._r
        with self._e.begin() as c:
            l = c.execute(select(r).where(r.c.id == str(ident), r.c.close.is_(None))).first()
            if l is None:
                return None
            c.execute(update(r).where(r.c.id == str(ident)).values(close=time.time()))
        return dict(l._mapping)

    def reprendre_demande(self, d: dict, propositions: list[dict], suite: dict | None = None) -> bool:
        """Une demande reprise d'un autre agent (packs/immobilier/reprise.py), avec son identifiant et ses choix ;
        faux si elle existe déjà."""
        with self._e.begin() as c:
            if c.execute(select(self._d.c.id).where(self._d.c.id == d["id"])).first() is not None:
                return False
            c.execute(insert(self._d).values(id=d["id"], partenaire=d["partenaire"], nom=d.get("nom", "")[:200], gestionnaire=d["gestionnaire"],
                                             recherche=(d.get("recherche") or "")[:400], suite=(suite or {}).get("recherche", ""),
                                             depuis=(suite or {}).get("depuis"), cree=d["cree"], statut=d.get("statut") or "nouvelle"))
            for x in propositions:
                c.execute(insert(self._p).values(demande=d["id"], rang=int(x["rang"]), reference=str(x["reference"])[:40], bien=_json(x.get("bien") or {}),
                                                 choix=x.get("choix"), etat=x.get("etat"), decide=x.get("decide")))
        return True

    def reprendre_recherche(self, r: dict) -> bool:
        """Une recherche gardée reprise d'un autre agent, avec son identifiant ; faux si elle existe déjà."""
        with self._e.begin() as c:
            if c.execute(select(self._r.c.id).where(self._r.c.id == r["id"])).first() is not None:
                return False
            c.execute(insert(self._r).values(id=r["id"][:16], partenaire=r["partenaire"], criteres=_json(r["criteres"]), resume=r["resume"][:400],
                                             cree=r["cree"], derniere=r["derniere"], close=r.get("close")))
        return True

    def oublier_partenaire(self, partenaire: str) -> None:
        """Un partenaire retiré : ses recherches ne sont plus suivies."""
        with self._e.begin() as c:
            c.execute(update(self._r).where(self._r.c.partenaire == partenaire, self._r.c.close.is_(None)).values(close=time.time()))


class Questions:
    """Les questions d'un visiteur transmises à un gestionnaire (table megga_questions), et leur suivi :
    sa réponse, relayée au visiteur ; ou, sans réponse à l'heure dite (`prevenir`), le visiteur prévenu une fois."""

    def __init__(self, url: str):
        self._e, self._t = _table(
            url,
            "megga_questions",
            Column("id", String(8), primary_key=True),
            Column("visiteur", String(PERSONNE), nullable=False, index=True),
            Column("gestionnaire", String(PERSONNE), nullable=False, index=True),
            Column("nom", String(120), nullable=False, default=""),
            Column("question", String(600), nullable=False),
            Column("sujet", String(160), nullable=False, default=""),
            Column("langue", String(8), nullable=False, default=""),
            Column("cree", Float, nullable=False),
            Column("prevenir", Float, nullable=True, index=True),  # l'heure du suivi, effacée une fois fait ou inutile
            Column("reponse", Text, nullable=True),
            Column("prise", Float, nullable=True),  # le gestionnaire s'en charge lui-même
            Column("prevenu", Float, nullable=True),
        )

    def poser(self, visiteur: str, gestionnaire: str, question: str, sujet: str, langue: str, prevenir: float | None,
              nom: str = "", maintenant: float | None = None) -> str:
        t = self._t
        maintenant = maintenant or time.time()
        with self._e.begin() as c:  # les questions de plus d'un mois s'effacent : leurs identifiants courts se libèrent
            c.execute(delete(t).where(t.c.cree < maintenant - GARDE_QUESTION))
        for _ in range(8):
            ident = "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(3))
            try:
                with self._e.begin() as c:
                    c.execute(insert(t).values(id=ident, visiteur=visiteur, gestionnaire=gestionnaire, nom=nom[:120], question=question[:600],
                                               sujet=sujet[:160], langue=langue[:8], cree=maintenant, prevenir=prevenir))
                return ident
            except IntegrityError:
                continue
        raise RuntimeError("question non rangée")

    def lire(self, ident: str) -> dict | None:
        with self._e.connect() as c:
            l = c.execute(select(self._t).where(self._t.c.id == str(ident).upper())).first()
        return dict(l._mapping) if l else None

    def repondre(self, ident: str, reponse: str | None, prise: bool = False) -> None:
        """La réponse du gestionnaire (ajoutée à la précédente, pour un complément), ou sa prise en charge : plus de suivi."""
        t = self._t
        q = self.lire(ident)
        if q is None:
            return
        valeurs: dict = {"prevenir": None}
        if prise:
            valeurs["prise"] = time.time()
        if reponse:
            valeurs["reponse"] = f"{q['reponse']}\n{reponse}" if q["reponse"] else reponse
        with self._e.begin() as c:
            c.execute(update(t).where(t.c.id == q["id"]).values(**valeurs))

    def du_visiteur(self, visiteur: str, depuis: float) -> list[dict]:
        t = self._t
        with self._e.connect() as c:
            return [dict(l._mapping) for l in c.execute(select(t).where(t.c.visiteur == visiteur, t.c.cree >= depuis).order_by(t.c.cree))]

    def du_gestionnaire(self, gestionnaire: str, depuis: float) -> list[dict]:
        t = self._t
        with self._e.connect() as c:
            return [dict(l._mapping) for l in c.execute(select(t).where(t.c.gestionnaire == gestionnaire, t.c.cree >= depuis).order_by(t.c.cree))]

    def a_prevenir(self, maintenant: float) -> list[dict]:
        t = self._t
        with self._e.connect() as c:
            return [dict(l._mapping) for l in c.execute(select(t).where(t.c.prevenir.is_not(None), t.c.prevenir <= maintenant))]

    def prevenu(self, ident: str, quand: float | None) -> None:
        """Le suivi est fait (`quand`), ou abandonné (None) : il ne se refait pas."""
        with self._e.begin() as c:
            c.execute(update(self._t).where(self._t.c.id == ident).values(prevenir=None, prevenu=quand))

    def prochain(self) -> float | None:
        t = self._t
        with self._e.connect() as c:
            return c.execute(select(func.min(t.c.prevenir)).where(t.c.prevenir.is_not(None))).scalar()


class Differes:
    """Les messages que l'agent envoie de lui-même et qui n'ont pas pu partir hors des 24 heures de WhatsApp
    (table megga_differes) : ils partent au prochain message de la personne, avant sa réponse.
    `contenu` : une liste de messages, {"texte": …} ou {"document": identifiant chez Meta, "nom": …, "legende": …}."""

    def __init__(self, url: str):
        self._e, self._t = _table(
            url,
            "megga_differes",
            Column("id", String(32), primary_key=True),
            Column("personne", String(PERSONNE), nullable=False, index=True),
            Column("contenu", Text, nullable=False),
            Column("quand", Float, nullable=False),
        )

    def garder(self, personne: str, contenu: list[dict], quand: float | None = None) -> str:
        """`quand` : l'heure où il a été gardé la première fois (un message remis en file ne rajeunit pas)."""
        ident = uuid.uuid4().hex
        contenu = [{k: v for k, v in m.items() if k != "_quand"} for m in contenu]
        with self._e.begin() as c:
            c.execute(insert(self._t).values(id=ident, personne=personne, contenu=_json(contenu), quand=quand or time.time()))
        return ident

    def prendre(self, personne: str, maintenant: float | None = None) -> list[dict]:
        """Les messages gardés pour cette personne, dans l'ordre, retirés de la table (chacun une fois), avec l'heure
        où ils ont été gardés (« _quand »). Ceux de plus de GARDE_DIFFERE sont effacés sans partir : un document
        déposé chez Meta n'y vit pas plus longtemps, et ce qui a tant attendu n'a plus de sens."""
        t = self._t
        limite = (maintenant or time.time()) - GARDE_DIFFERE
        with self._e.begin() as c:
            lignes = list(c.execute(select(t).where(t.c.personne == personne).order_by(t.c.quand)))
            if lignes:
                c.execute(delete(t).where(t.c.id.in_([l.id for l in lignes])))
        return [{**m, "_quand": l.quand} for l in lignes if l.quand >= limite for m in (_de_json(l.contenu) or [])]

    def effacer(self, personne: str) -> int:
        """Ce qui attendait cette personne ne lui partira pas (un partenaire retiré, un numéro bloqué)."""
        with self._e.begin() as c:
            return c.execute(delete(self._t).where(self._t.c.personne == personne)).rowcount


RELEVES_MAX = 2000  # relevés du carnet du marché, par client


class Carnet:
    """Le carnet du marché du client (table megga_releves) : des prix au m², chacun avec sa source (packs/immobilier/
    carnet.py) ; partagé par ses gestionnaires. Une annonce déjà notée (même lien) est mise à jour ; plein, les plus
    anciennes annonces s'en vont d'abord."""

    def __init__(self, url: str):
        self._e, self._t = _table(
            url,
            "megga_releves",
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("nature", String(10), nullable=False),
            Column("lieu", String(80), nullable=False),
            Column("quartier", String(80), nullable=True),
            Column("famille", String(12), nullable=False),
            Column("devise", String(3), nullable=False),
            Column("prix", Float, nullable=True),
            Column("surface", Float, nullable=True),
            Column("prix_m2", Float, nullable=False),
            Column("bas", Float, nullable=True),
            Column("haut", Float, nullable=True),
            Column("texte", String(300), nullable=True),
            Column("lien", String(300), nullable=True, index=True),
            Column("date", Float, nullable=False),
            Column("note", Float, nullable=False),
            Column("par", String(PERSONNE), nullable=True),
        )

    CHAMPS = ("nature", "lieu", "quartier", "famille", "devise", "prix", "surface", "prix_m2", "bas", "haut", "texte", "lien", "date", "note")

    def noter(self, r: dict, par: str | None = None) -> tuple[int, bool]:
        """(numéro du relevé, nouveau ?)."""
        t = self._t
        valeurs = {k: r.get(k) for k in self.CHAMPS}
        with self._e.begin() as c:
            if r.get("lien"):
                deja = c.execute(select(t.c.id).where(t.c.lien == r["lien"])).scalar()
                if deja is not None:
                    c.execute(update(t).where(t.c.id == deja).values(**{k: v for k, v in valeurs.items() if k not in ("nature", "bas", "haut", "texte", "lien")}))
                    return int(deja), False
            if (c.execute(select(func.count()).select_from(t)).scalar() or 0) >= RELEVES_MAX:
                annonces = c.execute(select(func.count()).where(t.c.nature == "annonce")).scalar() or 0
                vieux = select(t.c.id).where(t.c.nature == "annonce") if annonces else select(t.c.id)
                ids = [x[0] for x in c.execute(vieux.order_by(t.c.date).limit(50))]
                c.execute(delete(t).where(t.c.id.in_(ids)))
            ident = c.execute(insert(t).values(**valeurs, par=par)).inserted_primary_key[0]
        return int(ident), True

    def releves(self) -> list[dict]:
        t = self._t
        with self._e.connect() as c:
            return [dict(l._mapping) for l in c.execute(select(t).order_by(t.c.date.desc(), t.c.id.desc()))]

    def retirer(self, ident: int) -> dict | None:
        t = self._t
        with self._e.begin() as c:
            l = c.execute(select(t).where(t.c.id == int(ident))).first()
            if l is None:
                return None
            c.execute(delete(t).where(t.c.id == int(ident)))
        return dict(l._mapping)


class Veilles:
    """Ce qui se refait à l'heure dite pour une personne (table megga_veilles) : une veille du marché (une recherche
    relancée chaque jour ou chaque semaine) ou le suivi d'une zone (chaque semaine). `donnees` : en JSON ;
    `prochaine` : l'heure du prochain passage, réservée avant de le faire (deux réveils ne le font pas deux fois)."""

    def __init__(self, url: str):
        self._e, self._t = _table(
            url,
            "megga_veilles",
            Column("id", String(16), primary_key=True),
            Column("personne", String(PERSONNE), nullable=False, index=True),
            Column("genre", String(8), nullable=False),  # veille, zone
            Column("donnees", Text, nullable=False),
            Column("prochaine", Float, nullable=False, index=True),
            Column("cree", Float, nullable=False),
        )

    def ajouter(self, personne: str, genre: str, donnees: dict, prochaine: float, ident: str | None = None) -> str:
        """`ident` : un identifiant donné (une reprise, packs/immobilier/reprise.py) ; sinon tiré au hasard."""
        ident = ident or f"{genre[0]}{_ident(6)}"
        with self._e.begin() as c:
            c.execute(insert(self._t).values(id=ident, personne=personne, genre=genre, donnees=_json(donnees), prochaine=prochaine,
                                             cree=time.time()))
        return ident

    def _lignes(self, condition) -> list[dict]:
        t = self._t
        with self._e.connect() as c:
            lignes = [dict(l._mapping) for l in c.execute(select(t).where(condition).order_by(t.c.prochaine))]
        for l in lignes:
            l["donnees"] = _de_json(l["donnees"]) or {}
        return lignes

    def existe(self, ident: str) -> bool:
        with self._e.connect() as c:
            return c.execute(select(self._t.c.id).where(self._t.c.id == ident)).first() is not None

    def de(self, personne: str, genre: str | None = None) -> list[dict]:
        t = self._t
        return self._lignes(and_(t.c.personne == personne, t.c.genre == genre) if genre else t.c.personne == personne)

    def echues(self, maintenant: float) -> list[dict]:
        return self._lignes(self._t.c.prochaine <= maintenant)

    def reserver(self, ident: str, avant: float, prochaine: float) -> bool:
        """Repousse le passage à `prochaine` s'il était encore à `avant` : faux si un autre réveil l'a déjà pris."""
        t = self._t
        with self._e.begin() as c:
            return c.execute(update(t).where(t.c.id == ident, t.c.prochaine == avant).values(prochaine=prochaine)).rowcount > 0

    def mettre(self, ident: str, donnees: dict) -> None:
        with self._e.begin() as c:
            c.execute(update(self._t).where(self._t.c.id == ident).values(donnees=_json(donnees)))

    def retirer(self, ident: str, personne: str | None = None, genre: str | None = None) -> dict | None:
        """Retire une veille ou un suivi, seulement de cette personne et de cette sorte s'il les donne."""
        t = self._t
        condition = t.c.id == ident
        if personne is not None:
            condition = and_(condition, t.c.personne == personne)
        if genre is not None:
            condition = and_(condition, t.c.genre == genre)
        lignes = self._lignes(condition)
        if not lignes:
            return None
        with self._e.begin() as c:
            c.execute(delete(t).where(t.c.id == ident))
        return lignes[0]

    def prochaine(self) -> float | None:
        with self._e.connect() as c:
            return c.execute(select(func.min(self._t.c.prochaine))).scalar()


REGLES_MAX = 30  # règles de travail par personne


class Regles:
    """Les règles de travail qu'un gestionnaire a apprises à l'agent en le corrigeant (table megga_regles), relues à
    chaque tour (packs/immobilier/travail.py). `portee` : partout, une personne (`qui`), ou un site."""

    def __init__(self, url: str):
        self._e, self._t = _table(
            url,
            "megga_regles",
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("personne", String(PERSONNE), nullable=False, index=True),
            Column("texte", String(240), nullable=False),
            Column("portee", String(40), nullable=False),
            Column("qui", String(80), nullable=True),
            Column("cree", Float, nullable=False),
        )

    def de(self, personne: str) -> list[dict]:
        t = self._t
        with self._e.connect() as c:
            return [dict(l._mapping) for l in c.execute(select(t).where(t.c.personne == personne).order_by(t.c.id))]

    def apprendre(self, personne: str, texte: str, portee: str, qui: str | None = None, remplace: int | None = None) -> dict:
        """{id, deja, ancienne} ; une ValueError s'il y en a déjà REGLES_MAX ou si la règle à remplacer n'existe pas."""
        t = self._t
        with self._e.begin() as c:
            ancienne = None
            if remplace:
                ancienne = c.execute(select(t.c.id, t.c.texte).where(t.c.id == int(remplace), t.c.personne == personne)).first()
                if ancienne is None:
                    raise ValueError(f"pas de règle {remplace} à remplacer")
                c.execute(delete(t).where(t.c.id == ancienne.id))
            pareille = c.execute(select(t.c.id).where(t.c.personne == personne, func.lower(t.c.texte) == texte.lower())).scalar()
            if pareille is not None:
                return {"id": int(pareille), "deja": True, "ancienne": None}
            if (c.execute(select(func.count()).where(t.c.personne == personne)).scalar() or 0) >= REGLES_MAX:
                raise ValueError(f"déjà {REGLES_MAX} règles : demande laquelle retirer")
            ident = c.execute(insert(t).values(personne=personne, texte=texte[:240], portee=portee[:40], qui=(qui or None) and qui[:80],
                                               cree=time.time())).inserted_primary_key[0]
        return {"id": int(ident), "deja": False, "ancienne": ancienne.texte if ancienne else None}

    def oublier(self, personne: str, ident: int) -> dict | None:
        t = self._t
        with self._e.begin() as c:
            l = c.execute(select(t).where(t.c.id == int(ident), t.c.personne == personne)).first()
            if l is None:
                return None
            c.execute(delete(t).where(t.c.id == l.id))
        return dict(l._mapping)


AUDIT_JOURS = 90  # le journal d'audit garde trois mois
APPROBATION_DELAI = 48 * 3600  # une demande sans réponse en 48 heures expire
APPROBATIONS_EN_ATTENTE_MAX = 20  # par personne


class Audit:
    """Le journal d'audit des outils (table megga_audit, noyau/approbations.py) : chaque appel, son outil, la personne,
    la règle qui s'appliquait, son issue et sa durée. Jamais ses arguments ni son résultat : ce qu'une action a fait se
    lit dans la conversation, ou dans sa demande d'accord (Approbations)."""

    def __init__(self, url: str):
        self._e, self._t = _table(
            url,
            "megga_audit",
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("quand", Float, nullable=False, index=True),
            Column("personne", String(PERSONNE), nullable=False, index=True),
            Column("outil", String(60), nullable=False),
            Column("regle", String(12), nullable=False),
            Column("issue", String(12), nullable=False),
            Column("duree", Float, nullable=False),
            Column("detail", String(120), nullable=True),
        )
        self._ecrits = 0

    def noter(self, personne: str, outil: str, regle: str, issue: str, duree: float, detail: str = "") -> None:
        t = self._t
        with self._e.begin() as c:
            c.execute(insert(t).values(quand=time.time(), personne=str(personne)[:PERSONNE], outil=str(outil)[:60], regle=regle[:12],
                                       issue=issue[:12], duree=round(float(duree), 3), detail=(detail or None) and str(detail)[:120]))
            self._ecrits += 1
            if self._ecrits % 500 == 1:  # de temps en temps, oublie ce qui a plus de trois mois
                c.execute(delete(t).where(t.c.quand < time.time() - AUDIT_JOURS * 86400))

    def lire(self, depuis: float = 0, limite: int = 200, personne: str | None = None) -> list[dict]:
        """Les appels les plus récents d'abord."""
        t = self._t
        q = select(t).where(t.c.quand >= depuis)
        if personne:
            q = q.where(t.c.personne == personne)
        with self._e.connect() as c:
            return [dict(l._mapping) for l in c.execute(q.order_by(t.c.quand.desc(), t.c.id.desc()).limit(int(limite)))]


class Approbations:
    """Les actions qui attendent l'accord d'un gestionnaire (table megga_approbations, noyau/approbations.py).

    Une demande garde l'outil et ses arguments, pour être faite telle quelle une fois accordée, au nom de la personne
    qui l'a demandée. Ses états : attente, puis accordee (en cours), faite ou echec ; refusee ; expiree (48 heures sans
    réponse). Une décision ne se prend qu'une fois (écriture conditionnelle) : deux gestionnaires qui touchent en même
    temps ne la font pas deux fois. `relu` : la personne a été prévenue de l'issue (le Contexte de son tour suivant)."""

    def __init__(self, url: str):
        self._e, self._t = _table(
            url,
            "megga_approbations",
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("personne", String(PERSONNE), nullable=False, index=True),
            Column("role", String(20), nullable=False),
            Column("outil", String(60), nullable=False),
            Column("arguments", Text, nullable=False),
            Column("etat", String(12), nullable=False, index=True),
            Column("cree", Float, nullable=False),
            Column("decide", Float, nullable=True),
            Column("par", String(PERSONNE), nullable=True),
            Column("resultat", Text, nullable=True),
            Column("relu", Integer, nullable=False, default=0),
        )

    @staticmethod
    def _ligne(l) -> dict:
        d = dict(l._mapping)
        d["arguments"] = json.loads(d["arguments"] or "{}")
        return d

    def demander(self, personne: str, role: str, outil: str, arguments: dict) -> int:
        """Une nouvelle demande ; une ValueError si la personne en a déjà trop qui attendent."""
        t = self._t
        with self._e.begin() as c:
            attente = c.execute(select(func.count()).where(t.c.personne == personne, t.c.etat == "attente")).scalar() or 0
            if attente >= APPROBATIONS_EN_ATTENTE_MAX:
                raise ValueError("trop de demandes attendent déjà un accord")
            return int(c.execute(insert(t).values(personne=personne, role=role[:20], outil=outil[:60],
                                                  arguments=json.dumps(arguments, ensure_ascii=False, default=str),
                                                  etat="attente", cree=time.time(), relu=0)).inserted_primary_key[0])

    def une(self, ident: int) -> dict | None:
        with self._e.connect() as c:
            l = c.execute(select(self._t).where(self._t.c.id == int(ident))).first()
        return self._ligne(l) if l else None

    def decider(self, ident: int, accord: bool, par: str) -> dict | None:
        """Accorde ou refuse une demande qui attend encore ; None si elle n'attend plus (déjà décidée, expirée)."""
        t = self._t
        self.expirer()
        with self._e.begin() as c:
            fait = c.execute(update(t).where(t.c.id == int(ident), t.c.etat == "attente")
                             .values(etat="accordee" if accord else "refusee", decide=time.time(), par=str(par)[:PERSONNE])).rowcount
            if not fait:
                return None
            return self._ligne(c.execute(select(t).where(t.c.id == int(ident))).first())

    def finir(self, ident: int, etat: str, resultat: str) -> None:
        """L'issue d'une demande accordée : faite ou echec, avec ce que l'outil a rendu."""
        with self._e.begin() as c:
            c.execute(update(self._t).where(self._t.c.id == int(ident)).values(etat=etat, resultat=str(resultat)[:2000]))

    def expirer(self, maintenant: float | None = None) -> int:
        t = self._t
        avant = (maintenant or time.time()) - APPROBATION_DELAI
        with self._e.begin() as c:
            return c.execute(update(t).where(t.c.etat == "attente", t.c.cree < avant).values(etat="expiree", decide=time.time())).rowcount

    def lister(self, etat: str | None = None, limite: int = 100) -> list[dict]:
        """Les demandes, les plus récentes d'abord ; `etat` : seulement celles-là."""
        self.expirer()
        t = self._t
        q = select(t)
        if etat:
            q = q.where(t.c.etat == etat)
        with self._e.connect() as c:
            return [self._ligne(l) for l in c.execute(q.order_by(t.c.id.desc()).limit(int(limite)))]

    def a_relire(self, personne: str) -> list[dict]:
        """Les demandes de cette personne dont l'issue ne lui a pas encore été dite ; marquées dites."""
        t = self._t
        fin = ("faite", "echec", "refusee", "expiree")
        with self._e.begin() as c:
            lignes = [self._ligne(l) for l in c.execute(select(t).where(t.c.personne == personne, t.c.relu == 0, t.c.etat.in_(fin))
                                                       .order_by(t.c.id))]
            if lignes:
                c.execute(update(t).where(t.c.id.in_([l["id"] for l in lignes])).values(relu=1))
        return lignes
DOCUMENTS_MAX = 200  # par client
PASSAGES_MAX = 20_000


class Connaissances:
    """La base de connaissances d'un client (noyau/connaissances.py) : ses documents (megga_documents) et leurs passages,
    chacun avec son vecteur (megga_passages, float32 en octets, et le modèle qui l'a calculé). Le texte d'origine n'est
    pas gardé : seulement ses passages, ce que l'agent cite."""

    def __init__(self, url: str):
        self._e, self._d = _table(
            url,
            "megga_documents",
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("titre", String(200), nullable=False),
            Column("source", String(500), nullable=True),
            Column("genre", String(10), nullable=False),
            Column("taille", Integer, nullable=False),
            Column("passages", Integer, nullable=False),
            Column("ajoute", Float, nullable=False),
        )
        _, self._p = _table(
            url,
            "megga_passages",
            Column("id", Integer, primary_key=True, autoincrement=True),
            Column("document", Integer, nullable=False, index=True),
            Column("rang", Integer, nullable=False),
            Column("texte", Text, nullable=False),
            Column("modele", String(60), nullable=False),
            Column("vecteur", LargeBinary, nullable=False),
        )

    def ajouter(self, titre: str, source: str | None, genre: str, taille: int, modele: str, passages: list[tuple[str, bytes]]) -> int:
        """Un document et ses passages, d'un coup ; une ValueError au-delà des bornes du client."""
        d, p = self._d, self._p
        with self._e.begin() as c:
            if (c.execute(select(func.count()).select_from(d)).scalar() or 0) >= DOCUMENTS_MAX:
                raise ValueError(f"déjà {DOCUMENTS_MAX} documents : retirez-en d'abord")
            if (c.execute(select(func.count()).select_from(p)).scalar() or 0) + len(passages) > PASSAGES_MAX:
                raise ValueError(f"la base dépasserait {PASSAGES_MAX} passages : retirez des documents d'abord")
            ident = int(c.execute(insert(d).values(titre=titre[:200], source=source, genre=genre[:10], taille=int(taille),
                                                   passages=len(passages), ajoute=time.time())).inserted_primary_key[0])
            if passages:
                c.execute(insert(p), [{"document": ident, "rang": i, "texte": texte, "modele": modele[:60], "vecteur": v}
                                      for i, (texte, v) in enumerate(passages)])
        return ident

    def retirer(self, ident: int) -> bool:
        with self._e.begin() as c:
            c.execute(delete(self._p).where(self._p.c.document == int(ident)))
            return c.execute(delete(self._d).where(self._d.c.id == int(ident))).rowcount > 0

    def documents(self) -> list[dict]:
        with self._e.connect() as c:
            return [dict(l._mapping) for l in c.execute(select(self._d).order_by(self._d.c.id))]

    def passages(self, modele: str) -> list[dict]:
        """Les passages calculés par ce modèle, avec le titre et la source de leur document."""
        d, p = self._d, self._p
        q = (select(p.c.id, p.c.texte, p.c.vecteur, d.c.titre, d.c.source).join(d, d.c.id == p.c.document)
             .where(p.c.modele == modele).order_by(p.c.document, p.c.rang))
        with self._e.connect() as c:
            return [dict(l._mapping) for l in c.execute(q)]


class Medias:
    """Les médias reçus de chaque personne (table megga_medias), numérotés dans l'ordre d'arrivée : « média 3 »
    dans la conversation désigne le même fichier pour l'agent et ses outils. Seul l'identifiant chez Meta est
    gardé, jamais le fichier : un outil le télécharge s'il en a besoin."""

    def __init__(self, url: str):
        self._e, self._t = _table(
            url,
            "megga_medias",
            Column("id", String(32), primary_key=True),
            Column("personne", String(PERSONNE), nullable=False, index=True),
            Column("n", Integer, nullable=False),
            Column("genre", String(12), nullable=False),  # image, video, document
            Column("media_id", String(80), nullable=False),
            Column("type", String(80), nullable=False, default=""),
            Column("nom", String(120), nullable=False, default=""),
            Column("quand", Float, nullable=False),
            UniqueConstraint("personne", "n", name="megga_medias_personne_n"),
        )

    def noter(self, personne: str, genre: str, media_id: str, type_: str = "", nom: str = "", quand: float | None = None) -> int:
        """Range un média et rend son numéro pour cette personne (1, 2, 3…)."""
        t = self._t
        for _ in range(3):
            with self._e.begin() as c:
                n = (c.execute(select(func.max(t.c.n)).where(t.c.personne == personne)).scalar() or 0) + 1
                try:
                    c.execute(insert(t).values(id=uuid.uuid4().hex, personne=personne, n=n, genre=genre[:12], media_id=media_id[:80],
                                               type=type_[:80], nom=nom[:120], quand=quand or time.time()))
                    return n
                except IntegrityError:
                    continue
        raise RuntimeError("média non rangé")

    def lire(self, personne: str, n: int) -> dict | None:
        t = self._t
        with self._e.connect() as c:
            l = c.execute(select(t).where(t.c.personne == personne, t.c.n == n)).first()
        return dict(l._mapping) if l else None

    def derniers(self, personne: str, limite: int = 20) -> list[dict]:
        t = self._t
        with self._e.connect() as c:
            lignes = list(c.execute(select(t).where(t.c.personne == personne).order_by(t.c.n.desc()).limit(limite)))
        return [dict(l._mapping) for l in reversed(lignes)]


class Etats:
    """Ce qu'un outil garde d'un tour à l'autre pour une personne (table megga_etats) : un brouillon, une action
    à confirmer… En JSON, par clé ; survit au sommeil du conteneur."""

    def __init__(self, url: str):
        self._e, self._t = _table(
            url,
            "megga_etats",
            Column("personne", String(PERSONNE), primary_key=True),
            Column("cle", String(40), primary_key=True),
            Column("valeur", Text, nullable=False),
            Column("quand", Float, nullable=False),
        )

    def lire(self, personne: str, cle: str) -> Any:
        t = self._t
        with self._e.connect() as c:
            v = c.execute(select(t.c.valeur).where(t.c.personne == personne, t.c.cle == cle)).scalar()
        return _de_json(v)

    def ecrire(self, personne: str, cle: str, valeur: Any) -> None:
        t = self._t
        with self._e.begin() as c:
            c.execute(delete(t).where(t.c.personne == personne, t.c.cle == cle))
            if valeur is not None:
                c.execute(insert(t).values(personne=personne, cle=cle, valeur=_json(valeur), quand=time.time()))


class Journal:
    """Ce qu'Agno ne garde pas : les échecs autour d'un tour et les volumes de voix (table megga_journal).

    Jamais de texte de message ni de numéro de personne : un genre, une quantité, un détail technique.
    """

    # mise_a_jour_bloquee : le pilote ne peut plus avancer seul une mise à jour de l'image (retour non fait, ligne retouchée)
    # envoi_refuse : Meta a refusé un envoi après l'avoir accepté ; message_ancien : un message reçu trop tard pour une réponse
    ALERTES = ("tour_echec", "envoi_echec", "vocal_illisible", "voix_echec", "rappel_echec", "mise_a_jour_bloquee", "envoi_refuse",
               "message_ancien")

    def __init__(self, url: str):
        self._e, self._t = _table(
            url,
            "megga_journal",
            Column("id", String(32), primary_key=True),
            Column("quand", Float, nullable=False, index=True),
            Column("genre", String(30), nullable=False),
            Column("quantite", Float, nullable=False, default=1),
            Column("detail", String(200), nullable=False, default=""),
        )

    def noter(self, genre: str, quantite: float = 1, detail: str = "", quand: float | None = None) -> None:
        import time as _t

        with self._e.begin() as c:
            c.execute(insert(self._t).values(id=uuid.uuid4().hex, quand=quand or _t.time(), genre=genre[:30],
                                             quantite=quantite, detail=detail[:200]))

    def totaux(self, depuis: float) -> dict[str, dict]:
        from sqlalchemy import func

        t = self._t
        with self._e.connect() as c:
            lignes = c.execute(select(t.c.genre, func.count(), func.sum(t.c.quantite)).where(t.c.quand >= depuis).group_by(t.c.genre))
            return {g: {"nombre": n, "quantite": float(q or 0)} for g, n, q in lignes}

    def alertes(self, depuis: float, limite: int = 100) -> list[dict]:
        t = self._t
        with self._e.connect() as c:
            lignes = c.execute(select(t.c.quand, t.c.genre, t.c.detail).where(t.c.quand >= depuis, t.c.genre.in_(self.ALERTES))
                               .order_by(t.c.quand.desc()).limit(limite))
            return [dict(l._mapping) for l in lignes]


class Fil:
    """Le fil de chaque conversation, tel que la personne l'a vécu (table megga_fil).

    Ce qu'elle a envoyé (texte, vocal transcrit) et ce qu'elle a reçu (réponses, vocaux,
    rappels, messages du noyau), dans l'ordre. Même base et même confidentialité que
    l'historique d'Agno, qui garde déjà ces textes.
    """

    def __init__(self, url: str):
        self._e, self._t = _table(
            url,
            "megga_fil",
            Column("id", String(32), primary_key=True),
            Column("personne", String(PERSONNE), nullable=False, index=True),
            Column("quand", Float, nullable=False, index=True),
            Column("sens", String(8), nullable=False),  # recu, envoye
            Column("genre", String(12), nullable=False),  # texte, vocal, rappel, modele
            Column("texte", Text, nullable=False, default=""),
        )

    def noter(self, personne: str, sens: str, genre: str, texte: str, quand: float | None = None) -> None:
        import time as _t

        with self._e.begin() as c:
            c.execute(insert(self._t).values(id=uuid.uuid4().hex, personne=personne, quand=quand or _t.time(),
                                             sens=sens, genre=genre, texte=texte or ""))

    def vide(self) -> bool:
        with self._e.connect() as c:
            return c.execute(select(self._t.c.id).limit(1)).first() is None

    def conversations(self, limite: int = 50) -> list[dict]:
        from sqlalchemy import func

        t = self._t
        with self._e.connect() as c:
            lignes = c.execute(select(t.c.personne, func.count(), func.max(t.c.quand)).group_by(t.c.personne)
                               .order_by(func.max(t.c.quand).desc()).limit(limite))
            return [{"personne": p, "messages": n, "derniere": d} for p, n, d in lignes]

    def messages(self, personne: str, limite: int = 50) -> list[dict]:
        t = self._t
        with self._e.connect() as c:
            lignes = list(c.execute(select(t.c.quand, t.c.sens, t.c.genre, t.c.texte).where(t.c.personne == personne)
                                    .order_by(t.c.quand.desc(), t.c.id.desc()).limit(limite)))
        return [dict(l._mapping) for l in reversed(lignes)]


class Suivi:
    """La lecture des tours d'Agno (table agno_runs) pour le suivi : volumes, modèles, et l'historique d'avant le fil.

    Un tour = un message (ou un regroupement de messages) d'une personne et la réponse de l'agent.
    """

    def __init__(self, url: str):
        self._e = moteur(url)
        self._schema = SCHEMA if self._e.dialect.name == "postgresql" else None
        self._table: Table | None = None

    def _runs(self) -> Table | None:
        """La table des tours, lue une fois dans le catalogue de la base (Agno la crée au premier tour)."""
        if self._table is None:
            meta = MetaData(schema=self._schema)
            try:
                meta.reflect(bind=self._e, only=["agno_runs"])
            except Exception:
                return None
            self._table = meta.tables.get(f"{self._schema}.agno_runs" if self._schema else "agno_runs")
        return self._table

    @staticmethod
    def _donnees(brut: Any) -> dict:
        if isinstance(brut, dict):
            return brut
        try:
            d = json.loads(brut or "{}")
            return d if isinstance(d, dict) else {}
        except (TypeError, ValueError):
            return {}

    def tours(self, depuis: float) -> list[dict]:
        """Les tours depuis cette date : personne, heure, statut, modèles et jetons (sans texte).

        Seules les métriques sont lues dans la base, pas les messages de chaque tour.
        """
        t = self._runs()
        if t is None:
            return []
        from sqlalchemy.types import JSON

        metriques = t.c.run_data["metrics"] if isinstance(t.c.run_data.type, JSON) else t.c.run_data
        sortie = []
        with self._e.connect() as c:
            for l in c.execute(select(t.c.user_id, t.c.created_at, t.c.status, metriques.label("m")).where(t.c.created_at >= int(depuis))):
                m = self._donnees(l.m)
                if "metrics" in m and not isinstance(t.c.run_data.type, JSON):
                    m = m.get("metrics") or {}
                modeles = [x for liste in (m.get("details") or {}).values() for x in (liste or [])]
                sortie.append({"personne": l.user_id, "quand": l.created_at, "statut": l.status, "modeles": modeles})
        return sortie

    def conversations(self, limite: int = 50) -> list[dict]:
        """Les personnes qui ont écrit d'après les tours (avant le fil), la plus récente d'abord."""
        from sqlalchemy import func

        t = self._runs()
        if t is None:
            return []
        with self._e.connect() as c:
            lignes = c.execute(select(t.c.user_id, func.count(), func.max(t.c.created_at)).where(t.c.user_id.is_not(None))
                               .group_by(t.c.user_id).order_by(func.max(t.c.created_at).desc()).limit(limite))
            return [{"personne": p, "messages": 2 * n, "derniere": d} for p, n, d in lignes]

    def messages(self, personne: str, limite: int = 50, excuse: str = "") -> list[dict]:
        """Le fil d'avant megga_fil, rebâti des tours : ce que la personne a dit, ce que l'agent a répondu.

        Un tour en échec a valu à la personne l'excuse du noyau, pas le contenu du tour.
        """
        t = self._runs()
        if t is None:
            return []
        with self._e.connect() as c:
            # À la seconde près, deux tours se départagent par leur rang dans la conversation.
            ordre = [t.c.created_at.desc()] + ([t.c.run_index.desc()] if "run_index" in t.c else [])
            lignes = list(c.execute(select(t.c.created_at, t.c.status, t.c.run_data).where(t.c.user_id == personne)
                                    .order_by(*ordre).limit(max(1, limite // 2))))
        sortie = []
        for l in reversed(lignes):
            d = self._donnees(l.run_data)
            entree = d.get("input")
            brut = entree.get("input_content") if isinstance(entree, dict) else entree
            echec = str(l.status or "").upper() in {"ERROR", "CANCELLED"}
            sortie.append({"quand": l.created_at, "sens": "recu", "genre": "texte", "texte": "" if brut is None else str(brut)})
            reponse = excuse if echec else str(d.get("content") or "")
            if reponse:
                sortie.append({"quand": l.created_at, "sens": "envoye", "genre": "texte", "texte": reponse})
        return sortie[-limite:]


class Reglages:
    """Des réglages en JSON par clé (table megga_reglages) : dans l'atelier, les tarifs ; chez le client,
    la mise à jour d'image en cours (pilote)."""

    def __init__(self, url: str):
        self._e, self._t = _table(
            url,
            "megga_reglages",
            Column("cle", String(40), primary_key=True),
            Column("valeur", String(20000), nullable=False),
        )

    def lire(self, cle: str) -> Any:
        with self._e.connect() as c:
            v = c.execute(select(self._t.c.valeur).where(self._t.c.cle == cle)).scalar()
        return json.loads(v) if v is not None else None

    def ecrire(self, cle: str, valeur: Any) -> None:
        donnees = json.dumps(valeur, ensure_ascii=False)
        with self._e.begin() as c:
            c.execute(delete(self._t).where(self._t.c.cle == cle))
            c.execute(insert(self._t).values(cle=cle, valeur=donnees))

    def changer(self, cle: str, attendu: Any, valeur: Any) -> bool:
        """Écrit `valeur` seulement si la clé vaut encore `attendu` (lu juste avant) ; faux sinon : un autre
        processus l'a changée entre-temps (le pilote et la commande du script de l'hôte, par exemple)."""
        t, avant, apres = self._t, json.dumps(attendu, ensure_ascii=False), json.dumps(valeur, ensure_ascii=False)
        try:
            with self._e.begin() as c:
                if attendu is None and c.execute(select(t.c.valeur).where(t.c.cle == cle)).scalar() is None:
                    c.execute(insert(t).values(cle=cle, valeur=apres))
                    return True
                return c.execute(update(t).where(t.c.cle == cle, t.c.valeur == avant).values(valeur=apres)).rowcount > 0
        except IntegrityError:  # écrite au même instant par l'autre
            return False


# Le pilotage des installations hors Cloudflare (noyau/pilotage.py, pilote/, atelier/pilotage.py)


def _json(v: Any) -> str | None:
    return None if v is None else json.dumps(v, ensure_ascii=False, separators=(",", ":"))


def _de_json(v: Any) -> Any:
    try:
        return json.loads(v) if v else None
    except ValueError:
        return None


class Ordres:
    """Les ordres de pilotage (table megga_ordres), des deux côtés du canal.

    Chez MEGGA (base de l'atelier) : ceux déposés pour chaque installation, et ce qu'elle en dit.
    Chez le client : ceux que son pilote a reçus et vérifiés, et ce qu'ils sont devenus.

    états : en_attente (déposé, pas encore remis), remis, attente_accord (le oui du client),
    a_appliquer, applique, propose (une image, quand le pilote n'installe pas les mises à jour :
    le client l'installe à la main), refuse, echec, remplace (par un ordre plus récent), retire
    (le client revient à son fichier), expire.
    """

    SERVIS = ("a_appliquer", "applique")

    def __init__(self, url: str):
        self._e, self._t = _table(
            url,
            "megga_ordres",
            Column("client", String(63), primary_key=True),
            Column("numero", Integer, primary_key=True, autoincrement=False),
            Column("genre", String(10), nullable=False),
            Column("jeton", Text, nullable=False),
            Column("etat", String(20), nullable=False),
            Column("detail", String(200), nullable=False, default=""),
            Column("cree", Float, nullable=False),
            Column("expire", Float, nullable=False),
            Column("maj", Float, nullable=False),
        )

    def deposer(self, client: str, genre: str, signer, duree: float, maintenant: float | None = None, minimum: int = 0) -> dict:
        """Un nouvel ordre (chez MEGGA), au numéro suivant (au-delà de `minimum`), signé par `signer(numero, quand)`.

        Les ordres du même genre encore en attente, jamais remis, sont remplacés : ils ne partiront plus.
        """
        t = self._t
        quand = time.time() if maintenant is None else maintenant
        with self._e.begin() as c:
            numero = max(c.execute(select(func.max(t.c.numero)).where(t.c.client == client)).scalar() or 0, minimum) + 1
            remplaces = self._remplacer(c, client, genre, ("en_attente",), numero, quand)
            c.execute(insert(t).values(client=client, numero=numero, genre=genre, jeton=signer(numero, quand), etat="en_attente",
                                       detail="", cree=quand, expire=int(quand) + duree, maj=quand))
        return {"numero": numero, "remplaces": remplaces}

    def ajouter(self, client: str, numero: int, genre: str, jeton: str, etat: str, detail: str, cree: float, expire: float,
                maintenant: float | None = None) -> bool:
        """Un ordre reçu (chez le client) ; faux s'il est déjà là."""
        try:
            with self._e.begin() as c:
                c.execute(insert(self._t).values(client=client, numero=numero, genre=genre, jeton=jeton, etat=etat,
                                                 detail=detail[:200], cree=cree, expire=expire,
                                                 maj=time.time() if maintenant is None else maintenant))
            return True
        except IntegrityError:
            return False

    def lire(self, client: str, numero: int) -> dict | None:
        t = self._t
        with self._e.connect() as c:
            l = c.execute(select(t).where(t.c.client == client, t.c.numero == numero)).first()
        return dict(l._mapping) if l else None

    def lister(self, client: str, limite: int = 20, etats: tuple[str, ...] | None = None) -> list[dict]:
        """Les ordres d'un client, le plus récent d'abord."""
        t = self._t
        q = select(t).where(t.c.client == client)
        if etats:
            q = q.where(t.c.etat.in_(etats))
        with self._e.connect() as c:
            return [dict(l._mapping) for l in c.execute(q.order_by(t.c.numero.desc()).limit(limite))]

    def dernier_numero(self, client: str) -> int:
        t = self._t
        with self._e.connect() as c:
            return int(c.execute(select(func.max(t.c.numero)).where(t.c.client == client)).scalar() or 0)

    def changer(self, client: str, numero: int, etat: str, detail: str = "", depuis: tuple[str, ...] | None = None,
                maintenant: float | None = None) -> bool:
        """Change l'état d'un ordre (seulement depuis ces états, si `depuis`) ; vrai s'il a changé."""
        t = self._t
        q = update(t).where(t.c.client == client, t.c.numero == numero)
        if depuis:
            q = q.where(t.c.etat.in_(depuis))
        with self._e.begin() as c:
            r = c.execute(q.values(etat=etat, detail=detail[:200], maj=time.time() if maintenant is None else maintenant))
            return r.rowcount > 0

    def _remplacer(self, c, client: str, genre: str, depuis: tuple[str, ...], par: int, quand: float) -> list[int]:
        """Chaque ordre est changé seulement s'il est encore dans l'un de ces états : un changement venu entre-temps
        (un accord du client, par exemple) n'est jamais écrasé."""
        t = self._t
        changes = []
        for (n,) in c.execute(select(t.c.numero).where(t.c.client == client, t.c.genre == genre, t.c.etat.in_(depuis),
                                                       t.c.numero < par)).all():
            r = c.execute(update(t).where(t.c.client == client, t.c.numero == n, t.c.etat.in_(depuis))
                          .values(etat="remplace", detail=f"remplacé par l'ordre {par}", maj=quand))
            if r.rowcount:
                changes.append(n)
        return changes

    def remplacer(self, client: str, genre: str, depuis: tuple[str, ...], par: int, maintenant: float | None = None) -> list[int]:
        """Les ordres plus anciens de ce genre, dans ces états, remplacés par l'ordre `par` ; rend leurs numéros."""
        with self._e.begin() as c:
            return self._remplacer(c, client, genre, depuis, par, time.time() if maintenant is None else maintenant)

    def a_servir(self, client: str) -> dict | None:
        """La configuration que l'agent doit servir (chez le client) : le dernier ordre « config » à appliquer ou appliqué."""
        t = self._t
        with self._e.connect() as c:
            l = c.execute(select(t).where(t.c.client == client, t.c.genre == "config", t.c.etat.in_(self.SERVIS))
                          .order_by(t.c.numero.desc()).limit(1)).first()
        return dict(l._mapping) if l else None

    def expirer(self, client: str, maintenant: float) -> list[int]:
        """Chez MEGGA : les ordres qui n'ont pas abouti avant leur échéance (pas encore reçus, ou sans accord)
        expirent ; rend leurs numéros."""
        t = self._t
        vivants = ("en_attente", "remis", "attente_accord")  # une fois acceptée, la suite est rapportée par l'installation
        with self._e.begin() as c:
            expires = [n for (n,) in c.execute(select(t.c.numero).where(t.c.client == client, t.c.etat.in_(vivants),
                                                                       t.c.expire < maintenant)).all()]
            for n in expires:
                c.execute(update(t).where(t.c.client == client, t.c.numero == n, t.c.etat.in_(vivants))
                          .values(etat="expire", detail="pas abouti dans la semaine", maj=maintenant))
        return expires

    def a_remettre(self, client: str, apres: int, maintenant: float) -> tuple[list[dict], list[int]]:
        """Chez MEGGA : les ordres à remettre à l'installation (numéro au-delà du dernier qu'elle a reçu, encore
        valables). Rend ces ordres et ceux remis pour la première fois."""
        t = self._t
        attente = ("en_attente", "remis")
        valable = (t.c.client == client, t.c.numero > apres, t.c.expire >= maintenant)
        with self._e.begin() as c:
            # Marqués d'abord, sous condition ; puis relus : un ordre remplacé entre-temps n'est jamais remis.
            nouveaux = [n for (n,) in c.execute(select(t.c.numero).where(*valable, t.c.etat == "en_attente")).all()]
            nouveaux = [n for n in nouveaux if c.execute(update(t).where(t.c.client == client, t.c.numero == n,
                                                                          t.c.etat == "en_attente")
                                                         .values(etat="remis", maj=maintenant)).rowcount]
            lignes = [dict(l._mapping) for l in c.execute(select(t).where(*valable, t.c.etat.in_(attente)).order_by(t.c.numero))]
        return lignes, nouveaux

    REPORTES = ("attente_accord", "a_appliquer", "applique", "propose", "refuse", "echec", "remplace", "retire", "expire")
    # Un ordre arrivé là ne change plus : un état rapporté ensuite (rejoué, ou annoncé sans être signé) est ignoré.
    FINAUX = ("refuse", "echec", "remplace", "retire", "expire")

    def noter_etats(self, client: str, etats: list, maintenant: float) -> list[dict]:
        """Chez MEGGA : ce que l'installation dit de ses ordres (le dernier mot par ordre) ; rend ceux qui ont changé,
        d'état, ou de détail pour un ordre en cours (une mise à jour d'image avance sans changer d'état : vérifiée, lancée).
        Un ordre jamais remis (en_attente) n'a pas d'état chez elle ; un ordre arrivé à un état final n'en change plus."""
        t = self._t
        derniers: dict[int, tuple[str, str]] = {}
        for e in etats[:50]:
            if not isinstance(e, dict):
                continue
            numero, etat = e.get("numero"), e.get("etat")
            if isinstance(numero, int) and not isinstance(numero, bool) and etat in self.REPORTES:
                derniers[numero] = (etat, str(e.get("detail") or "")[:200])
        changes = []
        with self._e.begin() as c:
            for numero, (etat, detail) in derniers.items():
                r = c.execute(update(t).where(t.c.client == client, t.c.numero == numero,
                                              or_(t.c.etat != etat, and_(t.c.etat == "a_appliquer", t.c.detail != detail)),
                                              t.c.etat.notin_(("en_attente",) + self.FINAUX))
                              .values(etat=etat, detail=detail, maj=maintenant))
                if r.rowcount:
                    changes.append({"numero": numero, "etat": etat, "detail": detail})
        return changes


class JournalPilotage:
    """Le journal du pilotage (table megga_pilotage), des deux côtés : chaque ordre et ce qu'il devient,
    chaque clé enregistrée ou révoquée, chaque accord du client. Jamais de conversation."""

    def __init__(self, url: str):
        self._e, self._t = _table(
            url,
            "megga_pilotage",
            Column("id", String(32), primary_key=True),
            Column("quand", Float, nullable=False, index=True),
            Column("client", String(63), nullable=False, index=True),
            Column("numero", Integer, nullable=True),
            Column("evenement", String(30), nullable=False),
            Column("detail", String(300), nullable=False, default=""),
        )

    def noter(self, client: str, evenement: str, numero: int | None = None, detail: str = "", quand: float | None = None) -> None:
        with self._e.begin() as c:
            c.execute(insert(self._t).values(id=uuid.uuid4().hex, quand=time.time() if quand is None else quand, client=client,
                                             numero=numero, evenement=evenement[:30], detail=str(detail)[:300]))

    def lire(self, client: str, limite: int = 50) -> list[dict]:
        """Les derniers événements, le plus récent d'abord."""
        t = self._t
        with self._e.connect() as c:
            lignes = c.execute(select(t.c.quand, t.c.numero, t.c.evenement, t.c.detail).where(t.c.client == client)
                               .order_by(t.c.quand.desc(), t.c.id.desc()).limit(limite))
            return [dict(l._mapping) for l in lignes]


class Installations:
    """Les installations pilotées, vues de MEGGA (table megga_installations, base de l'atelier) : la clé
    publique enregistrée à la mise en service, et le dernier relevé de leur pilote (état, suivi)."""

    def __init__(self, url: str):
        self._e, self._t = _table(
            url,
            "megga_installations",
            Column("client", String(63), primary_key=True),
            Column("cle", String(200), nullable=False),
            Column("enregistree", Float, nullable=False),
            Column("revoquee", Float, nullable=True),
            Column("releve", Float, nullable=True),
            Column("etat", Text, nullable=True),
            Column("suivi", Text, nullable=True),
        )

    def enregistrer(self, client: str, cle: str, quand: float) -> None:
        """La clé d'une installation (une nouvelle remplace l'ancienne, et lève une révocation)."""
        t = self._t
        with self._e.begin() as c:
            r = c.execute(update(t).where(t.c.client == client).values(cle=cle, enregistree=quand, revoquee=None))
            if r.rowcount == 0:
                c.execute(insert(t).values(client=client, cle=cle, enregistree=quand))

    def client_de_cle(self, cle: str) -> str | None:
        """Le client dont c'est la clé en service, s'il y en a un : une clé ne sert qu'une installation."""
        t = self._t
        with self._e.connect() as c:
            return c.execute(select(t.c.client).where(t.c.cle == cle, t.c.revoquee.is_(None))).scalar()

    def revoquer(self, client: str, quand: float) -> bool:
        t = self._t
        with self._e.begin() as c:
            return c.execute(update(t).where(t.c.client == client, t.c.revoquee.is_(None)).values(revoquee=quand)).rowcount > 0

    def cle(self, client: str) -> str | None:
        """La clé en service de cette installation, si elle n'est pas révoquée."""
        t = self._t
        with self._e.connect() as c:
            return c.execute(select(t.c.cle).where(t.c.client == client, t.c.revoquee.is_(None))).scalar()

    def noter_releve(self, client: str, etat: dict, suivi: dict | None, quand: float) -> None:
        """Le dernier relevé : l'état à chaque fois, le suivi quand il arrive (toutes les quelques minutes)."""
        valeurs = {"releve": quand, "etat": _json(etat)}
        if suivi is not None:
            valeurs["suivi"] = _json(suivi)
        with self._e.begin() as c:
            c.execute(update(self._t).where(self._t.c.client == client).values(**valeurs))

    def lire(self, client: str) -> dict | None:
        with self._e.connect() as c:
            l = c.execute(select(self._t).where(self._t.c.client == client)).first()
        if not l:
            return None
        d = dict(l._mapping)
        return {**d, "etat": _de_json(d["etat"]), "suivi": _de_json(d["suivi"])}

    def toutes(self) -> list[dict]:
        """Toutes les installations et leur dernier état, sans leur suivi."""
        t = self._t
        with self._e.connect() as c:
            lignes = c.execute(select(t.c.client, t.c.cle, t.c.enregistree, t.c.revoquee, t.c.releve, t.c.etat).order_by(t.c.client))
            return [{**dict(l._mapping), "etat": _de_json(l.etat)} for l in lignes]


class Nonces:
    """Les nonces des requêtes signées déjà reçues (table megga_nonces) : une requête rejouée est refusée."""

    def __init__(self, url: str):
        self._e, self._t = _table(
            url,
            "megga_nonces",
            Column("nonce", String(32), primary_key=True),
            Column("client", String(63), nullable=False),
            Column("quand", Float, nullable=False, index=True),
        )

    def nouveau(self, client: str, nonce: str, quand: float, garde: float = 900) -> bool:
        """Vrai la première fois ; les nonces plus vieux que `garde` (au-delà de la fenêtre des requêtes) sont oubliés."""
        try:
            with self._e.begin() as c:
                c.execute(delete(self._t).where(self._t.c.quand < quand - garde))
                c.execute(insert(self._t).values(nonce=nonce, client=client, quand=quand))
            return True
        except IntegrityError:
            return False
