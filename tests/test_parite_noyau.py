"""Parité du noyau avec Alix FSP (relecture du 17.11.2026) : chaque correction, et son réglage par défaut qui garde le
comportement des autres clients."""

import asyncio
import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from noyau import accueil as accueils
from noyau import config as configuration
from noyau import humeur as humeurs
from noyau import phrases, stockage, tour as tours
from noyau.agent import REGLES, construire, modele
from noyau.fil import TenueDuFil
from noyau.garde import TROP_TU, Debit, Plafond
from noyau.memoire import Memoire
from noyau.oral import consignes as consignes_orales
from noyau.oral import pour_la_voix
from noyau.rappels import contexte as rappels_prevus
from noyau.rappels import lire_quand
from noyau.tour import Conversations
from noyau.typographie import Remplaceur
from noyau.voix import Voie, a_ecrire, balises_permises, langue
from noyau.whatsapp import Entrant, Expediteur, fenetre_ouverte
from test_lot2 import VOIX_FR, Agent, Exp, FausseVoie, FauxContacts, Sortie, conf, entrant, tourner
from test_lot7_1 import FSP_WA, GREG, agent_fsp

MOI = "+41790000000"
TU = {"gestionnaire": {"consignes": "", "outils": ["rappels"], "tutoiement": True}}


class Suite(Agent):
    """Rend ses réponses dans l'ordre, puis la dernière."""

    def __init__(self, *reponses):
        super().__init__(reponses[0])
        self.reponses = list(reponses)

    async def arun(self, texte, user_id=None, session_id=None, images=None):
        self.appels.append(texte)
        self.sessions = [*getattr(self, "sessions", []), session_id]
        self.images = [*getattr(self, "images", []), images]
        return Sortie(self.reponses.pop(0) if len(self.reponses) > 1 else self.reponses[0])


class ExpCartes(Exp):
    def __init__(self):
        super().__init__()
        self.sans_cartes = set()
        self.vus_sans_cartes = []

    async def texte(self, vers, texte, apercu=False):
        self.vus_sans_cartes.append(set(self.sans_cartes))
        await super().texte(vers, texte)


def gestionnaire(c: Conversations, *messages):
    async def f():
        for m in messages:
            c.recevoir(m, "gestionnaire")
        while c.taches:
            await asyncio.gather(*list(c.taches), return_exceptions=True)

    asyncio.run(f())


def c_de(agent, voie=None, exp=None, **autres):
    exp = exp or Exp()
    return Conversations(conf(**autres), agent, exp, voie, attente=0.01, seuil_regard=30), exp


# M1, M2 : réponse vide, phrase coupée


def test_reponse_vide_un_dernier_appel_puis_l_excuse_au_tutoiement():
    agent = Suite("", "Voici la réponse.")
    c, exp = c_de(agent)
    asyncio.run(tourner(c, entrant()))
    assert agent.appels[1] == phrases.FINIR and exp.journal[-1] == ("texte", "Voici la réponse.")
    agent = Suite("")
    c, exp = c_de(agent, roles=TU)
    gestionnaire(c, entrant())
    assert exp.journal[-1] == ("texte", phrases.EXCUSE[1])


def test_phrase_coupee_reecrite_seulement_si_reglee():
    c, exp = c_de(Suite("Oui je transmets votre", "Oui, je transmets votre demande."))
    asyncio.run(tourner(c, entrant()))
    assert exp.journal[-1] == ("texte", "Oui je transmets votre")  # par défaut, rien ne change
    agent = Suite("Oui je transmets votre", "Oui, je transmets votre demande.")
    c, exp = c_de(agent, reprendre_coupees=True)
    asyncio.run(tourner(c, entrant()))
    assert agent.appels[1] == phrases.REPRENDRE and exp.journal[-1] == ("texte", "Oui, je transmets votre demande.")
    assert phrases.inacheve("Voici le lien https://x.ch/a") is False and phrases.inacheve("Bien reçu 👍") is False


