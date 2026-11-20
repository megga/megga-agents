"""Un appel de Greg simulé de bout en bout (20.11.2026) : les vraies routes, les vrais outils d'Alix sur une gestion en mémoire,
les vraies tables. Le début, des outils (chercher, voir, montrer en cartes, un rappel, un souvenir), des refus, puis le
webhook de fin signé : le fil, le résumé sur WhatsApp, l'Activité et le Contexte de l'écrit. Seuls ElevenLabs et le modèle du
résumé sont simulés."""

import datetime as dt
import hashlib
import hmac
import json
import time
from zoneinfo import ZoneInfo

import httpx
import pytest
from fastapi.testclient import TestClient

import noyau.app as app_mod
from noyau import stockage
from noyau.appels import Appels, TableAppels, contexte_appel
from noyau.memoire import Memoire
from noyau.rappels import outils as outils_rappels
from noyau.roles import Personnes, lire_gestionnaires
from noyau.tour import Conversations
from packs.immobilier.annonces import Services, outils as outils_annonces
from packs.immobilier.gestion import Gestion
from test_lot7_2 import CONF, GREG, FausseRedactrice, FauxExp, FauxSite

AGENT = CONF.appels.agent
CLE = "k" * 40
SECRET = "wsec_signature_de_test"
INCONNU = "+41780000009"


class Agent:
    pass


def signe(corps: bytes) -> str:
    t = str(int(time.time()))
    return f"t={t},v0=" + hmac.new(SECRET.encode(), t.encode() + b"." + corps, hashlib.sha256).hexdigest()


@pytest.fixture
def appel(tmp_path):
    url = f"sqlite:///{tmp_path}/fsp.db"
    site, exp = FauxSite(), FauxExp()
    personnes = Personnes(CONF, lire_gestionnaires(json.dumps({GREG: "greg@agence.ch"})), stockage.Bloques(url), stockage.Partenaires(url))
    contacts, fil, etats, rappels = stockage.Contacts(url), stockage.Fil(url), stockage.Etats(url), stockage.Rappels(url)
    conv = Conversations(CONF, None, exp, contacts=contacts, fil=fil, etats=etats, rappels=rappels, differes=stockage.Differes(url),
                         journal=stockage.Journal(url))
    gestion = Gestion(CONF.gestion, "cle-gestion", transport=httpx.MockTransport(site))
    s = Services(gestion, personnes, stockage.Medias(url), etats, exp, FausseRedactrice(), CONF.gestion.noms_interdits, None)
    s.conversations = conv
    memoire = Memoire(stockage.base_agno(url), CONF.fuseau)
    outils = {f.__name__: f for f in [*outils_annonces(s), *outils_rappels(rappels, CONF.fuseau, "09:00"), *memoire.outils()]}
    resumes = []

    async def resumer(consigne, texte):
        resumes.append(texte)
        return "On a parlé de Cologny.\n- Cartes de deux villas envoyées.\n- Rappel lundi à 9 h pour le client de Vandœuvres."

    appels = Appels(conv, personnes, outils, TableAppels(url), rappels=rappels, fil=fil, etats=etats, contacts=contacts,
                    resumer=resumer, cle=CLE, signature=SECRET)
    env = {"CLIENT_CONFIG": json.dumps(CONF.model_dump()), "DATABASE_URL": url, "META_APP_SECRET": "s", "INTERNE_TOKEN": "i",
           "GESTIONNAIRES": json.dumps({GREG: "greg@agence.ch"})}
    app = app_mod.creer(env, agent=Agent(), agents={n: Agent() for n in ("gestionnaire", "partenaire", "visiteur")}, expediteur=exp,
                        attente=0.01, appels=appels)
    # Greg a écrit à Alix il y a une heure : les 24 heures de WhatsApp sont ouvertes.
    contacts.noter(GREG, time.time() - 3600, "Greg Lyonnet")
    fil.noter(GREG, "recu", "texte", "Tu me trouves quelque chose à Cologny pour les Martin ?", time.time() - 3600)
    return app, appels, conv, site, exp, fil, etats, rappels, memoire, resumes


