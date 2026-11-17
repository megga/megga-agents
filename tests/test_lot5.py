"""Lot 5 : l'atelier (créer, valider, essayer, activer, historique, rôles)."""

import json
from dataclasses import dataclass, field

import base64

import httpx
import pytest
from agno.models.base import Model
from agno.models.response import ModelResponse
from fastapi.testclient import TestClient

from atelier import regles
from atelier.app import creer
from atelier.porte import Porte
from noyau import config as configuration
from noyau.config import Config

ADMIN = "admin-essai"
MEGGA = {"authorization": f"Bearer {ADMIN}"}


def cle_jetable() -> tuple[object, str]:
    """Une clé Ed25519 d'essai et sa forme sur une ligne (base64 de ses 32 octets), jamais gardée."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat

    cle = Ed25519PrivateKey.generate()
    return cle, base64.b64encode(cle.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())).decode()


# La clé de pilotage de l'atelier d'essai : elle signe les ordres des installations hors Cloudflare.
CLE_PILOTAGE, CLE_PILOTAGE_TEXTE = cle_jetable()


def conf_exemple(**autres) -> dict:
    d = configuration.lire("clients/exemple.yaml").model_dump(mode="json")
    d.update(autres)
    return d


@dataclass
class FauxModele(Model):
    """Un modèle Agno qui répond sans réseau, et note ce qu'on lui demande."""

    id: str = "faux"
    name: str = "Faux"
    provider: str = "essai"
    vus: list = field(default_factory=list)

    def _repondre(self, messages):
        self.vus.append([getattr(m, "content", None) for m in messages])
        return ModelResponse(role="assistant", content="Bonjour, ici votre agent d'essai.")

    def invoke(self, messages=None, **kw):
        return self._repondre(messages or [])

    async def ainvoke(self, messages=None, **kw):
        return self._repondre(messages or [])

    def invoke_stream(self, *a, **kw):
        yield self.invoke(*a, **kw)

    async def ainvoke_stream(self, *a, **kw):
        yield await self.ainvoke(*a, **kw)

    def _parse_provider_response(self, response, **kw):
        return response

    def _parse_provider_response_delta(self, response):
        return response


class FaussePorte:
    """Une porte qui note les mises en service, ou les refuse ; elle tient son propre annuaire."""

    def __init__(self, refus=None):
        self.activations = []
        self.refus = refus
        self.demandes_etats = []

    async def activer(self, conf, version):
        from atelier.porte import PorteErreur

        if self.refus:
            raise PorteErreur(*self.refus)
        self.activations.append((conf.id, version, conf.model_dump(mode="json")))
        return {"ok": True, "redemarre": True}

    async def etats(self, ident=None):
        self.demandes_etats.append(ident)
        annuaire = {c: {"id": c, "actif": 1, "version": v} for c, v, _ in self.activations}
        return {k: e for k, e in annuaire.items() if ident in (None, k)}


@pytest.fixture
def atelier(tmp_path):
    porte = FaussePorte()
    modele = FauxModele()
    app = creer({"ADMIN_TOKEN": ADMIN, "DATABASE_URL": f"sqlite:///{tmp_path}/atelier.db", "ESSAIS_DIR": str(tmp_path / "essais"),
                 "PILOTAGE_CLE": CLE_PILOTAGE_TEXTE}, porte=porte, principal_essai=modele)
    t = TestClient(app)
    t.porte, t.modele = porte, modele
    return t


def nouveau_client(t, **autres):
    r = t.post("/atelier/clients", headers=MEGGA, json={"config": conf_exemple(**autres)})
    assert r.status_code == 201, r.text
    return r.json()


def jeton_client(t, ident="exemple"):
    r = t.post(f"/atelier/clients/{ident}/jetons", headers=MEGGA)
    assert r.status_code == 201
    return {"authorization": f"Bearer {r.json()['jeton']}"}


# Le moteur : la configuration du client


def test_metier_et_outils():
    d = configuration.lire("clients/megga-estates.yaml").model_dump()
    assert d["metier"] == "immobilier"
    sans_metier = {k: v for k, v in d.items() if k != "metier"}
    assert configuration.lire(sans_metier).metier == "immobilier"  # les configurations d'avant le métier
    with pytest.raises(Exception):
        configuration.lire({**d, "metier": "general"})  # l'immobilier hors du métier immobilier