def test_seconde_passe_d_un_pack():
    agent = Suite("Je transmets à Greg.", "C'est transmis, Greg vous rappelle.")
    vus = []

    async def passe(role, personne, reponse, debut):
        vus.append((role, personne, reponse))
        return "Contexte : rien n'est parti." if not vus[1:] else None

    c, exp = c_de(agent)
    c.seconde_passe = passe
    asyncio.run(tourner(c, entrant()))
    assert agent.appels[1] == "[Contexte : rien n'est parti.]" and exp.journal[-1] == ("texte", "C'est transmis, Greg vous rappelle.")


# M4, D13 : les phrases fixes au tutoiement, les pièces passées au modèle


def test_phrases_fixes_au_tutoiement():
    c, exp = c_de(Agent(), FausseVoie(transcription=None), roles=TU)
    gestionnaire(c, entrant("w1", "", vocal="m1"))
    assert exp.journal[-1] == ("texte", phrases.NON_COMPRIS[1])
    c, exp = c_de(Agent(), roles=TU)
    c.debit = Debit(maximum=1, fenetre=600)
    gestionnaire(c, entrant("w1", "un"))
    gestionnaire(c, entrant("w2", "deux"))
    assert exp.journal[-1] == ("texte", TROP_TU)
    assert phrases.rappel("relancer M. X.", True) == "Rappel, comme tu me l'avais demandé : relancer M. X."
    assert phrases.rappel("relancer M. X", False) == "Rappel : relancer M. X"


def test_pieces_passees_au_modele():
    agent = Agent()
    c, exp = c_de(agent, FausseVoie(transcription=None), pieces_au_modele=True)
    position = Entrant(id="w2", de=MOI, texte="", envoye=time.time(), genre="location")
    asyncio.run(tourner(c, entrant("w1", "", vocal="m1"), position))
    assert agent.appels == [f"{phrases.NON_TRANSCRIT}\n{phrases.piece('une position')}\n{phrases.VOCAL_DIT}"]
    c, exp = c_de(Agent())
    asyncio.run(tourner(c, Entrant(id="w3", de=MOI, texte="", envoye=time.time(), genre="sticker")))
    assert exp.journal[-1] == ("texte", tours.NON_LU)  # par défaut, la phrase fixe


# M5 : le vocal, l'écrit sur demande, pas de cartes


def test_vocal_par_ecrit_sur_demande_et_sur_un_oui():
    voie = FausseVoie(transcription="Envoie-moi ça par écrit")
    agent = Agent("Voici le détail complet.")
    c, exp = c_de(agent, voie)
    asyncio.run(tourner(c, entrant("w1", "", vocal="m1")))
    assert phrases.VOCAL_ECRIT in agent.appels[0]
    assert [e[0] for e in exp.journal if e[0] != "lu"] == ["vocal", "texte"]

    async def offre(_):
        return "Tu en as cinq, je t'envoie la liste par écrit ?"

    voie = FausseVoie(transcription="Qu'est-ce que j'ai à Cologny ?")
    agent = Agent("Cinq biens : A, B, C, D et E.")
    c, exp = c_de(agent, voie)
    c.reecrire = offre
    asyncio.run(tourner(c, entrant("w1", "", vocal="m1")))
    assert [e[0] for e in exp.journal if e[0] != "lu"] == ["vocal"]
    voie.transcription = "Oui vas-y"
    asyncio.run(tourner(c, entrant("w2", "", vocal="m2")))
    assert phrases.VOCAL_ECRIT in agent.appels[1] and [e[0] for e in exp.journal if e[0] != "lu"] == ["vocal", "vocal", "texte"]


