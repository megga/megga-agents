"""Lot 6.2 : l'installation chez le client (licence, webhook direct, secrets en fichiers, rappels sans porte)."""

import asyncio
import datetime as dt
import json
import time

import pytest
import yaml
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from noyau import licence
from noyau.app import creer
from noyau.environnement import charger
from test_app import CONF, FauxAgent, FauxExpediteur

CLE = Ed25519PrivateKey.generate()
AUTRE_CLE = Ed25519PrivateKey.generate()


def jeton(client="exemple", jours=30, cle=CLE):
    return licence.emettre({"client": client, "jusqu_au": (dt.date.today() + dt.timedelta(days=jours)).isoformat()}, cle)


def chez_le_client(**env):
    base = {"CLIENT_CONFIG": CONF, "META_APP_SECRET": "s", "MEGGA_INSTALLATION": "client", "MEGGA_LICENCE": jeton(),
            "META_VERIFY_TOKEN": "abonnement"}
    return creer({**base, **env}, agent=FauxAgent(), expediteur=FauxExpediteur(), cle_licence=CLE.public_key())


# La licence


def test_licence_valide_expiree_refusee():
    pub = CLE.public_key()
    assert licence.verifier(jeton(), "exemple", cle=pub)["etat"] == "valide"
    assert licence.verifier(jeton(jours=-5), "exemple", cle=pub)["etat"] == "expiree"  # délai de grâce
    refus = [
        (jeton(jours=-(licence.GRACE_JOURS + 1)), "délai de grâce passé"),
        (jeton(client="autre"), "autre client"),
        (jeton(cle=AUTRE_CLE), "non signée par MEGGA"),
        ("", "absente"),
        ("abc", "mal formée"),
    ]
    for j, motif in refus:
        with pytest.raises(licence.LicenceRefusee, match=motif):
            licence.verifier(j, "exemple", cle=pub)
    # une licence retouchée (autre date) ne passe plus
    donnees, signature = jeton().split(".")
    faux = licence._b64(json.dumps({"client": "exemple", "jusqu_au": "2099-12-31"}).encode())
    with pytest.raises(licence.LicenceRefusee, match="non signée"):
        licence.verifier(f"{faux}.{signature}", "exemple", cle=pub)


def test_etat_du_jour_d_un_conteneur_qui_tourne_longtemps():
    lic = {"jusqu_au": "2027-01-31"}
    assert licence.etat_du_jour(lic, dt.date(2027, 1, 31))["etat"] == "valide"
    assert licence.etat_du_jour(lic, dt.date(2027, 2, 15))["etat"] == "expiree"
    assert licence.etat_du_jour(lic, dt.date(2027, 4, 1))["etat"] == "hors_delai"


def test_sans_licence_pas_de_demarrage_chez_le_client():
    for mauvaise in ("", jeton(client="autre"), jeton(cle=AUTRE_CLE)):
        with pytest.raises(licence.LicenceRefusee):
            chez_le_client(MEGGA_LICENCE=mauvaise)
    # chez MEGGA (derrière la porte), aucune licence n'est demandée
    creer({"CLIENT_CONFIG": CONF, "META_APP_SECRET": "s"}, agent=FauxAgent(), expediteur=FauxExpediteur())


def test_sante_chez_le_client():
    s = TestClient(chez_le_client()).get("/sante").json()
    assert s["installation"] == "client" and s["licence"]["etat"] == "valide"


def test_la_cle_publique_absente_de_l_image(monkeypatch, tmp_path):
    monkeypatch.setattr(licence, "CLE_PUBLIQUE", tmp_path / "absente.pub")
    with pytest.raises(licence.LicenceRefusee, match="absente de l'image"):
        licence.verifier(jeton(), "exemple")


# Le webhook direct


