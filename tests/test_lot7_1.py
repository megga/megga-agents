"""Lot 7.1 : les fondations d'Alix FSP sur le socle. Les rôles des personnes, les médias de WhatsApp, la gestion du site."""

import asyncio
import hashlib
import hmac
import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from noyau import api, config as configuration, stockage
from noyau.app import creer
from noyau.roles import Personnes, lire_gestionnaires
from noyau.whatsapp import Expediteur, Media, decrire_media, lire_entrants
from packs.immobilier.gestion import Gestion, GestionErreur
from test_app import FauxAgent, FauxExpediteur, attendre

SECRET = "secret-essai"
FSP = configuration.lire("clients/four-seasons-properties.yaml").model_dump(mode="json")
NUMERO_ID = "100000000000042"
FSP_WA = {**FSP, "whatsapp": {"numero_id": NUMERO_ID}}
GREG = "+41790000001"
GESTIONNAIRES = json.dumps({GREG: "greg@agence.ch"})


def webhook(messages: list[dict], contacts: list[dict] | None = None) -> bytes:
    return json.dumps({"object": "whatsapp_business_account", "entry": [{"changes": [{"field": "messages", "value": {
        "metadata": {"phone_number_id": NUMERO_ID}, "contacts": contacts or [], "messages": messages}}]}]}).encode()


def texte(de: str, corps: str, ident: str) -> dict:
    return {"from": de.lstrip("+"), "id": ident, "type": "text", "timestamp": str(int(time.time())), "text": {"body": corps}}


def signe(c: bytes) -> dict:
    return {"x-hub-signature-256": "sha256=" + hmac.new(SECRET.encode(), c, hashlib.sha256).hexdigest(), "content-type": "application/json"}


class AgentNomme(FauxAgent):
    def __init__(self, nom):
        super().__init__(f"réponse de {nom}")
        self.nom = nom
        self.images = []

    async def arun(self, texte, user_id=None, session_id=None, images=None):
        self.images.append(images)
        return await super().arun(texte, user_id, session_id)


class ExpediteurMedias(FauxExpediteur):
    def __init__(self):
        super().__init__()
        self.telecharges = []

    async def telecharger(self, media_id, maximum=0):
        self.telecharges.append(media_id)
        return b"\xff\xd8photo"


def agent_fsp(tmp_path, conf=None, gestionnaires=GESTIONNAIRES):
    url = f"sqlite:///{tmp_path}/fsp.db"
    agents = {n: AgentNomme(n) for n in ("gestionnaire", "partenaire", "visiteur")}
    exp = ExpediteurMedias()
    env = {"CLIENT_CONFIG": json.dumps(conf or FSP_WA), "DATABASE_URL": url, "META_APP_SECRET": SECRET, "INTERNE_TOKEN": "interne"}
    if gestionnaires:
        env["GESTIONNAIRES"] = gestionnaires
    app = creer(env, agent=AgentNomme("public"), agents=agents, expediteur=exp, attente=0.01)
    return TestClient(app), agents, exp, app, url


# La configuration


def test_la_configuration_de_four_seasons():
    conf = configuration.lire("clients/four-seasons-properties.yaml")
    assert list(conf.les_roles()) == ["gestionnaire", "partenaire", "visiteur"]
    assert conf.whatsapp.numero_id == "1391058037432148" and conf.gestion.url == "https://fourseasonsproperties.ch"
    assert configuration.manques(conf) == []
    # Rien de secret : ni numéro de gestionnaire, ni clé
    texte_brut = open("clients/four-seasons-properties.yaml", encoding="utf-8").read()
    assert "+41" not in texte_brut and "@" not in texte_brut