def test_pas_de_cartes_dans_un_vocal_seul():
    exp = ExpCartes()
    c, _ = c_de(Agent("Voici le lien : https://x.ch"), FausseVoie(), exp=exp)

    async def pendant(texte, user_id=None, session_id=None):
        assert c.vocal_seul(MOI)
        return Sortie("C'est noté.")

    c.agent.arun = pendant
    asyncio.run(tourner(c, entrant("w1", "", vocal="m1")))
    assert not c.vocal_seul(MOI)
    vrai = Expediteur("j", "100000000000001", "v26.0", httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={}))))
    vrai.sans_cartes.add(MOI)
    with pytest.raises(RuntimeError, match="Pas de cartes"):
        asyncio.run(vrai.carrousel(MOI, "x", []))


# M6 : la langue imposée à ElevenLabs


def test_langue_imposee_relue_sans_si_refusee():
    corps = []

    def repondre(r):
        d = json.loads(r.content)
        corps.append(d)
        if "language_code" in d and d["language_code"] == "es":
            return httpx.Response(422, json={"detail": "non"})
        return httpx.Response(200, content=b"OggS" + b"0" * 200)

    voie = Voie("cle", configuration.Voix(voix=VOIX_FR), httpx.AsyncClient(transport=httpx.MockTransport(repondre)))
    asyncio.run(voie.dire("Bonjour, je vous rappelle demain."))
    assert corps[-1]["language_code"] == "fr"
    asyncio.run(voie.dire("Hola, gracias, tengo una casa muy bonita."))
    assert corps[-2]["language_code"] == "es" and "language_code" not in corps[-1]
    assert langue("Hola, ¿cómo está usted?") == "es"
    sans = Voie("cle", configuration.Voix(voix=VOIX_FR, imposer_langue=False), httpx.AsyncClient(transport=httpx.MockTransport(repondre)))
    asyncio.run(sans.dire("Bonjour"))
    assert "language_code" not in corps[-1]


def test_balises_de_jeu():
    assert balises_permises("[softly] Je comprends. [shouts] Non.", ("softly",)) == "[softly] Je comprends. Non."
    conf_b = conf(voix={"voix": VOIX_FR, "balises": ["warmly", "softly"]})
    assert "[warmly], [softly]" in consignes_orales(conf_b)
    with pytest.raises(ValidationError):
        configuration.Voix(balises=["SOFTLY!"])

    async def r(_):
        return "[warmly] C'est fait. [loud] Bravo."

    assert asyncio.run(pour_la_voix(r, "C'est fait.", balises=("warmly",))) == "[warmly] C'est fait. Bravo."
    assert asyncio.run(pour_la_voix(r, "C'est fait.")) == "C'est fait. Bravo."


# M7 : les réactions d'humeur


def test_reaction_d_humeur_puis_trois_tours_sans():
    vus = []

    async def juger(texte, genre):
        vus.append(genre)
        return "🎉"

    c, exp = c_de(Agent("Bravo !"), roles={"gestionnaire": {"outils": ["rappels"], "humeur": "complice"}})
    c.juger = juger
    for i in range(5):
        gestionnaire(c, entrant(f"w{i}", "J'ai vendu la villa !"))
    reactions = [e for e in exp.journal if e[0] == "reaction"]
    assert reactions == [("reaction", "🎉"), ("reaction", "🎉")] and vus == ["complice", "complice"]
    assert humeurs.lire('{"reaction": "😂"}', "sobre") == "" and humeurs.lire('```json\n{"reaction": "🎉"}\n```') == "🎉"
    c, exp = c_de(Agent())  # sans réglage, aucun juge
    c.juger = juger
    asyncio.run(tourner(c, entrant()))
    assert not [e for e in exp.journal if e[0] == "reaction"]


# D1 : l'historique