def test_regles_client():
    base = conf_exemple()
    c = regles.appliquer("client", base, {"nom_agent": "Lea", "ton": "direct", "voix": "EST9Ui6982FZPSi7gCHi"}, None)
    assert (c.nom_agent, c.ton, c.voix.voix) == ("Lea", "direct", "EST9Ui6982FZPSi7gCHi")
    assert c.modeles == Config.model_validate(base).modeles  # le reste est repris de la base
    for interdit in ({"modeles": {"principal": "claude-opus-5-5"}}, {"zone": "etats-unis"}, {"consignes": "x"}, {"catalogue": "demo:x"}):
        with pytest.raises(regles.Refus) as e:
            regles.appliquer("client", base, interdit, None)
        assert e.value.statut == 403
    with pytest.raises(regles.Refus) as e:
        regles.appliquer("client", base, {"nom_agent": "Lea \u2014 la meilleure"}, None)
    assert e.value.statut == 422 and e.value.details[0]["champ"] == "nom_agent"


def test_regles_megga_et_zone():
    base = conf_exemple()
    c = regles.appliquer("megga", base, {"modeles": {"principal": "claude-opus-5-5"}, "zone": "etats-unis"}, None)
    assert c.modeles.principal == "claude-opus-5-5" and c.modeles.secours == "deepseek-v4-pro"
    with pytest.raises(regles.Refus) as e:
        regles.appliquer("megga", base, {"zone": "etats-unis"}, "europe")
    assert e.value.statut == 409
    # une base d'une autre zone que celle en service, même sans toucher à la zone
    with pytest.raises(regles.Refus):
        regles.appliquer("megga", {**base, "zone": "suisse"}, {}, "europe")
    with pytest.raises(regles.Refus):
        regles.appliquer("megga", base, {"id": "autre"}, None)


def test_fusion_retire_un_modele_meta_ou_une_voix():
    base = configuration.lire("clients/megga-estates.yaml").model_dump(mode="json")
    base["modeles_meta"] = {"rappel": {"nom": "rappel_x", "langue": "fr"}, "relance": {"nom": "relance_y", "langue": "fr"}}
    base["voix"]["par_langue"] = {"en": "EST9Ui6982FZPSi7gCHi", "de": "EST9Ui6982FZPSi7gCHi"}
    c = regles.appliquer("megga", base, {"modeles_meta": {"rappel": {"nom": "rappel_x", "langue": "fr"}},
                                          "voix": {"par_langue": {"en": "EST9Ui6982FZPSi7gCHi"}}}, None)
    assert sorted(c.modeles_meta) == ["rappel"] and sorted(c.voix.par_langue) == ["en"]
    assert c.voix.voix == base["voix"]["voix"]  # le reste du sous-objet est gardé


def test_changer_de_metier_retire_les_outils():
    base = configuration.lire("clients/megga-estates.yaml").model_dump(mode="json")
    c = regles.appliquer("client", base, {"metier": "general"}, None)
    assert c.metier == "general" and c.outils == ()
    assert regles.manques(regles.appliquer("megga", base, {"catalogue": None}, None))


# L'API


def test_jetons_et_roles(atelier):
    t = atelier
    assert t.get("/atelier/clients").status_code == 401
    assert t.get("/atelier/clients", headers={"authorization": "Bearer faux"}).status_code == 401
    nouveau_client(t)
    nouveau_client(t, id="autre-client", whatsapp={"numero_id": "100000000000009"})
    client = jeton_client(t)
    ids = [c["id"] for c in t.get("/atelier/clients", headers=MEGGA).json()["clients"]]
    assert sorted(ids) == ["autre-client", "exemple"]
    assert [c["id"] for c in t.get("/atelier/clients", headers=client).json()["clients"]] == ["exemple"]
    assert t.get("/atelier/clients/autre-client", headers=client).status_code == 404  # ni lu ni deviné
    assert t.post("/atelier/clients", headers=client, json={"config": conf_exemple(id="pirate")}).status_code == 403
    assert t.post("/atelier/clients/exemple/jetons", headers=client).status_code == 403
    assert t.delete("/atelier/clients/exemple/jetons", headers=MEGGA).json()["retires"] == 1
    assert t.get("/atelier/clients", headers=client).status_code == 401