def test_les_roles_respectent_le_metier_et_le_catalogue():
    base = configuration.lire("clients/exemple.yaml").model_dump(mode="json")
    with pytest.raises(Exception, match="ne vont pas avec ce métier"):
        configuration.Config.model_validate({**base, "roles": {"visiteur": {"outils": ["immobilier"]}}})
    conf = configuration.Config.model_validate({**base, "metier": "immobilier", "roles": {"visiteur": {"outils": ["immobilier"]}}})
    assert configuration.manques(conf) == ["le pack immobilier attend son catalogue (réglage de MEGGA)"]
    with pytest.raises(Exception):
        configuration.Config.model_validate({**base, "roles": {"visiteur": {"consignes": "Bonjour \u2014 bienvenue"}}})
    with pytest.raises(Exception):
        configuration.Config.model_validate({**base, "gestion": {"url": "http://non-https.ch"}})


def test_les_gestionnaires_viennent_d_un_secret():
    assert lire_gestionnaires(json.dumps({"+41 79 000 00 01": " greg@agence.ch "})) == {GREG: "greg@agence.ch"}
    assert lire_gestionnaires("") == {}
    for mauvais in ("pas du json", "[]", json.dumps({"12": "x"}), json.dumps({GREG: ""})):
        with pytest.raises(ValueError, match="GESTIONNAIRES"):
            lire_gestionnaires(mauvais)


def test_un_secret_illisible_arrete_l_agent(tmp_path):
    with pytest.raises(RuntimeError, match="GESTIONNAIRES"):
        agent_fsp(tmp_path, gestionnaires="pas du json")


# Les rôles


def test_le_role_de_chaque_personne(tmp_path):
    url = f"sqlite:///{tmp_path}/r.db"
    bloques, partenaires = stockage.Bloques(url), stockage.Partenaires(url)
    p = Personnes(configuration.lire(FSP_WA), lire_gestionnaires(GESTIONNAIRES), bloques, partenaires)
    assert p.role(GREG) == "gestionnaire" and p.compte(GREG) == "greg@agence.ch"
    assert p.role("+41790000002") == "visiteur" and p.compte("+41790000002") is None
    assert partenaires.inscrire("+41790000003", "Agence du Lac", par=GREG) and not partenaires.inscrire("+41790000003")
    assert p.role("+41790000003") == "partenaire"
    assert bloques.bloquer("+41790000002", par=GREG) and p.role("+41790000002") == "bloque"
    assert bloques.debloquer("+41790000002") and p.role("+41790000002") == "visiteur"
    assert p.role(api.personne_interne("site", "visiteur-1")) == "visiteur"
    # Sans rôles : tout le monde parle au même agent, sauf un numéro bloqué
    sans = Personnes(configuration.lire("clients/exemple.yaml"), {}, bloques)
    bloques.bloquer("+41790000009")
    assert sans.role("+41790000002") == "public" and sans.role("+41790000009") == "bloque"


def test_sans_visiteurs_un_refus_une_fois_par_jour():
    conf = configuration.Config.model_validate({**FSP_WA, "roles": {"gestionnaire": {}, "refus": "Ce numéro est réservé à l'agence."}})
    p = Personnes(conf, lire_gestionnaires(GESTIONNAIRES))
    assert p.role("+41790000002") is None
    assert p.refuser("+41790000002", 0) == "Ce numéro est réservé à l'agence."
    assert p.refuser("+41790000002", 3600) is None
    assert p.refuser("+41790000002", 90000) is not None


def test_chacun_parle_a_l_agent_de_son_role(tmp_path):
    _, agents, exp, app, url = agent_fsp(tmp_path)
    stockage.Partenaires(url).inscrire("+41790000003", "Agence du Lac")
    stockage.Bloques(url).bloquer("+41790000004")
    c = webhook([texte(GREG, "mes annonces", "w1"), texte("+41790000002", "je cherche une villa à Genève", "w2"),
                 texte("+41790000003", "un client cherche", "w3"), texte("+41790000004", "spam", "w4")])
    with TestClient(app) as t:
        assert t.post("/whatsapp", content=c, headers=signe(c)).text == "reçu 3"
        t.portal.call(attendre(app))
    assert [a.appels[0][1] for a in (agents["gestionnaire"], agents["visiteur"], agents["partenaire"])] == [GREG, "+41790000002", "+41790000003"]
    assert all(len(a.appels) == 1 for a in agents.values())
    # Le numéro bloqué n'est ni lu ni répondu
    assert "+41790000004" not in [v for v, _ in exp.envois] and ("lu", "w4") not in exp.autres
    # Le visiteur reçoit d'abord l'accueil de Greg (lot 7.4), puis la réponse
    assert sorted(v for v, _ in exp.envois) == sorted([GREG, "+41790000002", "+41790000002", "+41790000003"])
    assert [t for v, t in exp.envois if v == "+41790000002"][0].startswith("Bonjour, je suis Alix, l'assistante de Greg.")