def test_conversation_repart_a_neuf_apres_l_inactivite(tmp_path):
    url = f"sqlite:///{tmp_path}/c.db"
    etats = stockage.Etats(url)
    agent = Suite("Bien reçu.")
    c = Conversations(conf(historique={"tours": 40, "inactivite": 12}), agent, Exp(), attente=0.01, etats=etats)
    asyncio.run(tourner(c, entrant("w1")))
    asyncio.run(tourner(c, entrant("w2")))
    assert agent.sessions == [MOI, MOI]
    etats.ecrire(MOI, "session", {"id": MOI, "debut": 0, "derniere": time.time() - 13 * 3600})
    c._sessions.clear()
    asyncio.run(tourner(c, entrant("w3")))
    assert agent.sessions[-1].startswith(f"{MOI}:") and etats.lire(MOI, "session")["debut"] > 0
    agent_reel = construire(conf(historique={"tours": 40}), None, {}, principal=modele("deepseek-v4-pro", {"DEEPSEEK_API_KEY": "x"}))
    assert agent_reel.num_history_runs == 40


def test_le_fil_resume_ce_qui_precede_la_remise_a_zero(tmp_path):
    url = f"sqlite:///{tmp_path}/f.db"
    fil, etats = stockage.Fil(url), stockage.Etats(url)
    for i in range(4):
        fil.noter(MOI, "recu", "texte", f"message {i}", 100.0 + i)
    resumes = []

    async def resumer(consigne, demande):
        resumes.append(demande)
        return "M. X cherche une villa."

    tenue = TenueDuFil(fil, etats, resumer, dans_l_historique=24)
    assert not asyncio.run(tenue.apres(MOI))  # rien n'est sorti de l'historique
    etats.ecrire(MOI, "session", {"id": f"{MOI}:1", "debut": 200.0, "derniere": 200.0})
    fil.noter(MOI, "recu", "texte", "nouveau", 201.0)
    assert asyncio.run(tenue.apres(MOI)) and "message 3" in resumes[0] and "nouveau" not in resumes[0]


# D2 : la mémoire par les outils


def test_memoire_retenir_oublier_souvenirs(tmp_path):
    base = stockage.base_agno(f"sqlite:///{tmp_path}/m.db")
    m = Memoire(base, montres=5)
    assert "Retenu" in m.retenir(MOI, "M. Smith, anglais, cherche une vue lac, 5 millions", "client")
    assert "Déjà retenu" in m.retenir(MOI, "m. smith, anglais, cherche une vue lac, 5 millions", "client")
    with pytest.raises(ValueError):
        m.retenir(MOI, "Le mot de passe du site est 1234", "autre")
    for i in range(6):
        m.retenir(MOI, f"Affaire numéro {i} en cours", "en cours" if i < 2 else "autre")
    rappel = m.rappel(MOI, "le client anglais")
    assert "Smith" in rappel and "Affaire numéro 0" in rappel and "autre(s)" in rappel
    ident = m.chercher(MOI, "Smith")[0].memory_id
    assert "Oublié" in m.oublier(MOI, ident) and not m.chercher(MOI, "Smith")
    assert m.rappel("+41000000000") == ""
    agent = construire(conf(memoire={"outils": True}), None, {}, principal=modele("deepseek-v4-pro", {"DEEPSEEK_API_KEY": "x"}))
    assert agent.enable_agentic_memory is False and any("retenir" in c for c in agent.instructions)


# D3 : l'oral réglable, les références


def test_oral_reglable_et_references():
    ref = r"\b(?=[0-9A-Z]*\d)(?=[0-9A-Z]*[A-Z])[0-9A-Z]{4}-[0-9A-Z]{4}\b"
    assert a_ecrire("La villa G8LR-2DW8 est en ligne.", ref) and not a_ecrire("La villa G8LR-2DW8 est en ligne.")
    propre = conf(oral={"consignes": "Tu parles comme Alix.", "references": ref})
    assert consignes_orales(propre) == "Tu parles comme Alix."
    assert "référence" in consignes_orales(conf(oral={"references": ref}))
    demandes = []

    async def r(d):
        demandes.append(d)
        return "La villa G8LR-2DW8 est en ligne."

    voie = FausseVoie()
    c = Conversations(conf(oral={"references": ref}, roles={"visiteur": {"oral": "Elle le vouvoie."}}), Agent("La villa G8LR-2DW8 est en ligne."),
                      Exp(), voie, reecrire=r, attente=0.01)
    asyncio.run(_visiteur(c, entrant("w1", "", vocal="m1")))
    assert demandes[0].startswith("À qui tu parles : Elle le vouvoie.") and "G8LR" not in voie.dits[0]
    assert [e[0] for e in c.exp.journal if e[0] != "lu"] == ["vocal", "texte"]
    with pytest.raises(ValidationError):
        conf(oral={"references": "("})


