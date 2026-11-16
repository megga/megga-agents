import asyncio
import json
import os
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from noyau import config as configuration
from noyau import stockage
from noyau.agent import construire
from noyau.app import creer
from noyau.garde import MASQUE, TROP, Debit, masquer_secrets
from noyau.rappels import lire_quand, outils
from noyau.tour import Conversations
from noyau.whatsapp import Entrant

FUSEAU = "Europe/Zurich"
MOI = "+41790000000"
AUTRE = "+41790000001"


def conf(**autres):
    d = configuration.lire("clients/exemple.yaml").model_dump()
    d.update(autres)
    return configuration.lire(d)


def ctx(personne):
    return SimpleNamespace(user_id=personne)


def demain():
    return time.strftime("%Y-%m-%dT%H:%M", time.localtime(time.time() + 86400))


@pytest.fixture(params=["sqlite"] + (["postgres"] if os.environ.get("TEST_POSTGRES_URL") else []))
def rappels(request, tmp_path):
    url = f"sqlite:///{tmp_path}/r.db" if request.param == "sqlite" else os.environ["TEST_POSTGRES_URL"]
    r = stockage.Rappels(url)
    if request.param == "postgres":  # base partagée : on repart d'une table vide
        with r._e.begin() as c:
            c.execute(r._t.delete())
    return r


# Les rappels


def test_quand():
    maintenant = time.time()
    assert lire_quand(demain(), FUSEAU) > maintenant
    for mauvais in ("hier", "2020-01-01T09:00", "2099-01-01T09:00"):
        with pytest.raises(ValueError):
            lire_quand(mauvais, FUSEAU)


def test_outils_par_personne(rappels):
    def synchrone(f):  # les outils sont asynchrones : la base se lit hors de la boucle (relecture du 16.11.2026)
        return lambda *a, **k: asyncio.run(f(*a, **k))

    rappeler, mes_rappels, annuler = map(synchrone, outils(rappels, FUSEAU))
    reponse = rappeler(demain(), "relancer M. Exemple", run_context=ctx(MOI))
    ident = reponse.split()[1]
    assert "relancer M. Exemple" in mes_rappels(run_context=ctx(MOI))
    assert mes_rappels(run_context=ctx(AUTRE)) == "Aucun rappel en attente."
    assert annuler(ident, run_context=ctx(AUTRE)).startswith("Aucun")  # pas le rappel d'un autre
    assert annuler(ident, run_context=ctx(MOI)) == "Rappel annulé."
    with pytest.raises(ValueError):
        rappeler(demain(), "x", run_context=ctx(None))


def test_echus_differes_et_prochain(rappels):
    a = rappels.ajouter(MOI, time.time() - 5, "passé")
    rappels.ajouter(MOI, time.time() + 3600, "plus tard")
    assert [r["id"] for r in rappels.echus(time.time())] == [a]
    assert rappels.prochain() == pytest.approx(time.time() - 5, abs=2)
    rappels.marquer(a, "differe")
    assert [r["id"] for r in rappels.differes(MOI)] == [a]
    assert rappels.prochain() > time.time()


# Les garde-fous


def test_secrets_masques():
    t = "base postgresql://u:p@hote/db, clé sk-ant-api03-abcdefghijklmnopqrstuv, jeton EAAB" + "x1" * 20
    assert "postgresql" not in masquer_secrets(t) and "sk-ant" not in masquer_secrets(t) and "EAAB" not in masquer_secrets(t)
    sain = "Votre rendez-vous du 20.11.2026 à 09:00, au +41 22 567 04 07, réf 1476827312177165."
    assert masquer_secrets(sain) == sain
    assert MASQUE in masquer_secrets("a1" * 25)