def test_sans_visiteurs_l_inconnu_recoit_le_refus(tmp_path):
    conf = {**FSP_WA, "roles": {"gestionnaire": {}, "refus": "Ce numéro est réservé à l'agence."}}
    _, agents, exp, app, _ = agent_fsp(tmp_path, conf)
    with TestClient(app) as t:
        for i in range(2):
            c = webhook([texte("+41790000002", "bonjour", f"x{i}")])
            assert t.post("/whatsapp", content=c, headers=signe(c)).text == "reçu 0"
        t.portal.call(attendre(app))
    assert exp.envois == [("+41790000002", "Ce numéro est réservé à l'agence.")]
    assert not any(a.appels for a in agents.values())


def test_par_api_un_visiteur(tmp_path):
    t, agents, _, _, url = agent_fsp(tmp_path)
    ident, cle, empreinte = api.nouvelle_cle()
    stockage.ClesApi(url).ajouter(ident, "site", empreinte, 30)
    r = t.post("/api/messages", headers={"authorization": f"Bearer {cle}"}, json={"personne": "p1", "texte": "je cherche une villa"})
    accueil, reponse = r.json()["reponse"].rsplit("\n\n", 1)
    assert accueil.startswith("Bonjour, je suis Alix") and reponse == "réponse de visiteur"
    # Des rôles sans visiteurs : l'entrée par API est fermée
    (tmp_path / "b").mkdir()
    t2, *_ = agent_fsp(tmp_path / "b", {**FSP_WA, "roles": {"gestionnaire": {}}})
    stockage.ClesApi(f"sqlite:///{tmp_path}/b/fsp.db").ajouter(ident, "site", empreinte, 30)
    r = t2.post("/api/messages", headers={"authorization": f"Bearer {cle}"}, json={"personne": "p1", "texte": "bonjour"})
    assert r.status_code == 403


# Les médias


def test_les_medias_recus_sont_lus():
    c = json.loads(webhook([
        {"from": "41790000001", "id": "m1", "type": "image", "timestamp": "1", "image": {"id": "IMG1", "mime_type": "image/jpeg", "caption": "la vue"}},
        {"from": "41790000001", "id": "m2", "type": "document", "timestamp": "1", "document": {"id": "DOC1", "mime_type": "application/pdf", "filename": "plaquette.pdf"}},
        {"from": "41790000001", "id": "m3", "type": "document", "timestamp": "1", "document": {"id": "VID1", "mime_type": "video/mp4", "filename": "visite.mp4"}},
        {"from": "41790000001", "id": "m4", "type": "video", "timestamp": "1", "video": {"id": "VID2", "mime_type": "video/mp4", "caption": "le jardin"}},
        {"from": "41790000001", "id": "m5", "type": "interactive", "timestamp": "1", "interactive": {"type": "list_reply", "list_reply": {"id": "bien-12", "title": "Villa"}}},
        {"from": "41790000001", "id": "m6", "type": "interactive", "timestamp": "1", "interactive": {"type": "nfm_reply", "nfm_reply": {"response_json": "{\"commune\": \"Cologny\"}"}}},
    ], [{"wa_id": "41790000001", "profile": {"name": "Greg  M."}}]))
    m = lire_entrants(c, NUMERO_ID)
    assert [(x.media.genre, x.media.id) if x.media else None for x in m] == [("image", "IMG1"), ("document", "DOC1"), ("video", "VID1"), ("video", "VID2"), None, None]
    assert m[0].texte == "la vue" and m[3].texte == "le jardin" and m[0].profil == "Greg M."
    assert not m[2].media.compressee and m[3].media.compressee
    assert m[4].choix == "bien-12" and m[4].texte == "Villa" and m[5].formulaire == "{\"commune\": \"Cologny\"}"
    assert decrire_media(m[1].media, 2) == "[PDF reçu : média 2, « plaquette.pdf »]"
    assert decrire_media(m[2].media, 3) == "[Vidéo reçue : média 3, qualité d'origine, « visite.mp4 »]"
    assert decrire_media(Media(id="x", genre="image"), 1) == "[Photo reçue : média 1]"


