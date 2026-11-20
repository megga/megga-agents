"""Les appels WhatsApp décrochés par ElevenLabs (noyau/appels.py, 20.11.2026) : qui peut appeler, ce qu'Alix fait pendant
l'appel (lire, chercher, noter, envoyer ; rien d'autre), et ce qui suit l'appel (le fil, le résumé, l'Activité)."""

import asyncio
import hashlib
import hmac
import json
import time

import pytest
from pydantic import ValidationError

from noyau import config as configuration
from noyau import stockage
from noyau.appels import ENVOIS, OUTILS, Appels, TableAppels, appelant, arguments, contexte_appel, signature_valide
from noyau.appels_outils import definitions
from noyau.roles import Personnes
from packs.immobilier.reglages import appliquer_au_mieux

CONF = configuration.lire("clients/four-seasons-properties.yaml")
GREG, JULIEN, INCONNU, BLOQUE = "+41790000001", "+41790000002", "+41780000003", "+41780000004"
AGENT = CONF.appels.agent
SECRET = "secret-de-signature-elevenlabs"
CLE = "c" * 40


def run(coro):
    return asyncio.run(coro)


class Bloques:
    def bloque(self, p):
        return p == BLOQUE


class Conversations:
    def __init__(self, conf=CONF):
        self.conf = conf
        self.journal, self.envois, self.taches = [], [], []

    def noter_journal(self, genre, quantite=1, detail=""):
        self.journal.append((genre, detail))

    def _lancer(self, coro):
        t = asyncio.ensure_future(coro)
        self.taches.append(t)
        return t

    @staticmethod
    async def _sans_echec(coro):
        try:
            await coro
        except Exception:
            pass

    async def envoyer_de_soi_meme(self, personne, messages, usage, variables=None, **_):
        self.envois.append((personne, messages, usage))
        return "libre"


def outils_factices(appels_recus):
    async def chercher_biens(run_context, transaction: str = "", budget_max: int = 0, communes: list[str] | None = None) -> str:
        """Cherche parmi les biens de l'agence.

        Args:
            transaction: vente ou location.
            budget_max: le budget maximum.
            communes: les communes voulues.
        """
        appels_recus.append(("chercher_biens", run_context.user_id, transaction, budget_max, communes))
        return "cologny-villa-lac | Villa contemporaine, Cologny | CHF 18’500’000"

    async def fiche_pdf(version: str, langue: str, run_context, slug: str = "", reference: str = "", sans_prix: bool = False,
                        titre: str = "", medias: list[int] | None = None) -> str:
        """Compose la fiche PDF d'un bien et l'envoie dans la conversation.

        Args:
            version: anonyme ou marque.
            langue: fr ou en.
            slug: l'identifiant d'une annonce du site.
            reference: la référence d'un bien en ligne.
            sans_prix: vrai pour une fiche sans prix.
            titre: pour un bien hors du site.
            medias: pour un bien hors du site.
        """
        appels_recus.append(("fiche_pdf", run_context.user_id, version, slug, titre, medias))
        if slug == "lente":
            await asyncio.sleep(0.3)
            raise ValueError("aucun bien en ligne n'a ce slug")
        if slug == "inconnue":
            raise ValueError("la gestion du site refuse : annonce introuvable")
        return "Fiche PDF envoyée dans la conversation."

    async def masquer_annonce(slug: str, masquer: bool, run_context) -> str:
        """Masque une annonce."""
        appels_recus.append(("masquer_annonce",))
        return "masquée"

    return {f.__name__: f for f in (chercher_biens, fiche_pdf, masquer_annonce)}


@pytest.fixture
def fsp(tmp_path):
    url = f"sqlite:///{tmp_path}/appels.db"
    recus = []
    conv = Conversations()
    personnes = Personnes(CONF, {GREG: "greg@agence.ch", JULIEN: "julien@megga.ch"}, Bloques())
    contacts, fil, etats, rappels = stockage.Contacts(url), stockage.Fil(url), stockage.Etats(url), stockage.Rappels(url)
    contacts.noter(GREG, time.time() - 3600, "Greg Lyonnet")
    contacts.noter(JULIEN, time.time() - 3600, "Julien")
    resumes = []

    async def resumer(consigne, texte):
        resumes.append((consigne, texte))
        return "On a parlé de Cologny.\n- Fiche de la villa de Cologny envoyée.\n- Rappel lundi à 9 h pour le client de Vandœuvres."

    a = Appels(conv, personnes, outils_factices(recus), TableAppels(url), rappels=rappels, fil=fil, etats=etats, contacts=contacts,
               resumer=resumer, cle=CLE, signature=SECRET)
    return a, conv, recus, fil, etats, rappels, resumes


