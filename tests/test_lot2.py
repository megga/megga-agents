import asyncio
import json
import os
import time

import httpx
import pytest
from pydantic import ValidationError

from noyau import config as configuration
from noyau import stockage
from noyau.oral import consignes, pour_la_voix
from noyau.tour import NON_COMPRIS, REGARD, Conversations
from noyau.voix import Voie, a_dire, a_ecrire, d_un_tenant, langue, voix_pour
from noyau.whatsapp import Entrant, Expediteur, fenetre_ouverte

VOIX_FR = "VoixFrancaise01"
VOIX_EN = "VoixAnglaise001"


def conf(**autres):
    d = configuration.lire("clients/exemple.yaml").model_dump()
    d.update(autres)
    return configuration.lire(d)


class Sortie:
    def __init__(self, content, status="COMPLETED"):
        self.content, self.status = content, status


class Agent:
    def __init__(self, reponse="Bien reçu.", delai=0.0):
        self.appels, self.reponse, self.delai = [], reponse, delai

    async def arun(self, texte, user_id=None, session_id=None):
        self.appels.append(texte)
        await asyncio.sleep(self.delai)
        return Sortie(self.reponse)


class Exp:
    def __init__(self):
        self.journal = []

    async def texte(self, vers, texte):
        self.journal.append(("texte", texte))

    async def lu(self, message_id):
        self.journal.append(("lu", message_id))

    async def reaction(self, vers, message_id, emoji):
        self.journal.append(("reaction", emoji))

    async def vocal(self, vers, audio, ogg):
        self.journal.append(("vocal", audio, ogg))

    async def telecharger(self, media_id):
        return b"OggS-vocal-" + media_id.encode()

    async def modele(self, vers, nom, langue, variables):
        self.journal.append(("modele", nom, langue, variables))


class FausseVoie:
    def __init__(self, transcription="Bonjour, je cherche un rendez-vous", panne_voix=False, parle=True):
        self.transcription, self.panne_voix, self.parle, self.ecoute = transcription, panne_voix, parle, True
        self.dits = []

    async def transcrire(self, audio):
        if self.transcription is None:
            raise RuntimeError("illisible")
        return self.transcription

    async def dire(self, texte):
        if self.panne_voix:
            raise RuntimeError("panne")
        self.dits.append(texte)
        return b"OggS-audio", True


class FauxContacts:
    def __init__(self, dernier=None):
        self.notes, self._dernier = [], dernier

    def noter(self, personne, quand):
        self.notes.append((personne, quand))

    def dernier(self, personne):
        return self._dernier


def entrant(ident="w1", texte="Bonjour", vocal=""):
    return Entrant(id=ident, de="+41790000000", texte=texte, envoye=time.time(), genre="audio" if vocal else "text", vocal=vocal)


async def tourner(c: Conversations, *messages):
    for m in messages:
        c.recevoir(m)
    while c.taches:
        await asyncio.gather(*list(c.taches), return_exceptions=True)


def conversations(agent=None, voie=None, contacts=None, reecrire=None, **autres):
    exp = Exp()
    c = Conversations(conf(**autres), agent or Agent(), exp, voie, contacts, reecrire, attente=0.02, seuil_regard=30)
    return c, exp


def test_messages_rapproches_lus_ensemble():
    agent = Agent()
    c, exp = conversations(agent)
    asyncio.run(tourner(c, entrant("w1", "Bonjour"), entrant("w2", "je cherche un appartement")))
    assert agent.appels == ["Bonjour\nje cherche un appartement"]
    assert ("lu", "w2") in exp.journal and exp.journal[-1] == ("texte", "Bien reçu.")


def test_vocal_recu_vocal_rendu():
    agent, voie = Agent("C'est noté, à jeudi."), FausseVoie()
    c, exp = conversations(agent, voie, reecrire=None)
    asyncio.run(tourner(c, entrant("w1", "", vocal="m1")))
    assert agent.appels == ["Bonjour, je cherche un rendez-vous"]
    assert [e[0] for e in exp.journal if e[0] != "lu"] == ["vocal"]