def test_une_photo_est_vue_par_le_modele_et_numerotee(tmp_path):
    _, agents, exp, app, url = agent_fsp(tmp_path)
    c = webhook([
        {"from": GREG.lstrip("+"), "id": "p1", "type": "image", "timestamp": str(int(time.time())), "image": {"id": "IMG1", "mime_type": "image/jpeg", "caption": "la terrasse"}},
        {"from": GREG.lstrip("+"), "id": "p2", "type": "document", "timestamp": str(int(time.time())), "document": {"id": "DOC1", "mime_type": "application/pdf", "filename": "plaquette.pdf"}},
    ])
    t = TestClient(app).__enter__()
    t.post("/whatsapp", content=c, headers=signe(c))
    t.portal.call(attendre(app))
    g = agents["gestionnaire"]
    assert g.appels[0][0] == "[Photo reçue : média 1]\nla terrasse\n[PDF reçu : média 2, « plaquette.pdf »]"
    (vues,) = g.images
    assert len(vues) == 1 and vues[0].content == b"\xff\xd8photo" and exp.telecharges == ["IMG1"]
    assert stockage.Medias(url).lire(GREG, 2)["media_id"] == "DOC1"
    # La numérotation continue au tour suivant
    c = webhook([{"from": GREG.lstrip("+"), "id": "p3", "type": "image", "timestamp": str(int(time.time())), "image": {"id": "IMG2", "mime_type": "image/jpeg"}}])
    t.post("/whatsapp", content=c, headers=signe(c))
    t.portal.call(attendre(app))
    t.__exit__(None, None, None)
    assert g.appels[1][0] == "[Photo reçue : média 3]"
    assert [m["media_id"] for m in stockage.Medias(url).derniers(GREG)] == ["IMG1", "DOC1", "IMG2"]


def test_l_expediteur_envoie_les_medias():
    envois = []

    def repondre(r: httpx.Request):
        if r.url.path.endswith("/media"):
            return httpx.Response(200, json={"id": "M1"})
        envois.append(json.loads(r.content))
        return httpx.Response(200, json={"messages": [{"id": "x"}]})

    exp = Expediteur("jeton", NUMERO_ID, "v26.0", httpx.AsyncClient(transport=httpx.MockTransport(repondre)))

    async def tout():
        assert await exp.televerser(b"%PDF", "application/pdf", "fiche.pdf") == "M1"
        await exp.document(GREG, "fiche.pdf", media_id="M1", legende="La fiche")
        await exp.image(GREG, lien="https://exemple.ch/a.jpg")
        await exp.video(GREG, lien="https://exemple.ch/v.mp4", legende="La visite")
        await exp.liste(GREG, "Quel bien ?", "Choisir", "Biens", [{"id": "b1", "titre": "Villa de Cologny", "description": "4 chambres"}])
        await exp.boutons(GREG, "On publie ?", [{"id": "oui", "titre": "Oui"}, {"id": "non", "titre": "Non"}])
        await exp.carrousel(GREG, "Vos biens", [{"image": "https://exemple.ch/a.jpg", "texte": "Villa", "bouton": "Voir", "url": "https://exemple.ch/v"}] * 2)
        await exp.formulaire(GREG, "123", "Nouvelle annonce", "Remplir", "jeton-1", "ACCUEIL")
        with pytest.raises(ValueError):
            await exp.image(GREG)

    asyncio.run(tout())
    assert [e["type"] for e in envois] == ["document", "image", "video", "interactive", "interactive", "interactive", "interactive"]
    assert envois[0]["document"] == {"id": "M1", "caption": "La fiche", "filename": "fiche.pdf"}
    assert envois[3]["interactive"]["action"]["sections"][0]["rows"][0] == {"id": "b1", "title": "Villa de Cologny", "description": "4 chambres"}
    assert [b["reply"]["id"] for b in envois[4]["interactive"]["action"]["buttons"]] == ["oui", "non"]
    assert len(envois[5]["interactive"]["action"]["cards"]) == 2
    assert envois[6]["interactive"]["action"]["parameters"]["flow_id"] == "123"