# Qui appelle

def test_l_appelant_vient_d_elevenlabs_et_un_identifiant_qui_n_est_pas_un_numero_est_refuse():
    assert appelant("41790000001") == GREG and appelant("+41 79 000 00 01") == GREG
    assert appelant("US.13491208655302741918") is None and appelant("") is None and appelant(None) is None


def test_greg_est_accueilli_par_son_prenom_avec_ses_rappels_et_sa_conversation(fsp):
    a, conv, _, fil, _, rappels, _ = fsp
    rappels.ajouter(GREG, time.time() + 600, "appeler le client de Vandœuvres")
    fil.noter(GREG, "recu", "texte", "Tu as la villa de Cologny ?", time.time() - 120)
    fil.noter(GREG, "envoye", "texte", "Oui, à CHF 18’500’000.", time.time() - 100)
    r = run(a.debut({"caller_id": "41790000001", "agent_id": AGENT}))
    v = r["dynamic_variables"]
    assert r["type"] == "conversation_initiation_client_data"
    assert (v["prenom"], v["role"], v["accueil"]) == ("Greg", "gestionnaire", "Salut Greg, c'est Alix.")
    assert "appeler le client de Vandœuvres" in v["rappels_du_jour"]
    assert "Alix : Oui, à CHF 18’500’000." in v["conversation_recente"] and "La personne : Tu as la villa" in v["conversation_recente"]
    assert set(v) == {"prenom", "role", "rappels_du_jour", "conversation_recente", "date_du_jour", "accueil"}
    assert r["conversation_config_override"]["conversation"]["max_duration_seconds"] == 600
    j = run(a.debut({"caller_id": "41790000002"}))["dynamic_variables"]
    assert (j["prenom"], j["accueil"]) == ("Julien", "Salut Julien, c'est Alix.")


def test_un_visiteur_et_un_numero_bloque_sont_refuses_poliment_en_quelques_secondes(fsp):
    a, conv, _, _, _, _, _ = fsp
    for numero in ("41780000003", "41780000004", "US.123"):
        r = run(a.debut({"caller_id": numero}))
        assert r["dynamic_variables"]["role"] == "refuse" and r["dynamic_variables"]["accueil"] == CONF.appels.refus
        assert r["conversation_config_override"]["conversation"]["max_duration_seconds"] == 20
        assert r["dynamic_variables"]["conversation_recente"] == "aucune"
    assert [g for g, _ in conv.journal].count("appel_refuse") == 3


def test_greg_regle_les_appels_dans_sa_gestion(fsp):
    a, conv, *_ = fsp
    conv.conf, refuses = appliquer_au_mieux(CONF, {"appels_qui": "tous", "appels_duree": 15})
    assert not refuses
    r = run(a.debut({"caller_id": "41780000003"}))
    assert r["dynamic_variables"]["role"] == "visiteur" and r["dynamic_variables"]["accueil"] == "Bonjour, ici Alix, de Four Seasons Properties."
    assert r["conversation_config_override"]["conversation"]["max_duration_seconds"] == 900
    assert run(a.debut({"caller_id": "41780000004"}))["dynamic_variables"]["role"] == "refuse"  # bloqué, toujours
    conv.conf, _ = appliquer_au_mieux(CONF, {"appels": False})
    assert run(a.debut({"caller_id": "41790000001"}))["dynamic_variables"]["role"] == "refuse"
    c, refuses = appliquer_au_mieux(CONF, {"appels_qui": "personne", "appels_duree": "x", "reactions": False})
    assert sorted(refuses) == ["appels_duree", "appels_qui"] and c.appels == CONF.appels and c.reactions is False


def test_un_autre_agent_vocal_est_refuse(fsp):
    a, *_ = fsp
    assert a.agent_connu(AGENT) and a.agent_connu(None) and not a.agent_connu("agent_autre1234567890")


def test_la_configuration_des_appels():
    assert CONF.appels.qui == "gestionnaires" and CONF.appels.duree_max == 600 and CONF.appels.accepter
    with pytest.raises(ValidationError):
        configuration.Appels(refus="Bonjour — écrivez-moi.")
    with pytest.raises(ValidationError):
        configuration.Appels(duree_max=30)


# Pendant l'appel