def test_vocal_avec_lien_part_aussi_par_ecrit():
    c, exp = conversations(Agent("Voici le lien : https://exemple.ch/rdv"), FausseVoie())
    asyncio.run(tourner(c, entrant("w1", "", vocal="m1")))
    assert [e[0] for e in exp.journal if e[0] != "lu"] == ["vocal", "texte"]


def test_voix_en_panne_reponse_ecrite():
    c, exp = conversations(Agent("C'est noté."), FausseVoie(panne_voix=True))
    asyncio.run(tourner(c, entrant("w1", "", vocal="m1")))
    assert [e for e in exp.journal if e[0] != "lu"] == [("texte", "C'est noté.")]


def test_vocal_illisible():
    agent = Agent()
    c, exp = conversations(agent, FausseVoie(transcription=None))
    asyncio.run(tourner(c, entrant("w1", "", vocal="m1")))
    assert agent.appels == [] and exp.journal[-1] == ("texte", NON_COMPRIS)


def test_texte_recu_texte_rendu_meme_avec_une_voix():
    c, exp = conversations(Agent("Bien reçu."), FausseVoie())
    asyncio.run(tourner(c, entrant("w1", "Bonjour")))
    assert exp.journal[-1] == ("texte", "Bien reçu.")


def test_reecriture_orale_utilisee():
    voie = FausseVoie()

    async def reecrire(demande):
        assert "Écrit" in demande
        return "C'est noté \u2014 à jeudi"

    c, _ = conversations(Agent("C'est noté."), voie, reecrire=reecrire)
    asyncio.run(tourner(c, entrant("w1", "", vocal="m1")))
    assert voie.dits == ["C'est noté, à jeudi"]


def test_regard_pose_puis_retire():
    exp = Exp()
    c = Conversations(conf(), Agent(delai=0.15), exp, attente=0.01, seuil_regard=0.05)
    asyncio.run(tourner(c, entrant()))
    reactions = [e[1] for e in exp.journal if e[0] == "reaction"]
    assert reactions == [REGARD, ""]


def test_pas_de_regard_si_desactive_ou_rapide():
    exp = Exp()
    c = Conversations(conf(reactions=False), Agent(delai=0.1), exp, attente=0.01, seuil_regard=0.02)
    asyncio.run(tourner(c, entrant()))
    assert not [e for e in exp.journal if e[0] == "reaction"]


def test_contact_note_a_chaque_tour():
    contacts = FauxContacts()
    c, _ = conversations(contacts=contacts)
    asyncio.run(tourner(c, entrant()))
    assert contacts.notes and contacts.notes[0][0] == "+41790000000"


@pytest.mark.parametrize("dernier,modeles,attendu", [
    (time.time() - 60, {}, "libre"),
    (time.time() - 30 * 3600, {"rappel": {"nom": "rappel_client", "langue": "fr"}}, "modele"),
    (None, {}, "attente"),
])
def test_message_de_soi_meme_et_fenetre(dernier, modeles, attendu):
    c, exp = conversations(contacts=FauxContacts(dernier), modeles_meta=modeles)
    assert asyncio.run(c.ecrire_de_soi_meme("+41790000000", "Relancer M. Exemple", "rappel")) == attendu
    if attendu == "modele":
        assert exp.journal == [("modele", "rappel_client", "fr", ["Relancer M. Exemple"])]


def test_fenetre():
    assert fenetre_ouverte(time.time() - 3600) and not fenetre_ouverte(time.time() - 25 * 3600) and not fenetre_ouverte(None)


# La voix, sans réseau


def test_outils_de_voix():
    assert a_ecrire("écrivez à contact@exemple.ch") and a_ecrire("appelez le +41 22 000 00 00")
    assert not a_ecrire("le prix est de 4 200 000 CHF")
    assert a_dire("**Bonjour** \U0001F600 https://x.ch/a") == "Bonjour"
    assert d_un_tenant("Bonjour...\nça va \u2014 oui") == "Bonjour ça va, oui"
    assert langue("Hello, thanks for your message") == "en" and langue("Bonjour, merci pour votre message") == "fr"
    v = configuration.Voix(voix=VOIX_FR, par_langue={"en": VOIX_EN})
    assert voix_pour(v, "Hello, thanks for your message") == VOIX_EN and voix_pour(v, "Bonjour") == VOIX_FR