# La gestion du site


def test_la_gestion_au_nom_d_un_gestionnaire():
    vus = []

    def repondre(r: httpx.Request):
        vus.append((r.method, r.url.path, r.headers.get("authorization"), r.headers.get("x-gestion-compte")))
        if r.url.path.endswith("/vitrine"):
            return httpx.Response(403, json={"erreur": "compte inconnu"})
        return httpx.Response(200, json={"annonces": [{"slug": "cologny-villa"}]})

    conf = configuration.lire("clients/four-seasons-properties.yaml")
    g = Gestion(conf.gestion, "cle-gestion", transport=httpx.MockTransport(repondre))

    async def tout():
        assert await g.appel("greg@agence.ch", "GET", "/annonces") == {"annonces": [{"slug": "cologny-villa"}]}
        with pytest.raises(GestionErreur, match="compte inconnu") as e:
            await g.appel("greg@agence.ch", "GET", "/vitrine")
        assert e.value.statut == 403
        with pytest.raises(GestionErreur):
            await g.appel("", "GET", "/annonces")
        with pytest.raises(GestionErreur):
            await g.appel("greg@agence.ch", "GET", "/../admin")
        # Un identifiant venu du modèle ne coupe, ne détourne ni ne prolonge le chemin (relecture du 16.11.2026, C2).
        for slug in ("cologny-villa#", "x?x=", "%2e%2e/%2e%2e/annonces/x", "x/visibilite", "x/acces#", "Villa", "x\n"):
            with pytest.raises(GestionErreur, match="chemin"):
                await g.appel("greg@agence.ch", "DELETE", f"/annonces/{slug}/videos", corps={"numero": 1})
        with pytest.raises(GestionErreur, match="chemin"):
            await g.appel("greg@agence.ch", "GET", "/clients/recherches/r1%2F..")
        with pytest.raises(GestionErreur, match="chemin"):
            await g.octets("greg@agence.ch", "/gestion/images/a.jpg?x=1")
        await g.appel("greg@agence.ch", "DELETE", "/annonces/cologny-villa/videos", corps={"numero": 1})
        await g.appel("greg@agence.ch", "GET", "/clients/recherches/r1-ab/biens")

    asyncio.run(tout())
    assert vus[0] == ("GET", "/api/gestion/annonces", "Bearer cle-gestion", "greg@agence.ch")
    assert g.site_du_bien("marbella-villa-olie") == "https://fspmarbella.com"
    assert g.site_du_bien("cologny-villa") == "https://fourseasonsproperties.ch"
    with pytest.raises(ValueError):
        Gestion(conf.gestion, "")


def test_l_agent_branche_la_gestion_si_sa_cle_est_la(tmp_path):
    t, _, _, app, _ = agent_fsp(tmp_path)
    assert app.state.gestion is None  # pas de GESTION_CLE
    env = {"CLIENT_CONFIG": json.dumps(FSP_WA), "DATABASE_URL": f"sqlite:///{tmp_path}/g.db", "GESTION_CLE": "cle", "GESTIONNAIRES": GESTIONNAIRES}
    app = creer(env, agent=AgentNomme("public"), agents={n: AgentNomme(n) for n in ("gestionnaire", "partenaire", "visiteur")},
                expediteur=FauxExpediteur())
    assert isinstance(app.state.gestion, Gestion)
    assert app.state.personnes.compte(GREG) == "greg@agence.ch"