async def _visiteur(c, m):
    c.recevoir(m, "visiteur")
    while c.taches:
        await asyncio.gather(*list(c.taches), return_exceptions=True)


# D4 : les rappels


def test_rappel_sans_heure_et_rappels_dans_le_contexte(tmp_path):
    demain = time.strftime("%Y-%m-%d", time.localtime(time.time() + 2 * 86400))
    t = lire_quand(demain, "Europe/Zurich", heure="09:00")
    assert time.strftime("%H:%M", time.localtime(t)) in ("09:00", "08:00", "10:00")
    assert lire_quand(demain, "Europe/Zurich") < t  # sans réglage, minuit
    rappels = stockage.Rappels(f"sqlite:///{tmp_path}/r.db")
    rappels.ajouter(MOI, t, "relancer M. X")
    assert "relancer M. X" in asyncio.run(rappels_prevus(rappels, "Europe/Zurich")(MOI))
    c = Conversations(conf(rappels={"contexte": True}), Agent(), Exp(), rappels=rappels)
    assert "Rappels prévus" in asyncio.run(c.contexte(MOI))
    assert "Rappels prévus" not in asyncio.run(Conversations(conf(), Agent(), Exp(), rappels=rappels).contexte(MOI))


# D6 : les photos


def test_photos_decrites_gardees_dans_le_message():
    from noyau.whatsapp import Media

    class ExpPhotos(Exp):
        async def telecharger(self, media_id, maximum=0):
            return b"\xff\xd8photo"

    async def decrire(images):
        return [f"un séjour lumineux {i}" for i in range(len(images))]

    agent = Suite("Belles photos.")
    c = Conversations(conf(photos={"max": 10, "decrire": True}), agent, ExpPhotos(), attente=0.01, decrire=decrire)
    photos = [Entrant(id=f"p{i}", de=MOI, texte="", envoye=time.time(), genre="image", media=Media(id=f"m{i}", genre="image"))
              for i in range(7)]
    asyncio.run(tourner(c, *photos))
    assert len(agent.images[0]) == 7 and "[Photo reçue : média 7, on y voit : un séjour lumineux 6]" in agent.appels[0]


# D7 : « en train d'écrire »


def test_en_train_d_ecrire_relance(monkeypatch):
    monkeypatch.setattr(tours, "ECRIT", 0.02)
    c, exp = c_de(Agent(delai=0.1))
    asyncio.run(tourner(c, entrant()))
    assert len([e for e in exp.journal if e[0] == "lu"]) >= 3


# D8, D14, D16


def test_claude_reflexion_jetons_effort_et_regles():
    m = modele("claude-sonnet-5-5", {"ANTHROPIC_API_KEY": "x"}, 16000, True, "medium")
    assert m.max_tokens == 16000 and m.thinking == {"type": "adaptive"} and m.output_config == {"effort": "medium"}
    d = modele("claude-sonnet-5-5", {"ANTHROPIC_API_KEY": "x"})
    assert d.max_tokens == 4096 and d.thinking is None
    assert modele("deepseek-flash", {"DEEPSEEK_API_KEY": "x"}).id == "deepseek-flash"  # DeepSeek sert de petit modèle
    assert conf(modeles={"oral": "deepseek-flash"}).modeles.petit() == "deepseek-flash"
    assert conf(modeles={"oral": "deepseek-flash", "fil": "claude-sonnet-5-5"}).modeles.du_fil() == "claude-sonnet-5-5"
    assert "sans titres ni tableaux" not in REGLES[0] and "seule étoile" in REGLES[0]
    assert fenetre_ouverte(time.time() - 23 * 3600) and not fenetre_ouverte(time.time() - 24 * 3600 + 300)