def test_creation_refusee(atelier):
    t = atelier
    r = t.post("/atelier/clients", headers=MEGGA, json={"config": conf_exemple(zone="lune")})
    assert r.status_code == 422 and r.json()["details"][0]["champ"] == "zone"
    nouveau_client(t)
    assert t.post("/atelier/clients", headers=MEGGA, json={"config": conf_exemple()}).status_code == 409


def test_le_parcours_du_client(atelier):
    """Créé par MEGGA, réglé, essayé puis activé par le client."""
    t = atelier
    v1 = nouveau_client(t)
    assert v1["version"] == 1 and v1["etat"] == "brouillon" and v1["auteur"] == "megga"
    client = jeton_client(t)

    # valider ne garde rien
    r = t.post("/atelier/clients/exemple/valider", headers=client, json={"changements": {"nom_agent": "Lea"}})
    assert r.status_code == 200 and r.json()["config"]["nom_agent"] == "Lea"
    assert len(t.get("/atelier/clients/exemple/versions", headers=client).json()["versions"]) == 1
    r = t.post("/atelier/clients/exemple/valider", headers=client, json={"changements": {"modeles": {"principal": "x"}}})
    assert r.status_code == 403

    v2 = t.post("/atelier/clients/exemple/versions", headers=client, json={"changements": {"nom_agent": "Lea", "ton": "direct"}}).json()
    assert (v2["version"], v2["base"], v2["auteur"]) == (2, 1, "client")

    # pas de mise en service sans essai
    r = t.post("/atelier/clients/exemple/versions/2/activer", headers=client)
    assert r.status_code == 409 and t.porte.activations == []

    r = t.post("/atelier/clients/exemple/versions/2/essai", headers=client, json={"message": "Bonjour"})
    assert r.status_code == 200 and r.json()["reponse"] == "Bonjour, ici votre agent d'essai."
    consignes = json.dumps(t.modele.vus[-1], ensure_ascii=False)
    assert "Tu es Lea" in consignes and "direct" in consignes  # l'agent de la version 2, pas celui de la 1
    assert t.get("/atelier/clients/exemple/versions/2", headers=client).json()["essais"] == 1

    r = t.post("/atelier/clients/exemple/versions/2/activer", headers=client)
    assert r.status_code == 200 and r.json()["version_en_service"] == 2 and r.json()["retour"] is False
    assert [(c, v) for c, v, _ in t.porte.activations] == [("exemple", 2)]
    assert t.porte.activations[0][2]["nom_agent"] == "Lea"
    d = t.get("/atelier/clients/exemple", headers=client).json()
    assert d["version_en_service"] == 2 and d["config"]["nom_agent"] == "Lea" and d["annuaire"]["version"] == 2
    assert t.post("/atelier/clients/exemple/versions/2/activer", headers=client).status_code == 409  # déjà en service


def test_historique_et_retour(atelier):
    t = atelier
    nouveau_client(t)
    t.post("/atelier/clients/exemple/versions/1/activer", headers=MEGGA, json={"forcer": True})
    t.post("/atelier/clients/exemple/versions", headers=MEGGA, json={"changements": {"nom_agent": "Lea"}})
    t.post("/atelier/clients/exemple/versions/2/essai", headers=MEGGA, json={"message": "Salut"})
    assert t.post("/atelier/clients/exemple/versions/2/activer", headers=MEGGA).status_code == 200
    # une version publiée est figée : un changement fait une version 3, partie de la 2
    v3 = t.post("/atelier/clients/exemple/versions", headers=MEGGA, json={"changements": {"ton": "sobre"}}).json()
    assert v3["version"] == 3 and v3["config"]["nom_agent"] == "Lea"
    # retour à la version 1, sans nouvel essai : elle a déjà servi
    r = t.post("/atelier/clients/exemple/versions/1/activer", headers=MEGGA)
    assert r.status_code == 200 and r.json()["retour"] is True
    assert [v for _, v, _ in t.porte.activations] == [1, 2, 1]
    assert t.porte.activations[-1][2]["nom_agent"] == "Alix"
    h = t.get("/atelier/clients/exemple/versions", headers=MEGGA).json()["versions"]
    assert [(v["version"], v["etat"]) for v in h] == [(3, "brouillon"), (2, "publiee"), (1, "publiee")]
    assert t.get("/atelier/clients/exemple", headers=MEGGA).json()["version_en_service"] == 1
    # une base au choix : repartir de la version 2
    v4 = t.post("/atelier/clients/exemple/versions", headers=MEGGA, json={"base": 2, "changements": {}}).json()
    assert v4["base"] == 2 and v4["config"]["nom_agent"] == "Lea"
    # la zone est figée après la mise en service
    r = t.post("/atelier/clients/exemple/versions", headers=MEGGA, json={"changements": {"zone": "etats-unis"}})
    assert r.status_code == 409