def test_un_appel_de_greg_de_bout_en_bout(appel):
    app, appels, conv, site, exp, fil, etats, rappels, memoire, resumes = appel
    h = {"authorization": f"Bearer {CLE}"}
    lundi = (dt.datetime.now(ZoneInfo("Europe/Zurich")) + dt.timedelta(days=4)).replace(hour=9, minute=0).strftime("%Y-%m-%dT%H:%M")
    with TestClient(app) as t:
        def outil(nom, **args):
            r = t.post(f"/appels/outils/{nom}", json={"appelant": "41790000001", "conversation": "conv_sim", **args}, headers=h)
            return r.status_code, r.json()

        # Le décrochage.
        r = t.post("/appels/debut", json={"caller_id": "41790000001", "agent_id": AGENT, "called_number": "1403253919537610"}, headers=h)
        v = r.json()["dynamic_variables"]
        assert r.status_code == 200 and (v["prenom"], v["role"], v["accueil"]) == ("Greg", "gestionnaire", "Salut Greg, c'est Alix.")
        assert "Cologny pour les Martin" in v["conversation_recente"]

        # Pendant l'appel : chercher, lire, montrer en cartes, un rappel, un souvenir.
        statut, r = outil("chercher_biens", communes=["Cologny"], budget_max=20000000.0, devise="CHF")
        assert statut == 200 and r["resultat"].startswith("cologny-villa-lac | Villa contemporaine avec vue sur le lac, Cologny")
        statut, r = outil("voir_annonce", slug="cologny-villa-lac")
        assert "Prix : CHF 9’500’000" in r["resultat"]
        statut, r = outil("montrer_biens", slugs=["cologny-villa-lac", "marbella-villa-olie"], introduction="Les deux villas dont on parle.")
        assert r["resultat"].startswith("2 carte(s) envoyée(s)")
        assert [e[0] for e in exp.envois] == ["carrousel"] and exp.envois[0][1] == GREG
        statut, r = outil("rappeler", quand=lundi, quoi="appeler le client de Vandœuvres")
        assert r["resultat"].startswith("Rappel ") and [l["texte"] for l in rappels.lister(GREG)] == ["appeler le client de Vandœuvres"]
        statut, r = outil("retenir", texte="Les Martin veulent une villa à Cologny, vingt millions au plus.", sujet="client")
        assert r["resultat"].startswith("Retenu") and "Les Martin" in memoire.rappel(GREG)

        # Ce qui reste à l'écrit n'existe pas au téléphone ; un autre numéro n'a aucun outil ; une erreur se dit simplement.
        assert outil("masquer_annonce", slug="cologny-villa-lac", masquer=True)[0] == 404
        assert outil("modifier_annonce", slug="cologny-villa-lac")[0] == 404
        r = t.post("/appels/outils/chercher_biens", json={"appelant": INCONNU, "communes": ["Cologny"]}, headers=h).json()
        assert "erreur" in r
        assert outil("voir_annonce", slug="inconnue")[1] == {"erreur": "la gestion du site refuse : annonce inconnue"}
        assert not any(m == "PUT" or m == "DELETE" for m, _, _ in site.appels)  # rien n'a changé dans la gestion

        # La fin, signée.
        debut = time.time() - 300
        fin = {"type": "post_call_transcription", "data": {
            "agent_id": AGENT, "conversation_id": "conv_sim", "metadata": {"start_time_unix_secs": debut, "call_duration_secs": 251},
            "conversation_initiation_client_data": {"dynamic_variables": {"system__caller_id": "41790000001", "role": "gestionnaire",
                                                                        "prenom": "Greg"}},
            "transcript": [
                {"role": "agent", "message": "Salut Greg, c'est Alix.", "time_in_call_secs": 0},
                {"role": "user", "message": "Qu'est-ce que j'ai à Cologny sous vingt millions ?", "time_in_call_secs": 3},
                {"role": "agent", "message": "", "time_in_call_secs": 4, "tool_calls": [{"tool_name": "chercher_biens"}]},
                {"role": "agent", "message": "La villa contemporaine avec vue sur le lac, à neuf millions et demi.", "time_in_call_secs": 7},
                {"role": "user", "message": "Rappelle-moi lundi à neuf heures d'appeler le client de Vandœuvres.", "time_in_call_secs": 30},
                {"role": "agent", "message": "C'est programmé pour lundi à neuf heures.", "time_in_call_secs": 33}]}}
        corps = json.dumps(fin).encode()
        assert t.post("/appels/fin", content=corps, headers={"elevenlabs-signature": "t=1,v0=" + "0" * 64}).status_code == 401
        r = t.post("/appels/fin", content=corps, headers={"elevenlabs-signature": signe(corps)})
        assert r.status_code == 200
        for _ in range(100):  # le reste se fait en arrière-plan
            j = t.portal.call(appels.journal, 1)
            if j and j[0]["statut"] != "en_cours":
                break
            time.sleep(0.05)
        assert t.post("/appels/fin", content=corps, headers={"elevenlabs-signature": signe(corps)}).status_code == 200  # rejoué
        time.sleep(0.2)

    # Le résumé est parti une fois, dans la conversation de Greg.
    textes = [e for e in exp.envois if e[0] == "texte"]
    assert len(textes) == 1 and textes[0][1] == GREG and textes[0][2].startswith("On a parlé de Cologny.")
    assert len(resumes) == 1 and "Greg : Qu'est-ce que j'ai à Cologny" in resumes[0]
    # Le fil : les répliques de l'appel, puis le résumé.
    lignes = [(m["sens"], m["genre"]) for m in fil.messages(GREG, 20)]
    assert lignes.count(("recu", "appel")) == 2 and lignes.count(("envoye", "appel")) == 4 and lignes[-1] == ("envoye", "resume_appel")
    # L'Activité et le Contexte de l'écrit.
    j = app_mod.asyncio.run(appels.journal(1))
    assert len(j) == 1 and (j[0]["nom"], j[0]["duree"], j[0]["statut"]) == ("Greg", 251, "libre")
    assert "Vous vous êtes parlé au téléphone" in app_mod.asyncio.run(contexte_appel(etats, CONF.fuseau)(GREG))
    # Le journal du noyau : le début, chaque outil, l'appel ; jamais un numéro.
    import sqlalchemy

    with stockage.moteur(appels.table._e.url.render_as_string(hide_password=False)).connect() as c:
        genres = [r[0] for r in c.execute(sqlalchemy.text("select genre from megga_journal"))]
    assert {"appel_debut", "appel_outil", "appel"} <= set(genres)