def test_un_outil_au_nom_de_greg(fsp):
    a, conv, recus, *_ = fsp
    r = run(a.outil("chercher_biens", {"appelant": "41790000001", "conversation": "conv_1", "transaction": "vente",
                                        "budget_max": 20000000.0, "communes": "Cologny, Vandœuvres", "inconnu": "x"}))
    assert r == {"resultat": "cologny-villa-lac | Villa contemporaine, Cologny | CHF 18’500’000"}
    assert recus == [("chercher_biens", GREG, "vente", 20000000, ["Cologny", "Vandœuvres"])]
    assert ("appel_outil", "chercher_biens") in conv.journal


def test_seuls_les_outils_permis_et_seulement_pour_l_equipe(fsp):
    a, conv, recus, *_ = fsp
    assert "masquer_annonce" not in a.outils and run(a.outil("masquer_annonce", {"appelant": "41790000001"})) == {"erreur": "outil inconnu"}
    assert "erreur" in run(a.outil("chercher_biens", {"appelant": "41780000003"}))  # un visiteur
    conv.conf, _ = appliquer_au_mieux(CONF, {"appels_qui": "tous"})
    assert "erreur" in run(a.outil("chercher_biens", {"appelant": "41780000003"}))  # même ouvert, les outils restent à l'équipe
    assert "erreur" in run(a.outil("chercher_biens", {}))
    assert recus == []
    assert set(OUTILS).isdisjoint({"modifier_annonce", "masquer_annonce", "supprimer_annonce", "creer_annonce", "preparer_annonce",
                                   "confirmer_action", "acces_annonce", "envoyer_mot_de_passe", "ajouter_photos", "retirer_photos"})


def test_une_fiche_se_fait_d_une_annonce_du_site(fsp):
    a, _, recus, *_ = fsp
    r = run(a.outil("fiche_pdf", {"appelant": "41790000001", "version": "anonyme", "langue": "fr", "slug": "cologny-villa-lac",
                                   "titre": "Un titre inventé", "medias": [1, 2]}))
    assert r == {"resultat": "Fiche PDF envoyée dans la conversation."}
    assert recus == [("fiche_pdf", GREG, "anonyme", "cologny-villa-lac", "", None)]
    assert run(a.outil("fiche_pdf", {"appelant": "41790000001", "version": "anonyme", "langue": "fr", "slug": "inconnue"})) == \
        {"erreur": "la gestion du site refuse : annonce introuvable"}


def test_un_envoi_long_continue_et_son_echec_part_par_ecrit(fsp, monkeypatch):
    import noyau.appels as module

    monkeypatch.setattr(module, "DELAI_ENVOI", 0.05)
    a, conv, *_ = fsp

    async def scenario():
        r = await a.outil("fiche_pdf", {"appelant": "41790000001", "version": "anonyme", "langue": "fr", "slug": "lente"})
        await asyncio.gather(*conv.taches)
        return r

    r = run(scenario())
    assert r["resultat"].startswith("C'est en route")
    assert conv.envois == [(GREG, [{"texte": "Ce que je devais t'envoyer pendant l'appel n'est pas parti : aucun bien en ligne n'a ce slug."}], "appel")]
    assert set(ENVOIS) <= set(OUTILS)


def test_les_arguments_reprennent_leur_forme():
    async def f(run_context, n: int = 0, ok: bool = False, mots: list[str] | None = None, x: str = "") -> str:
        return ""

    assert arguments(f, {"n": "12", "ok": "true", "mots": "a, b", "x": "", "y": 1}, "f") == {"n": 12, "ok": True, "mots": ["a", "b"]}
    with pytest.raises(ValueError):
        arguments(f, {"n": "douze"}, "f")


def test_les_outils_d_elevenlabs_sont_tires_de_ceux_d_alix(fsp):
    a, *_ = fsp
    d = {o["name"]: o for o in definitions(a.outils, "https://porte/appels/fsp", "sec_1")}
    assert set(d) == {"chercher_biens", "fiche_pdf"}
    c = d["chercher_biens"]
    assert c["type"] == "webhook" and c["api_schema"]["url"] == "https://porte/appels/fsp/outils/chercher_biens"
    assert c["api_schema"]["request_headers"] == {"Authorization": {"secret_id": "sec_1"}}
    props = c["api_schema"]["request_body_schema"]["properties"]
    assert props["appelant"] == {"type": "string", "dynamic_variable": "system__caller_id"}
    assert props["conversation"]["dynamic_variable"] == "system__conversation_id"
    assert props["communes"]["type"] == "array" and props["budget_max"]["type"] == "integer"
    assert set(d["fiche_pdf"]["api_schema"]["request_body_schema"]["properties"]) == {"version", "langue", "slug", "reference", "sans_prix",
                                                                                       "appelant", "conversation"}
    assert "appelant" in d["fiche_pdf"]["api_schema"]["request_body_schema"]["required"]