def test_reprise_en_main(atelier):
    t = atelier
    nouveau_client(t)
    client = jeton_client(t)
    t.post("/atelier/clients/exemple/versions", headers=client, json={"changements": {"nom_agent": "Zed"}})
    t.post("/atelier/clients/exemple/versions/2/essai", headers=client, json={"message": "Bonjour"})
    assert t.post("/atelier/clients/exemple/reprise", headers=client, json={}).status_code == 403
    assert t.post("/atelier/clients/exemple/reprise", headers=MEGGA, json={"gere_par_megga": True}).json()["gere_par_megga"]
    r = t.post("/atelier/clients/exemple/versions/2/activer", headers=client)
    assert r.status_code == 403 and t.porte.activations == []
    # MEGGA reprend le brouillon du client, le corrige et le met en service
    v3 = t.post("/atelier/clients/exemple/versions", headers=MEGGA, json={"base": 2, "changements": {"nom_agent": "Lea", "consignes": "Sois bref."}}).json()
    assert v3["auteur"] == "megga"
    assert t.post("/atelier/clients/exemple/versions/3/activer", headers=MEGGA, json={"forcer": True}).status_code == 200
    # la reprise survit à la mise en service
    assert t.get("/atelier/clients/exemple", headers=client).json()["gere_par_megga"] is True
    assert t.post("/atelier/clients/exemple/versions/2/activer", headers=client, json={"forcer": True}).status_code == 403
    t.post("/atelier/clients/exemple/reprise", headers=MEGGA, json={"gere_par_megga": False})
    assert t.get("/atelier/clients/exemple", headers=client).json()["gere_par_megga"] is False


def test_activation_refusee_par_la_porte(tmp_path):
    porte = FaussePorte(refus=(409, "numéro déjà pris"))
    t = TestClient(creer({"ADMIN_TOKEN": ADMIN, "DATABASE_URL": f"sqlite:///{tmp_path}/a.db"}, porte=porte))
    nouveau_client(t)
    r = t.post("/atelier/clients/exemple/versions/1/activer", headers=MEGGA, json={"forcer": True})
    assert r.status_code == 502 and r.json()["details"]["statut"] == 409
    # rien n'a changé : la version reste un brouillon, aucune n'est en service
    assert t.get("/atelier/clients/exemple", headers=MEGGA).json()["version_en_service"] is None
    assert t.get("/atelier/clients/exemple/versions/1", headers=MEGGA).json()["etat"] == "brouillon"


def test_activation_garde_la_zone(atelier):
    """Un brouillon ou une ancienne version d'une autre zone ne se met pas en service."""
    t = atelier
    nouveau_client(t)  # v1 en Europe
    t.post("/atelier/clients/exemple/versions", headers=MEGGA, json={"changements": {"zone": "suisse"}})  # v2, avant toute mise en service
    assert t.post("/atelier/clients/exemple/versions/1/activer", headers=MEGGA, json={"forcer": True}).status_code == 200
    r = t.post("/atelier/clients/exemple/versions/2/activer", headers=MEGGA, json={"forcer": True})
    assert r.status_code == 409 and "zone" in r.json()["erreur"]
    assert [v for _, v, _ in t.porte.activations] == [1]
    # partir de la v2 ne contourne pas la règle
    assert t.post("/atelier/clients/exemple/versions", headers=MEGGA, json={"base": 2, "changements": {}}).status_code == 409


