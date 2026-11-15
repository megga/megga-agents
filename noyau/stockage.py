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
import json
import threading
import uuid
from pathlib import Path
from typing import Any, Iterator

from sqlalchemy import Column, Float, MetaData, String, Table, Text, and_, create_engine, delete, insert, select, text, update
from sqlalchemy.engine import Engine

FORMAT = 1
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


def _lignes(e: Engine) -> Iterator[dict]:
    meta = _tables(e)
    with e.connect() as c:
        for table in meta.sorted_tables:
            for ligne in c.execute(select(table)).mappings():
                yield {"table": table.name, "ligne": {k: _en_json(v) for k, v in ligne.items()}}


def exporter(url: str, fichier: str | Path) -> int:
    """Toutes les lignes de la base du client dans un fichier JSON Lines ; rend leur nombre."""
    n = 0
    with open(fichier, "w", encoding="utf-8") as f:
        f.write(json.dumps({"format": FORMAT}) + "\n")
        for l in _lignes(moteur(url)):
            f.write(json.dumps(l, ensure_ascii=False, default=str) + "\n")
            n += 1
    return n


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


def importer(fichier: str | Path, url: str) -> int:
    """Recharge un export dans une base, neuve ou non (les tables sont créées au besoin).

    Une ligne de même clé est remplacée : l'import peut être rejoué sans doublon.
    """
    preparer(url)
    e = moteur(url)
    tables = {t.name: t for t in _tables(e).sorted_tables}
    n = 0
    with open(fichier, encoding="utf-8") as f, e.begin() as c:
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
            Column("personne", String(32), primary_key=True),
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
            Column("personne", String(32), nullable=False, index=True),
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


class Journal:
    """Ce qu'Agno ne garde pas : les échecs autour d'un tour et les volumes de voix (table megga_journal).

    Jamais de texte de message ni de numéro de personne : un genre, une quantité, un détail technique.
    """

    ALERTES = ("tour_echec", "envoi_echec", "vocal_illisible", "voix_echec", "rappel_echec")

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
            Column("personne", String(32), nullable=False, index=True),
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
    """Les réglages de l'atelier, en JSON par clé (table megga_reglages) : aujourd'hui, les tarifs."""

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