# D9 : les plafonds par rôle


def test_plafonds_par_role():
    p = Plafond(par_personne=2, client=100, par_role={"gestionnaire": 3, "visiteur": 1})
    for _ in range(3):
        assert p.libre(GREG, "gestionnaire") is None
        p.compter(GREG, "gestionnaire")
    assert p.libre(GREG, "gestionnaire") == "personne" and p._total == 0
    p.compter(MOI, "visiteur")
    assert p.libre(MOI, "visiteur") == "personne"
    d = Debit(maximum=1, fenetre=600)
    assert d.permis(GREG, maximum=0) and d.permis(GREG, maximum=0) and d.libre(GREG, maximum=0)
    c, _ = c_de(Agent(), roles={"gestionnaire": {"outils": ["rappels"], "par_jour": 400, "par_dix_minutes": 0}})
    assert c.plafond.par_role == {"gestionnaire": 400} and c._rafale("gestionnaire") == 0


# D11 : le prénom du profil, l'accueil jamais redit


def test_prenom_du_profil_et_accueil_redit():
    c = Conversations(conf(roles={"visiteur": {"prenom_du_profil": True}}), Agent(), Exp())
    c._roles[MOI], c._profils[MOI] = "visiteur", "anna müller"
    assert "le prénom Anna" in asyncio.run(c.contexte(MOI))
    accueil = {"fr": "Bonjour, je suis Alix.\n\nSouhaitez-vous acheter, louer ou vendre un bien ?"}
    redit = (r"acheter, louer ou vendre",)
    assert accueils.apres_accueil("Bonjour ! Volontiers.\n\nVous voulez acheter, louer ou vendre ?", accueil["fr"], redit) == "Volontiers."
    ecrit = "Bonjour, je suis Alix.\n\nSouhaitez-vous acheter, louer ou vendre un bien ?\n\nHello! Tell me.\n\nJe cherche pour vous."
    assert accueils.sans_doublon(ecrit, "Hallo", accueil, redit).endswith("Je cherche pour vous.")
    assert accueils.sans_doublon(ecrit, "Bonjour", accueil, redit).endswith("vendre un bien ?")


# Le filtre de noms au point d'envoi


FILTRE = [{"motif": r"(?:\b(?:Gr[ée]gory|Gregory|Greg|M\.|Monsieur|Mr\.?)\s+)?\bLyonnet\b", "par": "Greg"},
          {"motif": r"\bGr[ée]gory\b", "par": "Greg"}]


def test_filtre_de_noms_partout_sauf_liens_et_identifiants():
    r = Remplaceur(conf(remplacements=FILTRE).remplacements)
    assert r.texte("Grégory Lyonnet vous rappelle, écrivez à gregory.lyonnet@agence.ch") == \
        "Greg vous rappelle, écrivez à gregory.lyonnet@agence.ch"
    assert r.texte("M. Lyonnet et Gregory") == "Greg et Greg"
    sans = Remplaceur(conf(remplacements=[{"motif": r"\s*\bLyonnet\b"}]).remplacements)
    assert sans.texte("Greg Lyonnet arrive.") == "Greg arrive."
    vus = []
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda q: vus.append(json.loads(q.content)) or httpx.Response(200, json={})))
    exp = Expediteur("j", "100000000000001", "v26.0", client, remplaceur=r)
    asyncio.run(exp.modele("+41790000001", "fsp_rappel", "fr", ["appeler Grégory"], charge="vocal"))
    asyncio.run(exp.document("+41790000001", "Lyonnet.pdf", lien="https://x.ch/Lyonnet.pdf", legende="Fiche de M. Lyonnet"))
    assert vus[0]["template"]["components"][0]["parameters"][0]["text"] == "appeler Greg"
    assert vus[0]["template"]["components"][1]["parameters"][0]["payload"] == "vocal"
    assert vus[1]["document"]["caption"] == "Fiche de Greg" and vus[1]["document"]["link"] == "https://x.ch/Lyonnet.pdf"
    c, e = c_de(Agent("Grégory vous rappelle."), remplacements=FILTRE)
    asyncio.run(tourner(c, entrant()))
    assert e.journal[-1] == ("texte", "Greg vous rappelle.")
    with pytest.raises(ValidationError):
        conf(remplacements=[{"motif": "x*"}])