def test_un_lien_d_annonce_n_est_pas_un_secret():
    """Relecture du 16.11.2026 (C1) : un identifiant d'annonce long et chiffré, dans un lien, partait en « [masqué] »."""
    for lien in ("https://fspdubai.com/property/dubai-high-floor-2-br-apartment-bright-unit-with-canal-pool-view",
                 "https://www.jamesedition.com/real_estate/marbella-spain/villa-with-sea-views-in-sierra-blanca-12345678",
                 "http://fspdubai.com/en/property/dubai-premium-4-br-townhouse-high-potential-investment."):
        texte = f"La fiche : {lien} (à voir)"
        assert masquer_secrets(texte) == texte
    # Hors d'un lien, ou dans ses paramètres, le jeton reste masqué ; les clés connues, partout.
    jeton = "a1" * 25
    assert masquer_secrets(f"jeton {jeton}") == f"jeton {MASQUE}"
    assert masquer_secrets(f"https://site.ch/x?jeton={jeton}") == f"https://site.ch/x?jeton={MASQUE}"
    assert MASQUE in masquer_secrets("https://site.ch/sk-ant-api03-abcdefghijklmnopqrstuv")
    assert MASQUE in masquer_secrets("https://u:p@h/postgresql://u:motdepasse@hote/db")


def test_debit():
    d = Debit(maximum=2, fenetre=60)
    assert d.permis("p", 0) and d.permis("p", 1) and not d.permis("p", 2)
    assert d.permis("p", 70)
    assert d.prevenir("p", 0) and not d.prevenir("p", 10)


# La conversation


class Agent:
    def __init__(self, reponse="Bien reçu."):
        self.appels, self.reponse = [], reponse

    async def arun(self, texte, user_id=None, session_id=None):
        self.appels.append(texte)
        return SimpleNamespace(content=self.reponse, status="COMPLETED")


class Exp:
    def __init__(self):
        self.journal = []

    async def texte(self, vers, texte):
        self.journal.append(("texte", vers, texte))

    async def lu(self, i):
        pass

    async def reaction(self, *a):
        pass

    async def modele(self, vers, nom, langue, variables):
        self.journal.append(("modele", vers, nom))


class Contacts:
    def __init__(self, dernier):
        self._d = dernier

    def noter(self, *a):
        pass

    def dernier(self, personne):
        return self._d


def entrant(texte="Bonjour", ident="w1"):
    return Entrant(id=ident, de=MOI, texte=texte, envoye=time.time(), genre="text")


async def tourner(c, *messages):
    for m in messages:
        c.recevoir(m)
    while c.taches:
        await asyncio.gather(*list(c.taches), return_exceptions=True)


@pytest.mark.parametrize("dernier,modeles,attendu,etat", [
    (time.time() - 60, {}, "libre", None),
    (time.time() - 30 * 3600, {"rappel": {"nom": "rappel_client"}}, "modele", None),
    (time.time() - 30 * 3600, {}, "attente", "differe"),
])
def test_rappels_echus_selon_la_fenetre(rappels, dernier, modeles, attendu, etat):
    rappels.ajouter(MOI, time.time() - 1, "relancer M. Exemple")
    exp = Exp()
    c = Conversations(conf(modeles_meta=modeles), Agent(), exp, contacts=Contacts(dernier), rappels=rappels, attente=0.01)
    bilan = asyncio.run(c.envoyer_rappels_echus(time.time()))
    assert bilan[attendu] == 1
    if etat:
        assert rappels.differes(MOI) and exp.journal == []
        # Au prochain message de la personne, le rappel part avant la réponse.
        asyncio.run(tourner(c, entrant()))
        assert exp.journal[0] == ("texte", MOI, "Rappel : relancer M. Exemple") and not rappels.differes(MOI)


def test_debit_dans_la_conversation():
    exp, agent = Exp(), Agent()
    c = Conversations(conf(), agent, exp, attente=0.01, debit=Debit(maximum=1, fenetre=600))
    asyncio.run(tourner(c, entrant("un", "w1")))
    asyncio.run(tourner(c, entrant("deux", "w2")))
    asyncio.run(tourner(c, entrant("trois", "w3")))
    assert agent.appels == ["un"]
    assert [e[2] for e in exp.journal].count(TROP) == 1


