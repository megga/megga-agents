import hashlib
import os
import hmac
import json
import time

import pytest
from pydantic import ValidationError

from noyau import config as configuration
from noyau import stockage
from noyau.agent import consignes, construire
from noyau.typographie import nettoyer, sans_artefacts
from noyau.whatsapp import lire_entrants, signature_valide

EXEMPLE = "clients/exemple.yaml"


def conf(**autres):
    d = configuration.lire(EXEMPLE).model_dump()
    d.update(autres)
    return configuration.lire(d)


# La configuration


def test_exemple_valide():
    c = configuration.lire(EXEMPLE)
    assert c.id == "exemple" and c.zone == "europe" and c.whatsapp.numero_id == "100000000000001"


def test_json_accepte():
    c = configuration.lire(json.dumps(conf().model_dump()))
    assert c.nom_agent == "Alix"


@pytest.mark.parametrize(
    "champ,valeur",
    [("zone", "lune"), ("id", "Avec Majuscules"), ("version", 2), ("langue", "francais"), ("inconnu", 1), ("consignes", "a \u2014 b")],
)
def test_configuration_refusee(champ, valeur):
    d = conf().model_dump()
    d[champ] = valeur
    with pytest.raises(ValidationError):
        configuration.lire(d)


# La typographie


def test_artefacts_retires():
    assert sans_artefacts("Ouvert 17:00\u201320:00") == "Ouvert 17:00-20:00"
    assert sans_artefacts("La villa \u2014 vue lac \u2014 est libre.") == "La villa (vue lac) est libre."
    assert sans_artefacts("Prix\u00b7Surface") == "Prix, Surface"
    assert "\u2014" not in sans_artefacts("Seul \u2014 tiret")


def test_mise_en_forme_whatsapp():
    assert nettoyer("## Titre\n\n\n**gras** et\n• point") == "*Titre*\n\n*gras* et\n- point"


# WhatsApp


def signer(corps: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), corps, hashlib.sha256).hexdigest()


def test_signature():
    corps = b'{"a":1}'
    assert signature_valide(corps, signer(corps, "s"), "s")
    assert not signature_valide(corps, signer(corps, "autre"), "s")
    assert not signature_valide(corps, "sha1=00", "s")
    assert not signature_valide(corps, signer(corps, "s"), "")


def evenement(numero_id="100000000000001", texte="Bonjour", ident="wamid.1", horodatage=None):
    return {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"field": "messages", "value": {
            "metadata": {"phone_number_id": numero_id},
            "messages": [{"from": "41790000000", "id": ident, "type": "text", "timestamp": str(int(horodatage or time.time())), "text": {"body": texte}}],
        }}]}],
    }


def test_lecture_filtre_le_numero():
    assert [m.texte for m in lire_entrants(evenement(), "100000000000001")] == ["Bonjour"]
    assert lire_entrants(evenement(numero_id="999999999"), "100000000000001") == []
    m = lire_entrants(evenement(horodatage=time.time() - 3600), "100000000000001")[0]
    assert m.de == "+41790000000" and not m.frais()


# La base


def test_agent_construit_sans_reseau(tmp_path):
    db = stockage.base_agno(f"sqlite:///{tmp_path}/a.db")
    agent = construire(conf(), db, {"ANTHROPIC_API_KEY": "x", "DEEPSEEK_API_KEY": "y"})
    assert agent.model.id == "claude-sonnet-5-5"
    assert agent.fallback_config.on_error[0].id == "deepseek-v4-pro"
    assert agent.telemetry is False
    assert any("Entreprise exemple" in c for c in consignes(conf()))


def test_url_refusee():
    with pytest.raises(ValueError):
        stockage.moteur("mysql://x")


SOURCES = ["sqlite"] + (["postgres"] if os.environ.get("TEST_POSTGRES_URL") else [])


@pytest.mark.parametrize("genre", SOURCES)
def test_export_import_aller_retour(tmp_path, genre):
    """Postgres et SQLite (le moteur de la future base Cloudflare) : même export, même import."""
    from agno.db.schemas.memory import UserMemory

    source = f"sqlite:///{tmp_path}/source.db" if genre == "sqlite" else os.environ["TEST_POSTGRES_URL"]
    db = stockage.base_agno(source)
    db.upsert_user_memory(UserMemory(memory="Préfère être appelé le matin", user_id="+41790000000", memory_id=f"m-{genre}"))
    fichier = tmp_path / "export.jsonl"
    n = stockage.exporter(source, fichier)
    assert n >= 1

    cible = f"sqlite:///{tmp_path}/cible.db"  # une base neuve : l'import crée les tables
    assert stockage.importer(fichier, cible) == n
    assert stockage.importer(fichier, cible) == n  # rejouable sans doublon
    lus = stockage.base_agno(cible).get_user_memories(user_id="+41790000000")
    assert [m.memory for m in lus] == ["Préfère être appelé le matin"]