# Après l'appel

def signe(corps: bytes, t=None) -> str:
    t = str(int(t or time.time()))
    return f"t={t},v0=" + hmac.new(SECRET.encode(), t.encode() + b"." + corps, hashlib.sha256).hexdigest()


def fin_d_appel(conversation="conv_1", caller="41790000001", role="gestionnaire", prenom="Greg"):
    debut = time.time() - 300
    return {"type": "post_call_transcription", "event_timestamp": int(time.time()), "data": {
        "agent_id": AGENT, "conversation_id": conversation, "status": "done",
        "metadata": {"start_time_unix_secs": debut, "call_duration_secs": 252},
        "analysis": {"transcript_summary": "Greg asked about Cologny."},
        "conversation_initiation_client_data": {"dynamic_variables": {"system__caller_id": caller, "role": role, "prenom": prenom}},
        "transcript": [
            {"role": "agent", "message": "Salut Greg, c'est Alix.", "time_in_call_secs": 0},
            {"role": "user", "message": "Envoie-moi la fiche de la villa de Cologny.", "time_in_call_secs": 4},
            {"role": "agent", "message": "", "time_in_call_secs": 6, "tool_calls": [{"tool_name": "fiche_pdf"}]},
            {"role": "agent", "message": "C'est parti, elle arrive dans la conversation.", "time_in_call_secs": 9},
        ]}}


def test_la_signature_d_elevenlabs():
    corps = b'{"a":1}'
    assert signature_valide(corps, signe(corps), SECRET)
    assert not signature_valide(corps, signe(corps), "autre")
    assert not signature_valide(b'{"a":2}', signe(corps), SECRET)
    assert not signature_valide(corps, signe(corps, time.time() - 3600), SECRET)
    assert not signature_valide(corps, None, SECRET) and not signature_valide(corps, signe(corps), "")


def test_apres_l_appel_le_fil_le_resume_et_l_activite(fsp):
    a, conv, _, fil, etats, _, resumes = fsp
    corps = json.dumps(fin_d_appel()).encode()

    async def scenario():
        statut = await a.fin(corps, signe(corps))
        await asyncio.gather(*conv.taches)
        deux = await a.fin(corps, signe(corps))  # ElevenLabs renvoie le webhook : rien ne se refait
        await asyncio.gather(*conv.taches)
        return statut, deux

    assert run(scenario()) == ((200, {"ok": True}), (200, {"ok": True}))
    lignes = [(m["sens"], m["genre"], m["texte"]) for m in fil.messages(GREG, 10)]
    assert lignes == [("envoye", "appel", "Salut Greg, c'est Alix."), ("recu", "appel", "Envoie-moi la fiche de la villa de Cologny."),
                      ("envoye", "appel", "(outils : fiche_pdf)"), ("envoye", "appel", "C'est parti, elle arrive dans la conversation.")]
    assert len(resumes) == 1 and "Greg : Envoie-moi la fiche" in resumes[0][1] and "tutoie" in resumes[0][0]
    assert conv.envois == [(GREG, [{"texte": resumes and "On a parlé de Cologny.\n- Fiche de la villa de Cologny envoyée.\n- Rappel lundi à 9 h pour le client de Vandœuvres."}], "appel")]
    assert etats.lire(GREG, "dernier_appel")["duree"] == 252
    j = run(a.journal(1))
    assert len(j) == 1 and (j[0]["personne"], j[0]["nom"], j[0]["duree"], j[0]["statut"]) == (GREG, "Greg", 252, "libre")
    assert j[0]["resume"].startswith("On a parlé de Cologny.")
    assert "Vous vous êtes parlé au téléphone" in run(contexte_appel(etats, "Europe/Zurich")(GREG))
    assert run(contexte_appel(etats, "Europe/Zurich")(JULIEN)) == ""


def test_un_appel_refuse_n_entre_ni_au_fil_ni_dans_un_resume(fsp):
    a, conv, _, fil, *_ = fsp
    corps = json.dumps(fin_d_appel("conv_2", "41780000004", "refuse", "")).encode()

    async def scenario():
        await a.fin(corps, signe(corps))
        await asyncio.gather(*conv.taches)

    run(scenario())
    assert fil.messages(BLOQUE, 10) == [] and conv.envois == []
    assert run(a.journal(1))[0]["statut"] == "refuse"


