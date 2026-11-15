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
import uuid
from pathlib import Path
from typing import Any, Iterator

from sqlalchemy import MetaData, and_, create_engine, delete, insert, select
from sqlalchemy.engine import Engine

FORMAT = 1
# Le schéma Postgres des tables d'Agno (SQLite n'a pas de schéma).
SCHEMA = "agno"


def moteur(url: str) -> Engine:
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    if not (url.startswith("postgresql+psycopg://") or url.startswith("sqlite:///")):
        raise ValueError("DATABASE_URL : Postgres ou SQLite seulement")
    return create_engine(url, pool_pre_ping=True)


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


def importer(fichier: str | Path, url: str) -> int:
    """Recharge un export dans une base dont les tables existent déjà (créées par Agno).

    Une ligne de même clé est remplacée : l'import peut être rejoué sans doublon.
    """
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