def test_l_import_cree_toutes_nos_tables(tmp_path):
    """Relecture du 16.11.2026 (I14) : une base qui a les tables du lot 7 s'exporte et se recharge dans une base neuve ;
    aucune classe qui crée une table n'est oubliée par preparer()."""
    import inspect

    a, b = f"sqlite:///{tmp_path}/a.db", f"sqlite:///{tmp_path}/b.db"
    avec_table = {c for _, c in inspect.getmembers(stockage, inspect.isclass)
                  if c.__module__ == stockage.__name__ and "__init__" in vars(c) and "_table(" in inspect.getsource(c.__init__)}
    assert avec_table == set(stockage.TABLES)
    stockage.migrer(a)
    for c in stockage.TABLES:
        c(a)
    stockage.Reseau(a).creer("+41790000003", "Marc", "+41790000001", "villa", [{"reference": "G8LR2DW8"}])
    stockage.Questions(a).poser("+41790000002", "+41790000001", "Libre en mars ?", "la villa", "fr", None)
    stockage.Veilles(a).ajouter("+41790000001", "veille", {"recherche": "villa"}, 1.0)
    n = stockage.exporter(a, tmp_path / "x.jsonl")
    assert stockage.importer(tmp_path / "x.jsonl", b) == n
    assert stockage.Reseau(b).de_partenaire("+41790000003", 0)[0]["propositions"][0]["reference"] == "G8LR2DW8"


def test_le_fil_et_l_oral_restent_chez_claude(monkeypatch):
    """Relecture du 16.11.2026 (I16) : sans modèle d'oral réglé, le résumé du fil et la réécriture pour la voix prennent
    Claude Haiku quand le principal est Claude, jamais le modèle de secours (DeepSeek) d'office."""
    from noyau import app

    reelle = configuration.lire("clients/four-seasons-properties.yaml")
    # Four Seasons règle son oral comme l'ancienne Alix (DeepSeek Flash) ; ce test éprouve le défaut, sans réglage.
    assert reelle.modeles.petit() == "deepseek-flash"
    fsp = reelle.model_copy(update={"modeles": reelle.modeles.model_copy(update={"oral": None, "fil": None})})
    assert fsp.modeles.secours == "deepseek-v4-pro" and fsp.modeles.petit() == "claude-haiku-5-5"
    assert configuration.Modeles(principal="deepseek-v4-pro", secours=None).petit() == "deepseek-v4-pro"
    assert configuration.Modeles(oral="claude-sonnet-5-5").petit() == "claude-sonnet-5-5"
    noms = []
    monkeypatch.setattr(app, "modele", lambda nom, cles: noms.append(nom))
    monkeypatch.setattr("agno.agent.Agent.__init__", lambda self, **k: None)
    import asyncio

    app._reecriture(fsp, {})
    with pytest.raises(AttributeError):  # le résumeur construit son modèle à chaque résumé ; l'agent factice ne répond pas
        asyncio.run(app._resumeur(fsp, {})("consigne", "échanges"))
    assert noms == ["claude-haiku-5-5", "claude-haiku-5-5"]


def test_les_mineurs_du_noyau(tmp_path):
    """Relecture du 16.11.2026, constats mineurs du noyau."""
    import sqlite3

    from noyau.whatsapp import LIMITE_TEXTE, decouper

    # Une colonne ajoutée à une de nos tables complète une base créée avant elle
    url = f"sqlite:///{tmp_path}/a.db"
    with sqlite3.connect(tmp_path / "a.db") as c:
        c.execute("CREATE TABLE megga_partenaires (personne VARCHAR(80) PRIMARY KEY, nom VARCHAR(120) NOT NULL, ajoute FLOAT NOT NULL, par VARCHAR(80) NOT NULL)")
        c.execute("INSERT INTO megga_partenaires VALUES ('+41790000003', 'Marc', 1.0, '')")
    p = stockage.Partenaires(url)
    assert p.lire("+41790000003")["regle"] == "" and p.regle("+41790000003", "normale")
    # Un message déjà traité ne l'est pas deux fois, même après un redémarrage
    assert stockage.Vus(url).nouveau("wamid.1") and not stockage.Vus(url).nouveau("wamid.1")
    # Une réponse trop longue part en plusieurs messages, coupés entre deux paragraphes
    texte = "\n\n".join(["Bloc " + "x" * 3000] * 3)
    morceaux = decouper(texte)
    assert len(morceaux) == 3 and all(len(m) <= LIMITE_TEXTE for m in morceaux) and "".join(morceaux).count("x") == 9000
    assert decouper("court") == ["court"]
    # Un fuseau faux est refusé à la validation, pas au démarrage du conteneur
    with pytest.raises(ValidationError, match="fuseau"):
        conf(fuseau="Europe/Zurch")
    # Un message gardé ne se perd pas si l'envoi tombe : il reste jusqu'à ce qu'il parte
    d = stockage.Differes(url)
    d.garder("+41790000003", [{"texte": "un"}])
    (ligne,) = d.a_envoyer("+41790000003")
    assert d.a_envoyer("+41790000003") and ligne["messages"] == [{"texte": "un"}]
    d.retirer(ligne["ligne"])
    assert d.a_envoyer("+41790000003") == []
    # Le journal se purge
    j = stockage.Journal(url)
    j.noter("tour_echec", quand=1.0)
    j.noter("tour_echec")
    assert j.purger(time.time() - 86400) == 1 and j.totaux(0)["tour_echec"]["nombre"] == 1


def test_la_configuration_en_parties_se_recolle():
    """La porte passe une configuration de plus de 16 000 octets en parties (limite de Cloudflare, 17.11.2026)."""
    from noyau.app import configuration_en_parties

    assert configuration_en_parties({}) is None
    assert configuration_en_parties({"CLIENT_CONFIG_PARTIES": "2", "CLIENT_CONFIG_1": '{"a": "Gen', "CLIENT_CONFIG_2": 'ève"}'}) == '{"a": "Genève"}'
    with pytest.raises(RuntimeError, match="une partie manque"):
        configuration_en_parties({"CLIENT_CONFIG_PARTIES": "2", "CLIENT_CONFIG_1": "{"})