def test_un_numero_inconnu_est_refuse_au_decrochage_et_rien_ne_suit(appel):
    app, appels, conv, site, exp, fil, *_ = appel
    with TestClient(app) as t:
        r = t.post("/appels/debut", json={"caller_id": INCONNU.lstrip("+"), "agent_id": AGENT}, headers={"authorization": f"Bearer {CLE}"})
        v = r.json()["dynamic_variables"]
        assert v["role"] == "refuse" and v["conversation_recente"] == "aucune" and v["rappels_du_jour"] == "aucun"
        assert r.json()["conversation_config_override"]["conversation"]["max_duration_seconds"] == 20
        fin = {"type": "post_call_transcription", "data": {
            "agent_id": AGENT, "conversation_id": "conv_refus", "metadata": {"start_time_unix_secs": time.time(), "call_duration_secs": 12},
            "conversation_initiation_client_data": {"dynamic_variables": {"system__caller_id": INCONNU.lstrip("+"), "role": "refuse"}},
            "transcript": [{"role": "user", "message": "Bonjour, vous avez des villas ?", "time_in_call_secs": 2}]}}
        corps = json.dumps(fin).encode()
        assert t.post("/appels/fin", content=corps, headers={"elevenlabs-signature": signe(corps)}).status_code == 200
        time.sleep(0.3)
    assert exp.envois == [] and fil.messages(INCONNU, 10) == [] and site.appels == []