def test_abonnement_du_webhook_de_meta():
    t = TestClient(chez_le_client())
    ok = t.get("/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "abonnement", "hub.challenge": "42"})
    assert ok.status_code == 200 and ok.text == "42"
    for mauvais in ({"hub.mode": "subscribe", "hub.verify_token": "faux", "hub.challenge": "42"},
                    {"hub.mode": "autre", "hub.verify_token": "abonnement", "hub.challenge": "42"}, {}):
        assert t.get("/whatsapp", params=mauvais).status_code == 403
    sans_jeton = TestClient(chez_le_client(META_VERIFY_TOKEN=""))
    assert sans_jeton.get("/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "", "hub.challenge": "1"}).status_code == 403


# Les secrets en fichiers


def test_secrets_lus_dans_des_fichiers(tmp_path):
    (tmp_path / "anthropic").write_text("cle-anthropic\n")
    env = charger({"ANTHROPIC_API_KEY_FILE": str(tmp_path / "anthropic"), "DEEPSEEK_API_KEY": "direct",
                   "DEEPSEEK_API_KEY_FILE": str(tmp_path / "inutile")})
    assert env["ANTHROPIC_API_KEY"] == "cle-anthropic"  # sans le saut de ligne
    assert env["DEEPSEEK_API_KEY"] == "direct"  # la variable passe avant le fichier
    with pytest.raises(RuntimeError, match="illisible"):
        charger({"META_TOKEN_FILE": str(tmp_path / "absent")})


def test_la_licence_en_fichier(tmp_path):
    (tmp_path / "licence").write_text(jeton())
    s = TestClient(chez_le_client(MEGGA_LICENCE="", MEGGA_LICENCE_FILE=str(tmp_path / "licence"))).get("/sante").json()
    assert s["licence"]["etat"] == "valide"


# Les rappels sans porte


def test_chez_le_client_l_agent_veille_ses_rappels(tmp_path):
    from noyau import stockage

    rappels = stockage.Rappels(f"sqlite:///{tmp_path}/r.db")
    rappels.ajouter("+41790000000", time.time() - 1, "appeler l'agence")

    class Ouvert:
        def dernier(self, personne):
            return time.time()

        def noter(self, *a):
            pass

    exp = FauxExpediteur()
    app = creer({"CLIENT_CONFIG": CONF, "META_APP_SECRET": "s", "MEGGA_INSTALLATION": "client", "MEGGA_LICENCE": jeton()},
                agent=FauxAgent(), expediteur=exp, contacts=Ouvert(), rappels=rappels, cle_licence=CLE.public_key())
    with TestClient(app) as t:  # la veille démarre avec l'application
        for _ in range(50):
            if exp.envois:
                break
            t.portal.call(asyncio.sleep, 0.05)
    assert exp.envois == [("+41790000000", "Rappel : appeler l'agence")]
    assert rappels.en_attente() == 0


def test_chez_megga_la_porte_reveille_les_rappels(tmp_path):
    """Derrière la porte, pas de veille : c'est l'alarme de l'objet du client qui appelle /interne/rappels."""
    from noyau import stockage

    rappels = stockage.Rappels(f"sqlite:///{tmp_path}/r.db")
    rappels.ajouter("+41790000000", time.time() - 1, "appeler l'agence")
    exp = FauxExpediteur()
    app = creer({"CLIENT_CONFIG": CONF, "META_APP_SECRET": "s"}, agent=FauxAgent(), expediteur=exp, rappels=rappels)
    with TestClient(app) as t:
        t.portal.call(asyncio.sleep, 0.2)
    assert exp.envois == [] and rappels.en_attente() == 1


# Les fichiers d'installation


def test_compose_n_expose_que_le_webhook():
    c = yaml.safe_load(open("installation/compose/docker-compose.yml"))
    agent = c["services"]["agent"]
    assert "ports" not in agent and agent["environment"]["MEGGA_INSTALLATION"] == "client"
    assert "healthcheck" in agent and agent["depends_on"]["base"]["condition"] == "service_healthy"
    assert c["services"]["entree"]["ports"] == ["80:80", "443:443"]
    caddy = open("installation/compose/Caddyfile").read()
    assert "handle /whatsapp" in caddy and "respond 404" in caddy
    secrets = open("installation/compose/exemple-secrets.env").read()
    for k in ("MEGGA_LICENCE", "META_TOKEN", "META_APP_SECRET", "META_VERIFY_TOKEN", "ANTHROPIC_API_KEY"):
        assert f"\n{k}=\n" in secrets  # des noms, jamais de valeur


def test_helm_un_seul_agent_sans_droits():
    d = open("installation/helm/megga-agent/templates/deployment.yaml").read()
    for attendu in ("replicas: 1", "type: Recreate", "runAsNonRoot: true", "readOnlyRootFilesystem: true",
                    "MEGGA_INSTALLATION, value: client", "path: /sante"):
        assert attendu in d
    assert "path: /whatsapp" in open("installation/helm/megga-agent/templates/ingress.yaml").read()


# Corrections de la relecture


def test_l_arret_laisse_finir_les_tours_en_cours():
    """SIGTERM (mise à jour, redémarrage) : la réponse en route part avant que l'agent s'arrête."""
    from test_app import corps, signe

    class Lent:
        async def arun(self, texte, user_id=None, session_id=None):
            await asyncio.sleep(0.3)
            return type("S", (), {"content": "Voilà.", "status": "COMPLETED"})()

    exp = FauxExpediteur()
    app = creer({"CLIENT_CONFIG": CONF, "META_APP_SECRET": "secret-essai"}, agent=Lent(), expediteur=exp, attente=0.01)
    with TestClient(app) as t:
        c = corps()
        t.post("/whatsapp", content=c, headers=signe(c))
        assert exp.envois == []  # le tour est en route quand l'arrêt arrive
    assert [texte for _, texte in exp.envois] == ["Voilà."]


def test_l_arret_laisse_la_veille_finir_sa_tournee():
    """L'arrêt arrive pendant l'envoi d'un rappel : il part en entier, et il est marqué (pas de doublon au redémarrage)."""

    class Rappels:
        def __init__(self):
            self.rendu, self.marques = False, []

        def echus(self, maintenant):
            if self.rendu:
                return []
            self.rendu = True
            return [{"id": "r1", "personne": "+41790000000", "texte": "appeler l'agence", "quand": 0}]

        def marquer(self, ident, etat):
            self.marques.append((ident, etat))

        def prochain(self):
            return None

        def differes(self, personne):
            return []

        def en_attente(self):
            return 0

    class Ouvert:
        def dernier(self, personne):
            return time.time()

        def noter(self, *a):
            pass

    class EnvoiLent(FauxExpediteur):
        def __init__(self):
            super().__init__()
            self.commence = False

        async def texte(self, vers, texte):
            self.commence = True
            await asyncio.sleep(0.3)
            await super().texte(vers, texte)

    exp, rappels = EnvoiLent(), Rappels()
    app = creer({"CLIENT_CONFIG": CONF, "META_APP_SECRET": "s", "MEGGA_INSTALLATION": "client", "MEGGA_LICENCE": jeton()},
                agent=FauxAgent(), expediteur=exp, contacts=Ouvert(), rappels=rappels, cle_licence=CLE.public_key())
    with TestClient(app) as t:
        for _ in range(50):
            if exp.commence:
                break
            t.portal.call(asyncio.sleep, 0.02)
        assert exp.commence and exp.envois == []  # l'envoi est en route quand l'arrêt arrive
    assert exp.envois == [("+41790000000", "Rappel : appeler l'agence")]
    assert rappels.marques == [("r1", "envoye")]


def test_une_licence_hors_delai_arrete_un_agent_deja_lance(monkeypatch):
    from test_app import corps, signe

    app = creer({"CLIENT_CONFIG": CONF, "META_APP_SECRET": "secret-essai", "MEGGA_INSTALLATION": "client", "MEGGA_LICENCE": jeton()},
                agent=FauxAgent(), expediteur=FauxExpediteur(), cle_licence=CLE.public_key())
    t = TestClient(app)
    assert t.get("/sante").status_code == 200
    # des mois plus tard, le conteneur n'a jamais redémarré
    monkeypatch.setattr(licence, "etat_du_jour", lambda lic, aujourd_hui=None: {"jusqu_au": lic["jusqu_au"], "etat": "hors_delai"})
    s = t.get("/sante")
    assert s.status_code == 503 and s.json()["ok"] is False and s.json()["licence"]["etat"] == "hors_delai"
    c = corps()
    assert t.post("/whatsapp", content=c, headers=signe(c)).status_code == 503


def test_jetons_non_ascii():
    t = TestClient(chez_le_client(META_VERIFY_TOKEN="abonnement-été", INTERNE_TOKEN="jeton"))
    ok = t.get("/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "abonnement-été", "hub.challenge": "7"})
    assert ok.status_code == 200 and ok.text == "7"
    assert t.get("/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "é", "hub.challenge": "7"}).status_code == 403
    # un en-tête aux octets non ASCII : refusé, pas d'erreur 500
    assert t.post("/interne/rappels", headers={"x-megga-interne": "é".encode()}).status_code == 401


def test_la_cle_des_licences_ne_passe_jamais_en_ligne_de_commande(tmp_path, monkeypatch, capsys):
    """scripts/licence.py cle : la clé privée va au trousseau par l'entrée standard, et une clé déjà là est gardée."""
    import importlib.util
    import re
    import types

    spec = importlib.util.spec_from_file_location("script_licence", "scripts/licence.py")
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    monkeypatch.setattr(licence, "CLE_PUBLIQUE", tmp_path / "licence.pub")
    trousseau, appels = {}, []

    def security(args, input=None, **k):
        appels.append((args, input))
        if args[:2] == ["security", "find-generic-password"]:
            present = script.SERVICE in trousseau
            return types.SimpleNamespace(returncode=0 if present else 44, stdout=trousseau.get(script.SERVICE, ""))
        if args == ["security", "-i"]:
            trousseau[script.SERVICE] = re.search(r"-w (\S+)", input).group(1)
            return types.SimpleNamespace(returncode=0, stdout="")
        raise AssertionError(f"appel inattendu : {args}")

    monkeypatch.setattr(script.subprocess, "run", security)
    assert script.cle() == 0 and licence.CLE_PUBLIQUE.exists()
    cle_privee = trousseau[script.SERVICE]
    assert all(cle_privee not in " ".join(a) for a, _ in appels)  # jamais dans une ligne de commande
    # la clé rangée signe des licences que la clé publique de l'image reconnaît
    assert script.emettre("exemple", "2099-12-31") == 0
    assert licence.verifier(capsys.readouterr().out.strip().splitlines()[-1], "exemple")["etat"] == "valide"
    # une seule paire de clés : ni par-dessus la clé publique, ni par-dessus celle du trousseau
    assert script.cle() == 1
    licence.CLE_PUBLIQUE.unlink()
    assert script.cle() == 1 and trousseau[script.SERVICE] == cle_privee
    assert "déjà au trousseau" in capsys.readouterr().out