def test_echec_apres_la_porte_remet_l_annuaire(atelier, monkeypatch):
    t = atelier
    nouveau_client(t)
    t.post("/atelier/clients/exemple/versions/1/activer", headers=MEGGA, json={"forcer": True})
    t.post("/atelier/clients/exemple/versions", headers=MEGGA, json={"changements": {"nom_agent": "Lea"}})

    def panne(*a, **k):
        raise RuntimeError("base perdue")

    monkeypatch.setattr(t.app.state.versions, "mettre_en_service", panne)
    r = t.post("/atelier/clients/exemple/versions/2/activer", headers=MEGGA, json={"forcer": True})
    assert r.status_code == 500 and r.json()["details"] == {"annuaire_retabli": True}
    # la porte a reçu la v2, puis de nouveau la v1 : elle sert ce que l'atelier dit en service
    assert [v for _, v, _ in t.porte.activations] == [1, 2, 1]
    assert t.get("/atelier/clients/exemple", headers=MEGGA).json()["version_en_service"] == 1


def test_porte_muette_et_ecart(tmp_path):
    porte = FaussePorte(refus=(0, "sans réponse (ReadTimeout)"))
    t = TestClient(creer({"ADMIN_TOKEN": ADMIN, "DATABASE_URL": f"sqlite:///{tmp_path}/a.db"}, porte=porte))
    nouveau_client(t)
    r = t.post("/atelier/clients/exemple/versions/1/activer", headers=MEGGA, json={"forcer": True})
    assert r.status_code == 504
    # la porte a peut-être agi : la liste montre l'écart entre l'annuaire et l'atelier
    porte.refus = None
    porte.activations.append(("exemple", 1, {}))
    c = t.get("/atelier/clients", headers=MEGGA).json()["clients"][0]
    assert c["version_en_service"] is None and c["annuaire"]["version"] == 1 and c["ecart"] is True
    porte.demandes_etats.clear()
    assert t.get("/atelier/clients/exemple", headers=MEGGA).json()["ecart"] is True
    assert porte.demandes_etats == ["exemple"]  # un seul client demandé à la porte


def test_entrees_mal_formees(atelier):
    t = atelier
    nouveau_client(t)
    for corps in ({"forcer": "false"}, {"forcer": 1}):
        assert t.post("/atelier/clients/exemple/versions/1/activer", headers=MEGGA, json=corps).status_code == 400
    assert t.post("/atelier/clients/exemple/reprise", headers=MEGGA, json={"gere_par_megga": "false"}).status_code == 400
    for base in ("deux", 0, True):
        assert t.post("/atelier/clients/exemple/versions", headers=MEGGA, json={"base": base, "changements": {}}).status_code == 400
    assert t.post("/atelier/clients/exemple/versions", headers=MEGGA, json={"changements": []}).status_code == 400
    # une version qui ne passe plus la validation : un refus lisible, pas une erreur 500
    t.app.state.versions.db.upsert_config("exemple", config={**conf_exemple(), "inconnu": 1}, stage="draft")
    for route in ("essai", "activer"):
        r = t.post(f"/atelier/clients/exemple/versions/2/{route}", headers=MEGGA, json={"message": "x", "forcer": True})
        assert r.status_code == 422 and r.json()["details"][0]["champ"] == "inconnu"


def test_la_liste_suit_la_version_en_service(atelier):
    t = atelier
    nouveau_client(t)
    t.post("/atelier/clients/exemple/versions", headers=MEGGA, json={"changements": {"nom_agent": "Lea", "entreprise": "Autre SA"}})
    t.post("/atelier/clients/exemple/versions/2/activer", headers=MEGGA, json={"forcer": True})
    c = t.get("/atelier/clients", headers=MEGGA).json()["clients"][0]
    assert (c["nom_agent"], c["entreprise"], c["derniere_version"], c["ecart"]) == ("Lea", "Autre SA", 2, False)


def test_essais_sans_memoire_partagee(atelier, tmp_path):
    import sqlite3

    t = atelier
    nouveau_client(t)
    t.post("/atelier/clients/exemple/versions", headers=MEGGA, json={"changements": {"ton": "direct"}})
    for v, conv in ((1, "a"), (2, "a"), (2, "b")):
        t.post(f"/atelier/clients/exemple/versions/{v}/essai", headers=MEGGA, json={"message": "Je m'appelle Paul", "conversation": conv})
    with sqlite3.connect(tmp_path / "essais" / "exemple.db") as c:
        personnes = {u for (u,) in c.execute("SELECT DISTINCT user_id FROM agno_sessions")}
    assert personnes == {"essai-v1-a", "essai-v2-a", "essai-v2-b"}