def test_reponse_jamais_avec_un_secret():
    exp = Exp()
    c = Conversations(conf(), Agent("La base est postgresql://u:p@hote/db"), exp, attente=0.01)
    asyncio.run(tourner(c, entrant()))
    assert "postgresql" not in exp.journal[-1][2]


def test_route_interne_protegee(rappels):
    app = creer({"CLIENT_CONFIG": json.dumps(conf().model_dump()), "META_APP_SECRET": "s", "INTERNE_TOKEN": "jeton"},
                agent=Agent(), expediteur=Exp(), contacts=Contacts(time.time()), rappels=rappels)
    t = TestClient(app)
    assert t.post("/interne/rappels").status_code == 401
    assert t.post("/interne/rappels", headers={"x-megga-interne": "faux"}).status_code == 401
    rappels.ajouter(MOI, time.time() + 600, "plus tard")
    r = t.post("/interne/rappels", headers={"x-megga-interne": "jeton"}).json()
    assert r["prochain"] > time.time() and r["libre"] == 0


def test_agent_a_ses_outils_et_sa_memoire(tmp_path):
    url = f"sqlite:///{tmp_path}/a.db"
    agent = construire(conf(), stockage.base_agno(url), {"ANTHROPIC_API_KEY": "x", "DEEPSEEK_API_KEY": "y"},
                       outils=outils(stockage.Rappels(url), FUSEAU))
    noms = [getattr(o, "__name__", "") for o in agent.tools]
    assert noms == ["rappeler", "mes_rappels", "annuler_rappel"]
    assert agent.enable_agentic_memory is True


def test_un_modele_rappel_refuse_ne_boucle_pas(rappels):
    """Relecture du 16.11.2026 (I10) : un modèle « rappel » suspendu par Meta ne fait plus échouer le rappel toutes les
    5 minutes ; il attend le prochain message, et le modèle « message » l'annonce s'il est réglé."""
    class Refuse(Exp):
        async def modele(self, vers, nom, langue, variables):
            if nom == "rappel_client":
                raise RuntimeError("Meta 400 : modèle en pause")
            self.journal.append(("modele", vers, nom))

    rappels.ajouter(MOI, time.time() - 1, "relancer M. Exemple")
    exp = Refuse()
    c = Conversations(conf(modeles_meta={"rappel": {"nom": "rappel_client"}, "message": {"nom": "attente_client"}}), Agent(), exp,
                      contacts=Contacts(time.time() - 30 * 3600), rappels=rappels, attente=0.01)
    bilan = asyncio.run(c.envoyer_rappels_echus(time.time()))
    assert bilan["echec"] == 0 and bilan["attente"] == 1 and rappels.differes(MOI)
    assert exp.journal == [("modele", MOI, "attente_client")]


def bouton(texte="Afficher", ident="b1"):
    return Entrant(id=ident, de=MOI, texte=texte, envoye=time.time(), genre="button", choix=texte)


def test_le_bouton_d_un_modele_ne_lance_pas_de_tour(tmp_path):
    """Relecture du 16.11.2026 (I11) : toucher « Afficher » fait partir ce qui attendait, et c'est tout ; sans rien qui
    attende, le modèle répond comme à un message."""
    url = f"sqlite:///{tmp_path}/b.db"
    differes = stockage.Differes(url)
    differes.garder(MOI, [{"texte": "La demande de Marc attendait."}])
    agent, exp = Agent(), Exp()
    c = Conversations(conf(), agent, exp, contacts=Contacts(time.time() - 60), differes=differes, attente=0.01)
    asyncio.run(tourner(c, bouton()))
    assert agent.appels == [] and exp.journal == [("texte", MOI, "La demande de Marc attendait.")]
    asyncio.run(tourner(c, bouton(ident="b2")))
    assert agent.appels == ["Afficher"]


