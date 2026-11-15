"""Lot 6.1 : une image publiable et signée (version, migrations au démarrage, publication)."""

import os
import uuid

import pytest
import yaml
from sqlalchemy import Column, String, inspect

from noyau import stockage
from noyau.version import carte, revision, version

BASES = ["sqlite"] + (["postgres"] if os.environ.get("TEST_POSTGRES_URL") else [])


@pytest.fixture(params=BASES)
def base(request, tmp_path):
    """Une base neuve ; sous Postgres (partagée), la version de nos tables est remise comme avant."""
    if request.param == "sqlite":
        yield f"sqlite:///{tmp_path}/m.db"
        return
    url = os.environ["TEST_POSTGRES_URL"]
    e, t = stockage._table_schema(url)
    with e.begin() as c:
        avant = c.execute(t.select()).mappings().all()
        c.execute(t.delete())
    try:
        yield url
    finally:
        with e.begin() as c:
            c.execute(t.delete())
            for ligne in avant:
                c.execute(t.insert().values(**ligne))


def test_la_version_de_l_image(monkeypatch):
    assert version() not in ("", None)
    monkeypatch.setenv("MEGGA_REVISION", "abc123")
    assert revision() == "abc123"
    c = carte()
    assert c == {"version": version(), "revision": "abc123", "config": 1, "schema": stockage.SCHEMA_VERSION}


def test_migrations_au_demarrage(base):
    assert stockage.migrer(base) == stockage.SCHEMA_VERSION
    assert stockage.migrer(base) == stockage.SCHEMA_VERSION  # rejouée sans effet
    # une version suivante ajoute une table : l'étape ne passe qu'une fois
    nom = f"megga_essai_{uuid.uuid4().hex[:8]}"
    jouees = []

    def etape_2(c, schema):
        jouees.append(2)
        stockage._table(base, nom, Column("id", String(8), primary_key=True))

    try:
        assert stockage.migrer(base, version=2, etapes={2: etape_2}) == 2
        assert stockage.migrer(base, version=2, etapes={2: etape_2}) == 2
        assert jouees == [2]
        # retour arrière : l'image précédente démarre sur la base migrée par la suivante
        assert stockage.migrer(base, version=1) == 2
        # au-delà, elle refuse
        stockage.migrer(base, version=3, etapes={3: lambda c, s: None})
        with pytest.raises(stockage.BaseTropRecente):
            stockage.migrer(base, version=1)
    finally:
        e = stockage.moteur(base)
        schema = stockage.SCHEMA if e.dialect.name == "postgresql" else None
        if nom in inspect(e).get_table_names(schema=schema):
            with e.begin() as c:
                c.execute(stockage.text(f'DROP TABLE {schema + "." if schema else ""}{nom}'))


def test_une_base_d_avant_les_migrations_joue_ses_etapes(tmp_path):
    """Nos tables sans megga_schema : la base est à la version de départ, ses étapes passent."""
    url = f"sqlite:///{tmp_path}/ancienne.db"
    stockage.Fil(url)  # une base d'un conteneur d'avant le lot 6
    jouees = []
    assert stockage.migrer(url, version=2, etapes={2: lambda c, s: jouees.append(2)}) == 2
    assert jouees == [2]
    neuve = f"sqlite:///{tmp_path}/neuve.db"  # une base vide : déjà à la version de l'image
    assert stockage.migrer(neuve, version=2, etapes={2: lambda c, s: jouees.append("neuve")}) == 2
    assert jouees == [2]


def test_deux_demarrages_simultanes(tmp_path, monkeypatch):
    """L'autre démarrage écrit la version entre la lecture et l'écriture : on relit au lieu de tomber."""
    from sqlalchemy.exc import IntegrityError

    url = f"sqlite:///{tmp_path}/course.db"
    e, t = stockage._table_schema(url)
    vraie = stockage.insert
    appels = []

    def course(table):
        if getattr(table, "name", None) == "megga_schema" and not appels:
            appels.append(1)
            with e.begin() as c:  # l'autre conteneur, plus rapide
                c.execute(vraie(t).values(cle="megga", version=1))
        return vraie(table)

    monkeypatch.setattr(stockage, "insert", course)
    assert stockage.migrer(url) == stockage.SCHEMA_VERSION
    assert appels == [1]


def test_l_export_garde_la_version_des_tables(tmp_path):
    source = f"sqlite:///{tmp_path}/s.db"
    stockage.migrer(source)
    stockage.exporter(source, tmp_path / "e.jsonl")
    cible = f"sqlite:///{tmp_path}/c.db"
    stockage.importer(tmp_path / "e.jsonl", cible)
    assert stockage.migrer(cible) == stockage.SCHEMA_VERSION


def test_l_image_demarre_ses_migrations(tmp_path):
    """Un conteneur client (et l'atelier) migre sa base avant de servir."""
    from fastapi.testclient import TestClient

    from atelier.app import creer as creer_atelier

    url = f"sqlite:///{tmp_path}/a.db"
    t = TestClient(creer_atelier({"ADMIN_TOKEN": "x", "DATABASE_URL": url}))
    s = t.get("/sante").json()
    assert s["service"] == "atelier" and s["version"] == version() and s["schema"] == stockage.SCHEMA_VERSION
    e, table = stockage._table_schema(url)
    with e.connect() as c:
        assert c.execute(table.select()).first() is not None


def test_publier_seulement_a_la_main_et_signe():
    w = yaml.safe_load(open(".github/workflows/publier.yml"))
    declencheurs = w[True] if True in w else w["on"]  # « on » se lit True en YAML 1.1
    assert list(declencheurs) == ["workflow_dispatch"]
    job = w["jobs"]["publier"]
    assert "'Publie'" in job["if"] and "refs/heads/main" in job["if"]
    etapes = [str(s.get("run", "")) + str(s.get("name", "")) + str(s.get("with", "")) for s in job["steps"]]
    tout = " ".join(etapes)
    for attendu in ("cosign sign", "cosign verify", "socle/cosign.pub", "déjà publiée", "/sante", "push-by-digest=true"):
        assert attendu in tout
    assert w["permissions"] == {"contents": "read", "packages": "write"}
    # le numéro de version n'est posé qu'après l'essai, la signature et la vérification, sur la même empreinte
    rang = lambda mot: next(i for i, e in enumerate(etapes) if mot in e)  # noqa: E731
    assert rang("/sante") < rang("cosign sign") < rang("cosign verify") < rang("imagetools create")
    assert "--prefer-index=false" in etapes[rang("imagetools create")]
    # une panne du registre n'est pas prise pour « pas encore publiée »
    assert "registre injoignable" in etapes[rang("déjà publiée")]


def test_dockerfile_porte_sa_version():
    d = open("socle/Dockerfile").read()
    for attendu in ("ARG MEGGA_VERSION", "ARG MEGGA_REVISION", "org.opencontainers.image.version", "MEGGA_REVISION=${MEGGA_REVISION}"):
        assert attendu in d