def test_un_webhook_de_fin_non_signe_ou_d_un_autre_agent(fsp):
    a, conv, *_ = fsp
    corps = json.dumps(fin_d_appel()).encode()
    assert run(a.fin(corps, "t=1,v0=faux"))[0] == 401
    autre = fin_d_appel()
    autre["data"]["agent_id"] = "agent_autre1234567890"
    corps = json.dumps(autre).encode()
    assert run(a.fin(corps, signe(corps)))[0] == 403
    echec = json.dumps({"type": "call_initiation_failure", "data": {"failure_reason": "busy"}}).encode()
    assert run(a.fin(echec, signe(echec))) == (200, {"ok": True}) and ("appel_echec", "busy") in conv.journal


def test_sans_resume_du_modele_celui_d_elevenlabs(fsp):
    a, conv, *_ = fsp

    async def en_panne(consigne, texte):
        raise RuntimeError("panne")

    a.resumer = en_panne
    corps = json.dumps(fin_d_appel("conv_3")).encode()

    async def scenario():
        await a.fin(corps, signe(corps))
        await asyncio.gather(*conv.taches)

    run(scenario())
    assert conv.envois[0][1] == [{"texte": "Greg asked about Cologny."}]


# Les routes

def test_les_routes_des_appels(fsp, tmp_path):
    from fastapi.testclient import TestClient

    import noyau.app as app_mod
    from test_lot7_2 import FauxExp

    class Agent:
        pass

    a, conv, *_ = fsp
    env = {"CLIENT_CONFIG": json.dumps(CONF.model_dump()), "DATABASE_URL": f"sqlite:///{tmp_path}/routes.db", "META_APP_SECRET": "s",
           "INTERNE_TOKEN": "i", "GESTIONNAIRES": json.dumps({GREG: "greg@agence.ch"})}
    app = app_mod.creer(env, agent=Agent(), agents={n: Agent() for n in ("gestionnaire", "partenaire", "visiteur")},
                        expediteur=FauxExp(), attente=0.01, appels=a)
    a.conversations = conv
    h = {"authorization": f"Bearer {CLE}"}
    with TestClient(app) as t:
        assert t.post("/appels/debut", json={"caller_id": "41790000001"}, headers={"authorization": "Bearer faux"}).status_code == 401
        assert t.post("/appels/debut", json={"caller_id": "41790000001", "agent_id": "agent_autre1234567890"}, headers=h).status_code == 403
        r = t.post("/appels/debut", json={"caller_id": "41790000001", "agent_id": AGENT}, headers=h)
        assert r.status_code == 200 and r.json()["dynamic_variables"]["prenom"] == "Greg"
        assert t.post("/appels/outils/masquer_annonce", json={"appelant": "41790000001"}, headers=h).status_code == 404
        r = t.post("/appels/outils/chercher_biens", json={"appelant": "41790000001", "communes": ["Cologny"]}, headers=h)
        assert r.status_code == 200 and "cologny-villa-lac" in r.json()["resultat"]
        assert t.post("/appels/fin", content=b"{}", headers={"elevenlabs-signature": "t=1,v0=x"}).status_code == 401
        assert t.post("/appels/outils/chercher_biens", content=b"x" * 70000, headers=h).status_code == 413


def test_les_outils_d_elevenlabs_du_client_sont_ceux_d_alix():
    """Le script qui écrit les outils de l'agent vocal (scripts/appels_outils.py) les tire du code : tous ceux d'OUTILS, chacun
    avec l'appelant que remplit ElevenLabs, sans tiret long ni point médian."""
    import importlib.util
    import re
    from pathlib import Path

    chemin = Path(__file__).resolve().parent.parent / "scripts" / "appels_outils.py"
    spec = importlib.util.spec_from_file_location("appels_outils_script", chemin)
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    outils = script.outils_d_appel(CONF)
    assert set(outils) == set(OUTILS)
    d = definitions({n: outils[n] for n in OUTILS}, "https://porte/appels/four-seasons-properties", "sec")
    assert [o["name"] for o in d] == list(OUTILS)
    assert all(o["api_schema"]["request_body_schema"]["properties"]["appelant"]["dynamic_variable"] == "system__caller_id" for o in d)
    assert not re.search("[—–·]", json.dumps(d, ensure_ascii=False))