def test_zone_hors_porte_et_version_incomplete(atelier):
    t = atelier
    nouveau_client(t, zone="suisse")
    r = t.post("/atelier/clients/exemple/versions/1/activer", headers=MEGGA, json={"forcer": True})
    assert r.status_code == 200 and r.json()["annuaire"] == {"zone": "suisse", "porte": False}
    assert r.json()["pilotage"] == {"ordre": 1, "installation": False}  # un ordre signé attend l'installation
    assert t.porte.activations == []
    t.post("/atelier/clients/exemple/versions", headers=MEGGA, json={"changements": {"metier": "immobilier", "outils": ["immobilier"]}})
    v = t.get("/atelier/clients/exemple/versions/2", headers=MEGGA).json()
    assert v["config"]["catalogue"] is None
    assert t.post("/atelier/clients/exemple/versions/2/essai", headers=MEGGA, json={"message": "x"}).status_code == 409
    assert t.post("/atelier/clients/exemple/versions/2/activer", headers=MEGGA, json={"forcer": True}).status_code == 409


def test_essai_hors_whatsapp_et_a_part(atelier, tmp_path):
    t = atelier
    nouveau_client(t, outils=["immobilier"], metier="immobilier", catalogue="demo:megga-estates")
    for mauvais in ({}, {"message": ""}, {"message": "x" * 5000}, {"message": "ok", "conversation": "../x"}):
        assert t.post("/atelier/clients/exemple/versions/1/essai", headers=MEGGA, json=mauvais).status_code == 400
    r = t.post("/atelier/clients/exemple/versions/1/essai", headers=MEGGA, json={"message": "Un bien à Genève ?", "conversation": "a"})
    assert r.status_code == 200
    # la base d'essai est à part, dans le dossier des essais
    assert (tmp_path / "essais" / "exemple.db").exists()
    assert t.post("/atelier/clients/exemple/versions/9/essai", headers=MEGGA, json={"message": "x"}).status_code == 404


def test_catalogue(atelier):
    nouveau_client(atelier)
    c = atelier.get("/atelier/catalogue", headers=jeton_client(atelier)).json()
    # la base de connaissances (lot 9.2), les leads et les connecteurs (lot 9.4) vont avec tous les métiers
    assert c["metiers"] == {"general": ["connaissances", "leads", "connecteurs"],
                            "immobilier": ["immobilier", "connaissances", "leads", "connecteurs"]}
    assert "nom_agent" in c["champs_client"]


# Le lien avec la porte


def test_porte_http():
    vus = []

    def repondre(r: httpx.Request):
        vus.append((r.method, r.url.path, r.headers["authorization"], r.content))
        if r.method == "PUT":
            return httpx.Response(200, json={"ok": True, "redemarre": True})
        return httpx.Response(200, json={"clients": [{"id": "exemple", "actif": 1, "version": 2}]})

    import asyncio

    p = Porte("https://porte.essai", "jeton", transport=httpx.MockTransport(repondre))
    conf = Config.model_validate(conf_exemple())
    assert asyncio.run(p.activer(conf, 2)) == {"ok": True, "redemarre": True}
    assert asyncio.run(p.etats())["exemple"]["version"] == 2
    methode, chemin, auth, corps = vus[0]
    assert (methode, chemin, auth) == ("PUT", "/admin/clients/exemple/config", "Bearer jeton")
    assert json.loads(corps)["version"] == 2 and json.loads(corps)["config"]["id"] == "exemple"
    with pytest.raises(ValueError):
        Porte("http://non-chiffre", "jeton")

    def muette(r: httpx.Request):
        raise httpx.ReadTimeout("trop long", request=r)

    from atelier.porte import PorteErreur

    with pytest.raises(PorteErreur) as e:
        asyncio.run(Porte("https://porte.essai", "jeton", transport=httpx.MockTransport(muette)).activer(conf, 2))
    assert e.value.statut == 0
    asyncio.run(p.etats("exemple"))
    assert vus[-1][1] == "/admin/clients" and vus[-1][0] == "GET"