# Le vocal envoyé de soi-même, à la demande de l'équipe


class ExpVocal(Exp):
    def __init__(self):
        super().__init__()

    async def modele(self, vers, nom, langue, variables, charge=""):
        self.journal.append(("modele", nom, variables, charge))


def test_vocal_de_soi_meme(tmp_path):
    url = f"sqlite:///{tmp_path}/v.db"
    voie, exp = FausseVoie(), ExpVocal()
    contacts = FauxContacts(time.time() - 60)
    c = Conversations(conf(whatsapp={"numero_id": "100000000000001"}, modeles_meta={"vocal": {"nom": "fsp_vocal_alix"}}),
                      Agent(), exp, voie, contacts, attente=0.01, differes=stockage.Differes(url), etats=stockage.Etats(url))
    assert asyncio.run(c.vocal_de_soi_meme(MOI, "Bonjour Greg, la villa est vendue.")) == "parti"
    assert exp.journal[-1][0] == "vocal" and "vendue" in asyncio.run(c.contexte(MOI))
    contacts._dernier = time.time() - 30 * 3600
    assert asyncio.run(c.vocal_de_soi_meme(MOI, "Un second message.")) == "attente"
    assert exp.journal[-1] == ("modele", "fsp_vocal_alix", ["Alix"], "vocal")
    contacts._dernier = time.time()
    bouton = Entrant(id="b1", de=MOI, texte="Écouter le message", envoye=time.time(), genre="button", choix="vocal")
    asyncio.run(tourner(c, bouton))
    assert voie.dits[-1] == "Un second message." and c.agent.appels == []
    assert asyncio.run(Conversations(conf(), Agent(), Exp()).vocal_de_soi_meme(MOI, "x")) == "sans voix"


def test_route_vocal(tmp_path):
    cle = "v" * 40
    import noyau.app as app_mod

    t, agents, exp, app, url = agent_fsp(tmp_path)
    assert t.post("/vocal", json={"numero": GREG, "texte": "x"}).status_code == 404  # sans VOCAL_CLE
    env = {"CLIENT_CONFIG": json.dumps(FSP_WA), "DATABASE_URL": url, "META_APP_SECRET": "s", "INTERNE_TOKEN": "i",
           "GESTIONNAIRES": json.dumps({GREG: "greg@agence.ch"}), "VOCAL_CLE": cle}
    app = app_mod.creer(env, agent=Agent(), agents={n: Agent() for n in ("gestionnaire", "partenaire", "visiteur")},
                        expediteur=exp, voie=FausseVoie(), contacts=FauxContacts(time.time() - 60), attente=0.01)
    exp.vocal = lambda *a: asyncio.sleep(0)
    with TestClient(app) as t:
        h = {"authorization": f"Bearer {cle}"}
        assert t.post("/vocal", json={"numero": GREG, "texte": "x"}, headers={"authorization": "Bearer faux"}).status_code == 401
        assert t.post("/vocal", json={"numero": "+41799999999", "texte": "x"}, headers=h).status_code == 400  # pas un gestionnaire
        r = t.post("/vocal", json={"numero": GREG, "texte": "La villa est vendue."}, headers=h)
        assert r.status_code == 200 and r.json() == {"etat": "parti"}