def test_l_annonce_survit_au_sommeil_du_conteneur(tmp_path):
    """Relecture du 16.11.2026 (I13) : l'annonce « un message vous attend » est gardée en base ; un conteneur réveillé ne
    la renvoie pas tant que la personne n'a pas répondu."""
    url = f"sqlite:///{tmp_path}/a.db"
    etats, differes = stockage.Etats(url), stockage.Differes(url)

    def conversations():
        exp = Exp()
        return Conversations(conf(modeles_meta={"message": {"nom": "attente_client"}}), Agent(), exp,
                             contacts=Contacts(time.time() - 30 * 3600), differes=differes, etats=etats), exp

    c1, exp1 = conversations()
    assert asyncio.run(c1.envoyer_de_soi_meme(MOI, [{"texte": "Demande 1"}], "demande")) == "modele"
    c2, exp2 = conversations()  # le conteneur s'est endormi, puis réveillé
    assert asyncio.run(c2.envoyer_de_soi_meme(MOI, [{"texte": "Demande 2"}], "demande")) == "modele"
    assert exp1.journal == [("modele", MOI, "attente_client")] and exp2.journal == []


def test_le_plafond_du_jour():
    """Relecture du 16.11.2026 (I7) : au-delà de son plafond du jour, un visiteur reçoit une phrase, une fois, et plus de
    tour de modèle ; un gestionnaire n'est jamais arrêté ; le journal le note une fois."""
    from noyau.garde import TROP_JOUR, Plafond

    p = Plafond(par_personne=2, client=3)
    for _ in range(2):
        assert p.libre("a", "visiteur") is None
        p.compter("a", "visiteur")
    assert p.libre("a", "visiteur") == "personne" and p.libre("b", "visiteur") is None
    p.compter("b", "visiteur")
    assert p.libre("c", "partenaire") == "client" and p.libre("g", "gestionnaire") is None
    assert p.libre("a", "visiteur", maintenant=time.time() + 86400) is None  # le lendemain

    journal = []

    class Journal:
        def noter(self, genre, quantite=1, detail="", quand=None):
            journal.append((genre, detail))

    agent, exp = Agent(), Exp()
    c = Conversations(conf(), agent, exp, contacts=Contacts(time.time()), journal=Journal(), attente=0.01)
    c.plafond = Plafond(par_personne=1, client=100)
    asyncio.run(tourner(c, entrant("Bonjour", "w1")))
    asyncio.run(tourner(c, entrant("Encore", "w2")))
    asyncio.run(tourner(c, entrant("Et encore", "w3")))
    assert agent.appels == ["Bonjour"]
    assert [e[2] for e in exp.journal if e[0] == "texte"].count(TROP_JOUR) == 1
    assert journal.count(("plafond", "personne")) == 1


def test_une_plaquette_piegee_est_refusee():
    """Relecture du 16.11.2026 (I6) : une image de PDF qui se décompresse en centaines de Mo est refusée sans remplir la
    mémoire."""
    import zlib

    from packs.immobilier import fiche as fiches

    bombe = zlib.compress(b"\0" * 60_000_000, 9)
    pdf = b"%PDF" + bombe
    with pytest.raises(ValueError, match="trop lourde"):
        fiches.octets_image(pdf, {"mode": "flate-jpeg", "debut": 4, "fin": 4 + len(bombe)})
    with pytest.raises(ValueError, match="trop lourde"):
        fiches.octets_image(pdf, {"mode": "flate", "debut": 4, "fin": 4 + len(bombe), "largeur": 100, "hauteur": 100, "predicteur": 1})
    petite = zlib.compress(b"\xff\xd8" + b"x" * 1000)
    assert fiches.octets_image(b"%PDF" + petite, {"mode": "flate-jpeg", "debut": 4, "fin": 4 + len(petite)}).startswith(b"\xff\xd8")