def test_l_image_choisit_son_service(monkeypatch):
    import runpy
    import sys

    appele = []
    monkeypatch.setattr("atelier.app.principal", lambda: appele.append("atelier"))
    monkeypatch.setattr("noyau.app.principal", lambda: appele.append("agent"))
    for service, attendu in (("atelier", "atelier"), ("", "agent")):
        monkeypatch.setenv("MEGGA_SERVICE", service)
        sys.modules.pop("noyau.__main__", None)
        runpy.run_module("noyau", run_name="__main__")
        assert appele[-1] == attendu


@pytest.mark.parametrize("moteur", ["sqlite"] + (["postgres"] if __import__("os").environ.get("TEST_POSTGRES_URL") else []))
def test_versions_sur_les_deux_bases(moteur, tmp_path):
    """L'historique tient sur SQLite comme sur Postgres (la base de l'atelier est un Postgres)."""
    import os
    import uuid

    from atelier.versions import Versions
    from noyau import stockage

    url = f"sqlite:///{tmp_path}/v.db" if moteur == "sqlite" else os.environ["TEST_POSTGRES_URL"]
    v = Versions(stockage.base_agno(url))
    ident = f"essai-{uuid.uuid4().hex[:8]}"  # base partagée sous Postgres
    conf = Config.model_validate(conf_exemple(id=ident))
    v.creer(conf, "megga")
    try:
        v.ajouter(Config.model_validate(conf_exemple(id=ident, nom_agent="Lea")), "client", 1)
        v.regler(ident, gere_par_megga=True)
        v.mettre_en_service(ident, 2, None)
        assert v.courante(ident) == 2 and v.reglages(ident)["gere_par_megga"] is True
        assert v.client(ident)["name"] == "Lea"  # la ligne suit la version en service
        v.ajouter(conf, "megga", 2)
        v.mettre_en_service(ident, 3, 2)
        v.mettre_en_service(ident, 2, 3)  # retour
        assert v.courante(ident) == 2 and v.client(ident)["name"] == "Lea"
        with pytest.raises(Exception):
            v.mettre_en_service(ident, 3, 1)  # la garde : on ne croyait pas la bonne version en service
        assert v.courante(ident) == 2
        assert [x["etat"] for x in v.historique(ident)] == ["publiee", "publiee", "brouillon"]
        assert ident in [c["component_id"] for c in v.clients()]
        assert v.dernieres({ident}) == {ident: 3}
        j = stockage.Jetons(url)
        jeton = j.creer(ident)
        assert j.client(jeton) == ident and j.client("faux") is None and j.revoquer(ident) == 1
    finally:
        # Base partagée : on n'y laisse rien, même en cas d'échec. Sous Postgres, Agno 3.2 donne aux
        # versions une colonne deleted_at que SQLite n'a pas ; une ligne restante casserait l'export
        # vers SQLite (test_noyau).
        v.db.delete_component(ident, hard_delete=True)


def test_le_conteneur_finit_ses_tours_avant_de_redemarrer():
    """/interne/vider attend la réponse en cours (la porte n'arrête le conteneur qu'ensuite)."""
    import asyncio

    from noyau.app import creer as creer_agent
    from test_app import CONF, FauxExpediteur, corps, signe

    class Lent:
        def __init__(self):
            self.appels = []

        async def arun(self, texte, user_id=None, session_id=None):
            await asyncio.sleep(0.3)
            self.appels.append(texte)
            return type("S", (), {"content": "Voilà.", "status": "COMPLETED"})()

    exp = FauxExpediteur()
    app = creer_agent({"CLIENT_CONFIG": CONF, "META_APP_SECRET": "secret-essai", "INTERNE_TOKEN": "jeton"},
                      agent=Lent(), expediteur=exp, attente=0.01, seuil_regard=30)
    with TestClient(app) as t:
        assert t.post("/interne/vider", headers={"x-megga-interne": "faux"}).status_code == 401
        c = corps()
        t.post("/whatsapp", content=c, headers=signe(c))
        assert exp.envois == []  # le tour est en route
        assert t.post("/interne/vider", headers={"x-megga-interne": "jeton"}).json() == {"restantes": 0}
        assert [texte for _, texte in exp.envois] == ["Voilà."]