def test_reglages_de_voix_valides():
    with pytest.raises(ValidationError):
        configuration.Voix(voix="pas une voix!")
    with pytest.raises(ValidationError):
        configuration.Voix(serveur="http://non-chiffre")
    with pytest.raises(ValidationError):
        conf(modeles_meta={"rappel": {"nom": "Avec Majuscules"}})


def test_oral_retombe_sur_l_ecrit():
    async def panne(_):
        raise RuntimeError("x")

    assert asyncio.run(pour_la_voix(panne, "C'est noté.")) == "C'est noté."
    assert "Entreprise exemple" in consignes(conf()) and "Four Seasons" not in consignes(conf())


def test_appels_http_meta_et_elevenlabs():
    vus = []

    def repondre(r: httpx.Request):
        vus.append(r)
        if r.url.path.endswith("/media"):
            return httpx.Response(200, json={"id": "media-1"})
        if r.url.path.endswith("/speech-to-text"):
            return httpx.Response(200, json={"text": "  Bonjour   Alix "})
        if "/text-to-speech/" in r.url.path:
            return httpx.Response(200, content=b"OggS" + b"0" * 200)
        if r.url.host == "media.exemple":
            return httpx.Response(200, content=b"audio")
        if r.url.path.endswith("/m1"):
            return httpx.Response(200, json={"url": "https://media.exemple/m1", "file_size": 10})
        return httpx.Response(200, json={})

    client = httpx.AsyncClient(transport=httpx.MockTransport(repondre))
    exp = Expediteur("jeton", "100000000000001", "v26.0", client)
    voie = Voie("cle", configuration.Voix(voix=VOIX_FR), client)

    async def scenario():
        assert await exp.telecharger("m1") == b"audio"
        assert await voie.transcrire(b"x") == "Bonjour Alix"
        audio, ogg = await voie.dire("Bonjour")
        assert ogg
        await exp.vocal("+41790000000", audio, ogg)
        await exp.reaction("+41790000000", "w1", REGARD)
        await exp.lu("w1")
        await exp.modele("+41790000000", "rappel_client", "fr", ["x"])

    asyncio.run(scenario())
    stt = next(r for r in vus if r.url.path.endswith("/speech-to-text"))
    assert stt.headers["xi-api-key"] == "cle" and b"scribe_v3" in stt.content
    tts = next(r for r in vus if "/text-to-speech/" in r.url.path)
    assert tts.url.params["output_format"] == "opus_48000_64" and json.loads(tts.content)["model_id"] == "eleven_v4"
    envoi_vocal = json.loads(next(r for r in vus if r.url.path.endswith("/messages") and b'"audio"' in r.content).content)
    assert envoi_vocal["audio"] == {"id": "media-1", "voice": True}
    assert all(r.headers.get("authorization") == "Bearer jeton" for r in vus if r.url.host == "graph.facebook.com")


# La table des contacts, sur SQLite et sur Postgres


@pytest.mark.parametrize("genre", ["sqlite"] + (["postgres"] if os.environ.get("TEST_POSTGRES_URL") else []))
def test_contacts(tmp_path, genre):
    url = f"sqlite:///{tmp_path}/c.db" if genre == "sqlite" else os.environ["TEST_POSTGRES_URL"]
    c = stockage.Contacts(url)
    personne = f"+4179{genre}"
    c.noter(personne, 100.0)
    c.noter(personne, 50.0)
    c.noter(personne, 200.0)
    assert c.dernier(personne) == 200.0 and c.dernier("+1000") is None
    fichier = tmp_path / "export.jsonl"
    stockage.exporter(url, fichier)
    assert "megga_contacts" in fichier.read_text()
